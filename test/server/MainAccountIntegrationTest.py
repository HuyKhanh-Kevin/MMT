from contextlib import ExitStack
from pathlib import Path
import queue
import tempfile
import time
import unittest
from unittest.mock import patch

from client.client_account import Client
from client.client_listener import Listener
from common.MessageType import MessageType
from common.UdpPacketIO import UdpPacketIO
from server.account_exception import AccountException
from server.tcp_server import TCPServer


class Events(Listener):
    def __init__(self):
        self.presence = queue.Queue()
        self.users = queue.Queue()
        self.messages = queue.Queue()
        self.errors = queue.Queue()
        self.logouts = queue.Queue()

    def display_signup_response(self, status, reason):
        pass

    def display_login_response(self, status, reason):
        pass

    def display_logout_response(self, status):
        self.logouts.put(status)

    def display_user_list(self, users):
        self.users.put(users)

    def display_presence(self, update):
        self.presence.put((update.username, update.status))

    def display_message(self, sender, message):
        self.messages.put((sender, message))

    def display_error(self, code, message):
        self.errors.put((code, message))


class MainAccountIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        temp = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.server = self.stack.enter_context(TCPServer(
            "127.0.0.1", 0, 0, temp / "accounts.json"))

    def register(self, username):
        client = self.stack.enter_context(Client(
            "127.0.0.1", self.server.tcp_port, self.server.udp_port, 6000, 6001))
        client.listener = Events()
        signup = client.create_signup_packet(username, "password123")
        login = client.create_login_packet(username, "password123")
        for packet in (signup, login):
            self.assertEqual(0, packet.header.streamID)
            self.assertGreater(packet.header.sequenceNumber, 0)
            self.assertEqual("success", client.send_tcp_packet(packet).status)
        return client

    def test_console_client_login_discovery_logout_and_relogin(self):
        alice = self.register("alice")
        self.assertTrue(alice.get_authenticated())
        users = alice.request_user_list()
        self.assertEqual(["alice"], [user.username for user in users])
        self.assertEqual(users, tuple(alice.user_list_users))
        self.assertIsNotNone(self.server.session_manager.get_session(alice.id))
        old_id, old_token = alice.id, alice.session_id
        alice.send_tcp_packet(alice.create_logout_packet())
        self.assertEqual("success", alice.listener.logouts.get(timeout=2))
        self.assertIsNone(self.server.session_manager.get_session(old_id))
        self.assertFalse(alice.get_authenticated())
        self.assertTrue(alice.get_running())
        alice.send_tcp_packet(alice.create_login_packet("alice", "password123"))
        self.assertNotEqual(old_token, alice.session_id)
        self.assertEqual(old_id, alice.id)
        marker = object()
        alice.set_file_transfer(marker)
        self.assertIs(marker, alice.file_transfer)
        self.assertEqual(alice.get_outgoing_stream(2), alice.get_outgoing_stream(2))

    def test_presence_and_chat_share_authenticated_server_connections(self):
        alice = self.register("alice")
        alice.request_user_list()
        bob = self.register("bob")
        bob.request_user_list()
        self.assertEqual(("bob", "online"), alice.listener.presence.get(timeout=2))
        bob.send_tcp_packet(bob.create_private_message_packet(alice.id, "hello"))
        self.assertEqual((bob.id, "hello"), alice.listener.messages.get(timeout=2))
        alice.send_tcp_packet(alice.create_global_message_packet("everyone"))
        self.assertEqual((alice.id, "everyone"), bob.listener.messages.get(timeout=2))
        bob.send_tcp_packet(bob.create_logout_packet())
        self.assertEqual(("bob", "offline"), alice.listener.presence.get(timeout=2))

    def test_discovery_timeout_and_server_error_do_not_block_later_requests(self):
        alice = self.register("alice")
        original = UdpPacketIO.sendPacket

        def drop_users(sock, destination, packet):
            if packet.header.messageType != MessageType.USER_LIST_RESPONSE:
                original(sock, destination, packet)

        with patch.object(UdpPacketIO, "sendPacket", side_effect=drop_users):
            self.assertIsNone(alice.request_user_list())
        self.assertIn("timed out", alice.listener.errors.get(timeout=2)[1])
        with patch.object(self.server.directory, "page",
                          side_effect=AccountException(1003, "INVALID_CURSOR")):
            self.assertIsNone(alice.request_user_list())
        self.assertEqual((1003, "INVALID_CURSOR"), alice.listener.errors.get(timeout=2))
        self.assertEqual(["alice"], [user.username for user in alice.request_user_list()])

    def test_periodic_users_recover_lost_presence(self):
        alice = self.register("alice")
        alice.set_listener(alice.listener)
        original = UdpPacketIO.sendPacket

        def drop_presence(sock, destination, packet):
            if packet.header.messageType != MessageType.PRESENCE_UPDATE:
                original(sock, destination, packet)

        with patch.object(UdpPacketIO, "sendPacket", side_effect=drop_presence):
            self.register("bob")
            deadline = time.monotonic() + 7
            while True:
                users = alice.listener.users.get(timeout=max(0.01, deadline - time.monotonic()))
                if {user.username for user in users} == {"alice", "bob"}:
                    break
                if time.monotonic() >= deadline:
                    self.fail("Online users were not refreshed")

    def test_expiry_removes_both_account_and_chat_session(self):
        alice = self.register("alice")
        alice.request_user_list()
        user_id = alice.id
        alice.set_heartbeats_enabled(False)
        self.server.sessions.timeout = 0.3
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if not alice.get_running() and self.server.session_manager.get_session(user_id) is None:
                break
            time.sleep(0.02)
        self.assertFalse(alice.get_running())
        self.assertIsNone(self.server.session_manager.get_session(user_id))
        self.assertEqual((), self.server.sessions.online_peers())
