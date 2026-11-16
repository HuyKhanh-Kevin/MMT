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
        self.host = host
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.peer_tcp_port = peer_tcp_port
        self.file_udp_port = file_udp_port
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
            return AccountClient(self.host, self.tcp_port, self.udp_port,
                                 self.peer_tcp_port, self.file_udp_port)
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
        session = self._get(token)
        users = []
        for user in session.client.online_users():
            users.append({
                "username": user.username,
                "status": user.status,
                "user_id": user.user_id,
                "ip": user.ip,
                "tcp_port": user.tcp_port,
                "file_udp_port": user.file_udp_port,
            })
        return {"users": users}

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
            clients = []
            for token, session in list(self._sessions.items()):
                timed_out = self._clock() - session.last_activity >= self._timeout
                disconnected = not session.client.is_connected
                logged_out = not session.client.is_authenticated
                if timed_out or disconnected or logged_out:
                    clients.append(session.client)
                    del self._sessions[token]
        for client in clients:
            client.close()

    def _reap_loop(self):
        while not self._stop.wait(0.2):
            self.expire()

    def close(self):
        with self._lock:
            self._closed = True
            self._stop.set()
            clients = []
            for session in self._sessions.values():
                clients.append(session.client)
            self._sessions.clear()
        for client in clients:
            client.close()
        if threading.current_thread() is not self._worker:
            self._worker.join(timeout=2)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
