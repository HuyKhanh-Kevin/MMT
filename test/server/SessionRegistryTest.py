from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
import uuid

from server.account_exception import AccountException
from server.account_store import Account
from server.session_registry import SessionRegistry


class SessionRegistryTest(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.registry = SessionRegistry(clock=lambda: self.now)
        self.connection = uuid.uuid4()
        self.account = Account(1, "alice")
        self.source = ("127.0.0.1", 7000)
        self.first = self.registry.login(self.account, "127.0.0.1", 5001, 6001, self.connection)
        self.token = self.first.session_id

    def test_heartbeat_refreshes_but_replay_and_discovery_do_not(self):
        self.now = 10
        self.registry.heartbeat(self.token, 1, 2, self.source)
        self.now = 20
        self.registry.heartbeat(self.token, 1, 1, self.source)
        self.registry.heartbeat(self.token, 1, 2, self.source)
        self.assertEqual(1, len(self.registry.discover(self.token, 1, self.source)))
        self.now = 25
        with self.assertRaises(AccountException):
            self.registry.heartbeat(self.token, 1, 3, self.source)
        self.registry.expire()
        self.assertEqual((), self.registry.online_peers())
        self.assertEqual((self.connection,), self.registry.drain_disconnected_connections())

    def test_token_user_ip_port_and_connection_must_all_match(self):
        self.registry.heartbeat(self.token, 1, 1, self.source)
        attempts = (("bad", 1, self.source), (self.token, 2, self.source),
                    (self.token, 1, ("192.0.2.1", 7000)),
                    (self.token, 1, ("127.0.0.1", 7001)))
        for token, user, source in attempts:
            with self.assertRaises(AccountException):
                self.registry.authenticate_udp(token, user, source)
        with self.assertRaises(AccountException):
            self.registry.logout(self.token, 1, uuid.uuid4())
        for seq in (0, -1, True, 0x100000000):
            with self.assertRaises(AccountException):
                self.registry.heartbeat(self.token, 1, seq, self.source)

    def test_logout_relogin_rotates_token_and_updates_endpoints(self):
        self.registry.logout(self.token, 1, self.connection)
        second = self.registry.login(self.account, "192.0.2.2", 5010, 6010, self.connection)
        self.assertNotEqual(self.token, second.session_id)
        self.assertEqual(43, len(second.session_id))
        self.assertEqual(("192.0.2.2", 5010, 6010),
                         (second.peer.ip, second.peer.tcp_port, second.peer.file_udp_port))
        with self.assertRaises(AccountException):
            self.registry.authenticate_tcp(self.token, 1, self.connection)

    def test_expired_connection_cannot_relogin_or_delete_new_session(self):
        self.now = 15
        self.registry.expire()
        self.registry.drain_disconnected_connections()
        with self.assertRaises(AccountException):
            self.registry.login(self.account, "127.0.0.1", 5001, 6001, self.connection)
        new = self.registry.login(self.account, "127.0.0.1", 5002, 6002, uuid.uuid4())
        self.registry.disconnect(self.connection)
        self.assertEqual(new.peer, self.registry.find_online_user(1))

    def test_disconnect_emits_one_offline_event(self):
        self.registry.drain_changes()
        self.registry.disconnect(self.connection)
        self.registry.disconnect(self.connection)
        self.now = 20
        self.registry.expire()
        self.assertEqual(["offline"], [event.status for event in self.registry.drain_changes()])

    def test_concurrent_login_has_one_winner(self):
        self.registry.logout(self.token, 1, self.connection)
        barrier = threading.Barrier(2)
        def login(_):
            barrier.wait(timeout=3)
            try:
                self.registry.login(self.account, "127.0.0.1", 5001, 6001, uuid.uuid4())
                return True
            except AccountException:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(1, sum(pool.map(login, range(2))))

    def test_discovery_requires_first_heartbeat(self):
        with self.assertRaises(AccountException) as error:
            self.registry.discover(self.token, 1, self.source)
        self.assertEqual("HEARTBEAT_REQUIRED", error.exception.reason)
