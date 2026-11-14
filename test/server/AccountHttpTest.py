from contextlib import ExitStack
import http.client
import json
from pathlib import Path
import socket
import tempfile
import time
import unittest

from apps.account_http import AccountHttpServer
from apps.account_sessions import AccountSessions
from server.tracker_server import TrackerServer


class AccountHttpTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        temp = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.tracker = self.stack.enter_context(TrackerServer(
            tcp_port=0, udp_port=0, account_file=temp / "accounts.json"))
        self.now = 0.0
        self.sessions = self.stack.enter_context(AccountSessions(
            "127.0.0.1", self.tracker.tcp_port, self.tracker.udp_port,
            5001, 6001, clock=lambda: self.now))
        self.http = self.stack.enter_context(AccountHttpServer(self.sessions, 0))

    def request(self, method, path, body=None, token=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.http.port, timeout=5)
        request_headers = dict(headers or {})
        if token:
            request_headers["Authorization"] = "Bearer " + token
        if body is not None:
            body = json.dumps(body)
            request_headers.setdefault("Content-Type", "application/json")
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            self.assertEqual("no-store", response.getheader("Cache-Control"))
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def login(self, name):
        credentials = {"username": name, "password": "password123"}
        self.assertEqual(200, self.request("POST", "/signup", credentials)[0])
        status, result = self.request("POST", "/login", credentials)
        self.assertEqual(200, status)
        return result

    def wait_offline(self, user_id):
        deadline = time.monotonic() + 2
        while self.tracker.sessions.find_online_user(user_id) and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIsNone(self.tracker.sessions.find_online_user(user_id))

    def test_http_requests_keep_tracker_session_and_browser_tokens_are_separate(self):
        alice = self.login("alice")
        bob = self.login("bob")
        token = alice["access_token"]
        self.assertNotIn(token, self.tracker.sessions.active_tokens())
        self.assertNotIn("session_id", alice)
        for _ in range(3):
            status, users = self.request("GET", "/users", token=token)
            self.assertEqual(200, status)
            self.assertEqual({"alice", "bob"}, {u["username"] for u in users["users"]})
        self.assertEqual(2, len(self.tracker.sessions.online_peers()))
        self.assertEqual(200, self.request("POST", "/logout", token=token)[0])
        self.wait_offline(alice["user_id"])
        self.assertEqual(401, self.request("GET", "/users", token=token)[0])
        self.assertEqual(200, self.request("GET", "/session", token=bob["access_token"])[0])
        status, relogin = self.request("POST", "/login", {"username": "alice", "password": "password123"})
        self.assertEqual(200, status)
        self.assertNotEqual(token, relogin["access_token"])
        self.assertEqual(alice["user_id"], relogin["user_id"])

    def test_browser_abandonment_expires_even_though_native_heartbeats_run(self):
        alice = self.login("alice")
        token = alice["access_token"]
        self.now = 14
        self.assertEqual(200, self.request("POST", "/heartbeat", token=token)[0])
        self.now = 28
        self.sessions.expire()
        self.assertIsNotNone(self.tracker.sessions.find_online_user(alice["user_id"]))
        self.now = 29
        self.sessions.expire()
        self.wait_offline(alice["user_id"])
        self.assertEqual(401, self.request("GET", "/session", token=token)[0])

    def test_invalid_credentials_cannot_create_session(self):
        self.login("alice")
        status, result = self.request("POST", "/login", {"username": "alice", "password": "wrongpass"})
        self.assertEqual(409, status)
        self.assertEqual("INVALID_CREDENTIALS", result["reason"])
        self.assertNotIn("access_token", result)
        self.assertEqual(1, len(self.sessions._sessions))
        self.assertEqual(400, self.request("POST", "/login", {"text": "hi"})[0])
        self.assertEqual(401, self.request("GET", "/users", token="forged")[0])

    def test_origin_host_content_type_and_method_are_checked(self):
        credentials = {"username": "alice", "password": "password123"}
        for headers, status in (({"Origin": "https://evil.example"}, 403),
                                ({"Host": "evil.example"}, 403),
                                ({"Content-Type": "text/plain"}, 415)):
            self.assertEqual(status, self.request("POST", "/signup", credentials, headers=headers)[0])
        self.assertEqual(405, self.request("GET", "/login")[0])
        self.assertEqual(404, self.request("GET", "/chat")[0])
        self.assertEqual((), self.tracker.sessions.online_peers())

    def test_malformed_http_is_rejected_without_breaking_next_client(self):
        with socket.create_connection(("127.0.0.1", self.http.port), timeout=3) as peer:
            peer.sendall(b"POST /login HTTP/1.1\r\nContent-Length: 2\r\nContent-Length: 4\r\n\r\n{}")
            self.assertIn(b"400 Bad Request", peer.recv(2048))
        self.login("healthy")

    def test_sampleapp_login_uses_same_service_and_no_longer_returns_fake_success(self):
        from apps import sampleapp
        sampleapp.configure_account_sessions(None)
        result = json.loads(sampleapp.login({}, b'{"username":"alice","password":"password123"}'))
        self.assertEqual("ACCOUNT_API_NOT_CONFIGURED", result["reason"])
        sampleapp.configure_account_sessions(self.sessions)
        self.addCleanup(sampleapp.configure_account_sessions, None)
        credentials = b'{"username":"alice","password":"password123"}'
        self.assertEqual("success", json.loads(sampleapp.signup({}, credentials))["status"])
        result = json.loads(sampleapp.login({}, credentials))
        self.assertEqual("success", result["status"])
        headers = {"Authorization": "Bearer " + result["access_token"]}
        self.assertEqual(1, len(json.loads(sampleapp.users(headers))["users"]))
        self.assertEqual("success", json.loads(sampleapp.logout(headers))["status"])

    def test_tracker_disconnect_invalidates_browser_session(self):
        alice = self.login("alice")
        self.tracker.close()
        deadline = time.monotonic() + 2
        while any(s.client.is_connected for s in self.sessions._sessions.values()) and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(401, self.request("GET", "/session", token=alice["access_token"])[0])
