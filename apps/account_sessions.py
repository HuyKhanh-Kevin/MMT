"""Persistent native account connections behind a local browser's HTTP requests.

Run this bridge on the peer's machine: advertised ports belong to native peer
modules on that machine, never to a remote browser. Browser leases are separate
from tracker tokens and expire when the browser stops polling/heartbeating.
"""

from dataclasses import dataclass
import secrets
import threading
import time

from client.AccountClient import AccountClient


class WebAccountError(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status
        self.reason = reason


@dataclass
class _BrowserSession:
    client: AccountClient
    username: str
    last_activity: float


class AccountSessions:
    def __init__(self, host, tcp_port, udp_port, peer_tcp_port, file_udp_port,
                 *, browser_timeout=15.0, max_sessions=64, clock=time.monotonic):
        if browser_timeout <= 0 or max_sessions < 1:
            raise ValueError("Invalid browser session limits")
        self._address = (host, tcp_port, udp_port, peer_tcp_port, file_udp_port)
        self._timeout = browser_timeout
        self._limit = max_sessions
        self._clock = clock
        self._lock = threading.RLock()
        self._sessions = {}
        self._creating = 0
        self._closed = False
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._reap_loop, name="browser-sessions", daemon=True)
        self._worker.start()

    def _new_client(self):
        with self._lock:
            if self._closed:
                raise WebAccountError(503, "ACCOUNT_SERVICE_CLOSED")
            if len(self._sessions) + self._creating >= self._limit:
                raise WebAccountError(503, "ACCOUNT_SERVICE_BUSY")
            self._creating += 1
        try:
            return AccountClient(*self._address)
        except BaseException:
            with self._lock:
                self._creating -= 1
            raise

    def signup(self, username, password):
        client = self._new_client()
        try:
            response = client.signup(username, password)
            return {"status": response.status, "reason": response.reason}
        finally:
            client.close()
            with self._lock:
                self._creating -= 1

    def login(self, username, password):
        client = self._new_client()
        registered = False
        try:
            response = client.login(username, password)
            if response.status != "success":
                return {"status": "failed", "reason": response.reason}
            # Ensure UDP registration works before publishing a browser session.
            client.online_users()
            with self._lock:
                if self._closed:
                    raise WebAccountError(503, "ACCOUNT_SERVICE_CLOSED")
                token = secrets.token_urlsafe(32)
                while token in self._sessions:
                    token = secrets.token_urlsafe(32)
                self._sessions[token] = _BrowserSession(client, username, self._clock())
                registered = True
            return {"status": "success", "access_token": token,
                    "user_id": response.user_id, "username": username}
        finally:
            with self._lock:
                self._creating -= 1
            if not registered:
                client.close()

    def _get(self, token):
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                raise WebAccountError(401, "LOGIN_REQUIRED")
            if (self._clock() - session.last_activity >= self._timeout
                    or not session.client.is_authenticated or not session.client.is_connected):
                del self._sessions[token]
            else:
                session.last_activity = self._clock()
                return session
        session.client.close()
        raise WebAccountError(401, "SESSION_EXPIRED")

    def status(self, token):
        session = self._get(token)
        return {"status": "success", "connected": True, "authenticated": True,
                "user_id": session.client.user_id, "username": session.username}

    def users(self, token):
        from dataclasses import asdict
        session = self._get(token)
        return {"users": [asdict(user) for user in session.client.online_users()]}

    def logout(self, token):
        session = self._get(token)
        with self._lock:
            self._sessions.pop(token, None)
        try:
            session.client.logout()
        finally:
            session.client.close()
        return {"status": "success"}

    def expire(self):
        with self._lock:
            expired = [token for token, session in self._sessions.items()
                       if self._clock() - session.last_activity >= self._timeout
                       or not session.client.is_connected or not session.client.is_authenticated]
            clients = [self._sessions.pop(token).client for token in expired]
        for client in clients:
            client.close()

    def _reap_loop(self):
        while not self._stop.wait(0.2):
            self.expire()

    def close(self):
        with self._lock:
            self._closed = True
            self._stop.set()
            clients = [session.client for session in self._sessions.values()]
            self._sessions.clear()
        for client in clients:
            client.close()
        if threading.current_thread() is not self._worker:
            self._worker.join(timeout=2)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
