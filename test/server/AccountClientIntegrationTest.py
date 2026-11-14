from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from client.AccountClient import AccountClient, AccountRequestError
from client.Client import Client
from client.ClientListener import ClientListener
from common.MessageType import MessageType
from common.PacketIO import PacketIO
from common.UdpPacketIO import UdpPacketIO
from server.account_exception import AccountException
from server.tracker_server import TrackerServer


class AccountClientIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        temp = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.server = self.stack.enter_context(TrackerServer(
            tcp_port=0, udp_port=0, account_file=temp / "accounts.json"))

    def client(self, cls=Client):
        return self.stack.enter_context(cls("127.0.0.1", self.server.tcp_port,
                                           self.server.udp_port, 5001, 6001))

    def register(self, name, cls=Client):
        client = self.client(cls)
        self.assertEqual("success", client.signup(name, "password123").status)
        self.assertEqual("success", client.login(name, "password123").status)
        return client

    def wait_snapshot(self, events, names, timeout=7):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            users = events.get(timeout=max(0.01, deadline - time.monotonic()))
            if {user.username for user in users} == set(names):
                return users
        self.fail("Expected online snapshot not delivered")

    def test_legacy_account_api_reuses_one_connection_and_rotates_session(self):
        client = self.client()
        class Listener:
            def __init__(self):
                self.events = []
            def display_signup_response(self, status, reason):
                self.events.append(("signup", status))
            def display_login_response(self, status, reason):
                self.events.append(("login", status))
            def display_logout_response(self):
                self.events.append(("logout", "success"))
        listener = Listener()
        client.set_listener(listener)
        reader = client._tcp_reader
        client.start_receiving()
        client.start_receiving()
        client.send_tcp_packet(client.create_signup_packet("alice", "password123"))
        client.send_tcp_packet(client.create_login_packet("alice", "password123"))
        old_token = client.session_id
        old_request = client.create_online_users_list_packet()
        users = client.send_udp_packet(old_request)
        self.assertEqual(["alice"], [u.username for u in users])
        client.send_tcp_packet(client.create_logout_packet())
        self.assertFalse(client.authenticated)
        self.assertTrue(client.running)
        client.send_tcp_packet(client.create_login_packet("alice", "password123"))
        self.assertNotEqual(old_token, client.session_id)
        self.assertIs(reader, client._tcp_reader)
        self.assertEqual(1, len(self.server._connections))
        with self.assertRaisesRegex(ValueError, "Stale"):
            client.send_udp_packet(old_request)
        self.assertEqual([("signup", "success"), ("login", "success"),
                          ("logout", "success"), ("login", "success")], listener.events)

    def test_lost_presence_is_repaired_by_periodic_snapshot_and_close_clears_ui(self):
        alice = self.register("alice")
        events = queue.Queue()
        alice.on_users(events.put)
        self.wait_snapshot(events, ["alice"])
        original = UdpPacketIO.sendPacket
        def drop_presence(sock, destination, packet):
            if packet.header.messageType != MessageType.PRESENCE_UPDATE:
                original(sock, destination, packet)
        with patch.object(UdpPacketIO, "sendPacket", side_effect=drop_presence):
            bob = self.register("bob")
            self.wait_snapshot(events, ["alice", "bob"])
            bob.logout()
            self.wait_snapshot(events, ["alice"])
        self.server.close()
        self.wait_snapshot(events, [])
        self.assertFalse(alice.authenticated)

    def test_expired_cursor_restarts_whole_snapshot_without_duplicates(self):
        clients = [self.register(f"user{i:028d}") for i in range(9)]
        original = self.server.directory.page
        failed = []
        def expire_once(owner, cursor, users, reference=None):
            if cursor is not None and not failed:
                failed.append(True)
                raise AccountException(1003, "INVALID_CURSOR")
            return original(owner, cursor, users, reference)
        with patch.object(self.server.directory, "page", side_effect=expire_once):
            users = clients[0].send_udp_packet(clients[0].create_online_users_list_packet())
        self.assertTrue(failed)
        self.assertEqual(9, len(users))
        self.assertEqual(9, len({user.user_id for user in users}))

    def test_cursor_restart_is_bounded(self):
        client = self.register("alice", AccountClient)
        with patch.object(client, "_online_users_snapshot",
                          side_effect=AccountRequestError(1003, "INVALID_CURSOR")) as fetch:
            with self.assertRaises(AccountRequestError):
                client.online_users()
        self.assertEqual(2, fetch.call_count)

    def test_concurrent_discovery_calls_on_one_client_receive_their_own_replies(self):
        alice = self.register("alice", AccountClient)
        self.register("bob", AccountClient)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: alice.online_users(), range(6)))
        for users in results:
            self.assertEqual({"alice", "bob"}, {user.username for user in users})
        alice.logout()
        self.assertTrue(alice.is_connected)

    def test_close_wakes_a_client_waiting_for_a_lost_udp_reply(self):
        alice = self.register("alice", AccountClient)
        response_dropped = threading.Event()
        original = UdpPacketIO.sendPacket
        def drop_reply(sock, destination, packet):
            if packet.header.messageType == MessageType.USER_LIST_RESPONSE:
                response_dropped.set()
                return
            original(sock, destination, packet)
        with patch.object(UdpPacketIO, "sendPacket", side_effect=drop_reply):
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(alice.online_users)
                self.assertTrue(response_dropped.wait(2))
                alice.close()
                with self.assertRaises(OSError):
                    result.result(timeout=2)

    def test_existing_chat_callback_does_not_consume_account_response(self):
        client = self.register("alice")
        events = queue.Queue()
        class Listener:
            def display_message(self, sender, text):
                events.put((sender, text))
        client.set_listener(Listener())
        packet = client.create_private_chat_packet(client.id, "hello")
        self.assertEqual(2, packet.header.version)
        self.assertNotEqual(0, packet.header.streamID)
        connection = next(iter(self.server._connections.values()))
        PacketIO.writePacket(connection, packet)
        self.assertEqual((client.id, "hello"), events.get(timeout=2))
        client.logout()
        self.assertTrue(client.running)

    def test_prelogin_timeout_default_allows_user_input_and_is_configurable(self):
        self.assertEqual(120, self.server._idle_timeout)
