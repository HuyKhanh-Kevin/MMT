"""Exercise the Python implementation with real TCP/UDP sockets and clients."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
from pathlib import Path
import queue
import socket
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from client.AccountClient import AccountClient
from common.ControlPackets import ControlPackets
from common.JsonPayloadCodec import JsonPayloadCodec
from common.MessageType import MessageType as MT
from common.Packet import Packet
from common.PacketHeader import PacketHeader
from common.PacketIO import PacketIO
from common.UdpPacketIO import UdpPacketIO
from common.payload.ErrorPayload import ErrorPayload
from common.payload.Heartbeat import Heartbeat
from common.payload.LoginRequest import LoginRequest
from common.payload.LoginResponse import LoginResponse
from common.payload.LogoutRequest import LogoutRequest
from common.payload.SignupRequest import SignupRequest
from common.payload.UserListRequest import UserListRequest
from common.payload.UserListResponse import UserListResponse
from server.tracker_server import TrackerServer


class WireClient:
    def __init__(self, server):
        self.tcp = socket.create_connection(("127.0.0.1", server.tcp_port), timeout=3)
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("127.0.0.1", 0))
        self.udp.settimeout(3)
        self.address = ("127.0.0.1", server.udp_port)
        self.sequence = 0

    def packet(self, kind, sender, body):
        self.sequence += 1
        return ControlPackets.create(str(kind), self.sequence, sender, 0, body)

    def control(self, kind, sender, body):
        request = self.packet(kind, sender, body)
        PacketIO.writePacket(self.tcp, request)
        return PacketIO.readPacket(self.tcp)

    def datagram(self, kind, sender, body):
        request = self.packet(kind, sender, body)
        UdpPacketIO.sendPacket(self.udp, self.address, request)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            response = UdpPacketIO.receivePacket(self.udp).packet
            if response.header.messageType == MT.PRESENCE_UPDATE:
                continue
            if response.header.sequenceNumber == request.header.sequenceNumber:
                return response
        raise TimeoutError("No matching UDP reply")

    def register(self, name="alice"):
        self.control(MT.SIGNUP_REQUEST, 0, SignupRequest(name, "password123"))
        response = self.control(MT.LOGIN_REQUEST, 0, LoginRequest(name, "password123", 5001, 6001))
        login = JsonPayloadCodec.decode(response.payload, LoginResponse)
        UdpPacketIO.sendPacket(self.udp, self.address, self.packet(
            MT.HEARTBEAT, login.user_id, Heartbeat(login.session_id, 1)))
        # Round trip behind the heartbeat establishes that the server received it.
        self.datagram(MT.USER_LIST_REQUEST, login.user_id, UserListRequest(login.session_id, None))
        return login

    def close(self):
        self.tcp.close()
        self.udp.close()


class TrackerServerTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temp = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.server = self.stack.enter_context(TrackerServer(
            tcp_port=0, udp_port=0, account_file=self.temp / "accounts.json"))

    def client(self, **kwargs):
        return self.stack.enter_context(AccountClient(
            "127.0.0.1", self.server.tcp_port, self.server.udp_port,
            kwargs.get("tcp_port", 5001), kwargs.get("udp_port", 6001)))

    def wire(self):
        wire = WireClient(self.server)
        self.stack.callback(wire.close)
        return wire

    def login(self, name):
        client = self.client()
        self.assertEqual("success", client.signup(name, "password123").status)
        self.assertTrue(client.login(name, "password123").is_success)
        client.online_users()
        return client

    def assert_error(self, packet, code):
        self.assertEqual(MT.ERROR, packet.header.messageType)
        error = JsonPayloadCodec.decode(packet.payload, ErrorPayload)
        self.assertEqual(code, error.error_code)
        self.assertEqual(packet.header.sequenceNumber, error.related_sequence_number)

    def await_condition(self, condition, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.01)
        self.assertTrue(condition())

    def test_account_lifecycle_presence_and_relogin(self):
        alice = self.login("alice")
        events = queue.Queue()
        alice.on_presence(events.put)
        duplicate = self.client()
        self.assertEqual("USERNAME_TAKEN", duplicate.signup("alice", "password123").reason)
        self.assertEqual("INVALID_CREDENTIALS", duplicate.login("alice", "wrongpass").reason)
        self.assertEqual("ALREADY_ONLINE", duplicate.login("alice", "password123").reason)
        bob = self.login("bob")
        self.assertEqual(("bob", "online"), self.event(events))
        self.assertEqual(["alice", "bob"], [user.username for user in alice.online_users()])
        old_token, user_id = bob.session_id, bob.user_id
        bob.logout()
        self.assertEqual(("bob", "offline"), self.event(events))
        self.assertFalse(bob.is_authenticated)
        self.assertTrue(bob.is_connected)
        bob.login("bob", "password123")
        self.assertEqual(user_id, bob.user_id)
        self.assertNotEqual(old_token, bob.session_id)

    @staticmethod
    def event(events, timeout=3):
        event = events.get(timeout=timeout)
        return event.username, event.status

    def test_production_heartbeat_keeps_observer_and_silent_peer_expires(self):
        observer = self.login("observer")
        events = queue.Queue()
        observer.on_presence(events.put)
        silent = self.login("silent")
        silent_id = silent.user_id
        silent.set_heartbeats_enabled(False)
        self.assertEqual(("silent", "online"), self.event(events))
        self.assertEqual(("silent", "offline"), self.event(events, timeout=18))
        self.await_condition(lambda: not silent.is_connected and not silent.is_authenticated)
        self.assertIsNone(self.server.sessions.find_online_user(silent_id))
        self.assertTrue(observer.is_authenticated)
        self.assertEqual(["observer"], [user.username for user in observer.online_users()])

    def test_abrupt_disconnect_publishes_offline_without_waiting_fifteen_seconds(self):
        observer = self.login("observer")
        events = queue.Queue()
        observer.on_presence(events.put)
        dropped = self.login("dropped")
        self.assertEqual(("dropped", "online"), self.event(events))
        dropped.close()
        self.assertEqual(("dropped", "offline"), self.event(events))
        self.assertEqual(1, len(observer.online_users()))

    def test_forged_sessions_sources_and_old_tokens_are_rejected(self):
        alice = self.wire()
        login = alice.register()
        attacker = self.wire()
        self.assert_error(attacker.control(MT.LOGOUT_REQUEST, login.user_id,
                                          LogoutRequest(login.session_id)), 1004)
        self.assert_error(attacker.datagram(MT.HEARTBEAT, login.user_id,
                                           Heartbeat(login.session_id, 500)), 1004)
        self.assert_error(alice.datagram(MT.USER_LIST_REQUEST, login.user_id + 1,
                                        UserListRequest(login.session_id)), 1004)
        self.assert_error(alice.datagram(MT.USER_LIST_REQUEST, login.user_id,
                                        UserListRequest("bad")), 1004)
        alice.control(MT.LOGOUT_REQUEST, login.user_id, LogoutRequest(login.session_id))
        self.assert_error(alice.datagram(MT.USER_LIST_REQUEST, login.user_id,
                                        UserListRequest(login.session_id)), 1004)

    def test_malformed_json_and_udp_datagrams_do_not_kill_server(self):
        wire = self.wire()
        malformed = (b'{"username":"alice"}', b'{"username":12,"password":"password123"}',
                     b'{"username":"a","username":"b","password":"password123"}',
                     b'{"username":"alice","password":"password123","extra":true}',
                     b'\xc3\x28', b'[]', b'null', b'{')
        for payload in malformed:
            wire.sequence += 1
            packet = Packet(PacketHeader(2, MT.SIGNUP_REQUEST, 0, 0, wire.sequence,
                                         len(payload), 0, 0), payload)
            PacketIO.writePacket(wire.tcp, packet)
            self.assert_error(PacketIO.readPacket(wire.tcp), 1003)
        for data in (b"bad", bytes(1300)):
            wire.udp.sendto(data, wire.address)
        self.assert_error(wire.datagram(MT.USER_LIST_REQUEST, 1, UserListRequest("fake")), 1004)
        self.assertTrue(wire.register().is_success)

    def test_invalid_control_headers_ports_and_transports_are_rejected(self):
        wire = self.wire()
        for change in ({"flags": 1}, {"streamID": 1}, {"sequenceNumber": 0}, {"receiverID": 1}):
            payload = JsonPayloadCodec.encode(SignupRequest("alice", "password123"))
            fields = dict(version=2, messageType=MT.SIGNUP_REQUEST, flags=0, streamID=0,
                          sequenceNumber=10, payloadLength=len(payload), senderID=0, receiverID=0)
            fields.update(change)
            PacketIO.writePacket(wire.tcp, Packet(PacketHeader(**fields), payload))
            self.assert_error(PacketIO.readPacket(wire.tcp), 1003)
        body = dict(username="alice", password="password123", tcp_port=0, file_udp_port=6000)
        self.assert_error(wire.control(MT.LOGIN_REQUEST, 0, body), 1003)
        self.assert_error(wire.datagram(MT.SIGNUP_REQUEST, 0, SignupRequest("alice", "password123")), 1003)
        self.assertEqual((), self.server.sessions.online_peers())

    def test_partial_frame_disconnect_does_not_block_healthy_client(self):
        for wire_bytes in (bytes(10), struct.pack("!BBHIIIII", 2, MT.LOGIN_REQUEST, 0, 0, 1, 0, 0, 1200)):
            with socket.create_connection(("127.0.0.1", self.server.tcp_port), timeout=3) as peer:
                peer.sendall(wire_bytes)
                peer.shutdown(socket.SHUT_WR)
                self.assertEqual(b"", peer.recv(1))
        self.assertTrue(self.login("healthy").is_connected)

    def test_twenty_concurrent_clients_have_complete_paginated_discovery(self):
        clients = [self.client() for _ in range(20)]
        def register(index):
            client = clients[index]
            name = f"user{index:028d}"
            self.assertEqual("success", client.signup(name, "password123").status)
            self.assertTrue(client.login(name, "password123").is_success)
        with ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(register, range(20)))
        for client in clients:
            users = client.online_users()
            self.assertEqual(20, len(users))
            self.assertEqual(20, len({user.user_id for user in users}))
            self.assertTrue(all(user.ip == "127.0.0.1" for user in users))
        for client in clients:
            client.close()
        self.await_condition(lambda: not self.server.sessions.online_peers())

    def test_lost_discovery_reply_retries_same_reference_and_returns_all_users(self):
        alice = self.login("alice")
        original_send = UdpPacketIO.sendPacket
        responses = []
        def drop_first(sock, destination, packet):
            if packet.header.messageType == MT.USER_LIST_RESPONSE:
                responses.append(packet)
                if len(responses) == 1:
                    return
            original_send(sock, destination, packet)
        with patch.object(UdpPacketIO, "sendPacket", side_effect=drop_first):
            self.assertEqual(["alice"], [user.username for user in alice.online_users()])
        self.assertEqual(2, len(responses))
        self.assertEqual(responses[0].header.sequenceNumber, responses[1].header.sequenceNumber)
        self.assertEqual(responses[0].payload, responses[1].payload)

    def test_lost_initial_heartbeat_is_recovered_by_discovery(self):
        alice = self.client()
        alice.signup("alice", "password123")
        original_send = UdpPacketIO.sendPacket
        dropped = []
        def drop_first(sock, destination, packet):
            if packet.header.messageType == MT.HEARTBEAT and not dropped:
                dropped.append(True)
                return
            original_send(sock, destination, packet)
        with patch.object(UdpPacketIO, "sendPacket", side_effect=drop_first):
            alice.login("alice", "password123")
            self.assertEqual(1, len(alice.online_users()))
        self.assertTrue(alice.is_authenticated)

    def test_presence_callback_can_refresh_users_without_deadlock(self):
        alice = self.login("alice")
        result = queue.Queue()
        def refresh(event):
            if event.username == "bob" and event.status == "online":
                result.put(alice.online_users())
        alice.on_presence(refresh)
        self.login("bob")
        self.assertEqual(2, len(result.get(timeout=4)))

    def test_discovered_endpoints_accept_tcp_and_udp_data_after_relogin(self):
        alice = self.login("alice")
        old = self.login("bob")
        old_id = old.user_id
        old.logout()
        with self.assertRaisesRegex(OSError, "RECIPIENT_OFFLINE"):
            alice.peer_endpoint(old_id)
        with socket.socket() as peer, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as file:
            peer.bind(("127.0.0.1", 0))
            peer.listen(1)
            peer.settimeout(3)
            file.bind(("127.0.0.1", 0))
            file.settimeout(3)
            new = self.client(tcp_port=peer.getsockname()[1], udp_port=file.getsockname()[1])
            self.assertEqual(old_id, new.login("bob", "password123").user_id)
            endpoint = alice.peer_endpoint(old_id)
            with socket.create_connection(endpoint.tcp, timeout=3) as sender:
                recipient, _ = peer.accept()
                with recipient:
                    recipient.settimeout(3)
                    sender.sendall(b"hello")
                    self.assertEqual(b"hello", recipient.recv(5))
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                data = bytes(range(256)) * 4
                sender.sendto(data, endpoint.file_udp)
                self.assertEqual(data, file.recvfrom(1200)[0])

    def test_server_shutdown_notifies_clients_and_cleans_sessions(self):
        alice = self.login("alice")
        self.server.close()
        self.await_condition(lambda: not alice.is_connected and not alice.is_authenticated)
        self.assertEqual((), self.server.sessions.online_peers())

    def test_connection_limit_and_prelogin_timeout_release_slots(self):
        with TrackerServer(tcp_port=0, udp_port=0, account_file=self.temp / "limited.json",
                           max_connections=1, idle_timeout=0.3) as server:
            with socket.create_connection(("127.0.0.1", server.tcp_port), timeout=3) as idle:
                self.await_condition(lambda: len(server._connections) == 1)
                with socket.create_connection(("127.0.0.1", server.tcp_port), timeout=3) as extra:
                    self.assertEqual(b"", extra.recv(1))
                self.assertEqual(b"", idle.recv(1))
            self.await_condition(lambda: len(server._connections) == 0)
            with AccountClient("127.0.0.1", server.tcp_port, server.udp_port, 5001, 6001) as client:
                self.assertEqual("success", client.signup("healthy", "password123").status)
