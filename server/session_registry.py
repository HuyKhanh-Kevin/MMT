from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import secrets
import threading
import time

from common.payload.presence_update import PresenceUpdate
from common.payload.user_info import UserInfo
from server.account_exception import AccountException
from server.account_store import Account


@dataclass(frozen=True)
class Peer:
    user_id: int
    username: str
    ip: str
    tcp_port: int
    file_udp_port: int
    last_seen: datetime
    presence_endpoint: tuple[str, int] | None

    def user_info(self) -> UserInfo:
        return UserInfo(self.username, "online", self.user_id, self.ip,
                        self.tcp_port, self.file_udp_port)


@dataclass(frozen=True)
class CreatedSession:
    session_id: str
    peer: Peer


@dataclass
class _Session:
    token: str
    account: Account
    ip: str
    tcp_port: int
    file_udp_port: int
    connection: object
    last_heartbeat: float
    last_seen: datetime
    heartbeat_seq: int = 0
    endpoint: tuple[str, int] | None = None

    def peer(self) -> Peer:
        return Peer(self.account.user_id, self.account.username, self.ip,
                    self.tcp_port, self.file_udp_port, self.last_seen, self.endpoint)


class SessionRegistry:
    DEFAULT_TIMEOUT = 15.0

    def __init__(self, timeout: float = DEFAULT_TIMEOUT, clock=time.monotonic):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.timeout = timeout
        self._clock = clock
        self._lock = threading.RLock()
        self._sessions: dict[str, _Session] = {}
        self._changes = []
        self._disconnected = []
        self._expired_connections = set()

    def _expired(self, session: _Session) -> bool:
        return self._clock() - session.last_heartbeat >= self.timeout

    def _remove(self, session: _Session, close_control: bool = False) -> None:
        if self._sessions.pop(session.token, None) is None:
            return
        self._changes.append(PresenceUpdate(session.account.username, "offline"))
        if close_control:
            self._expired_connections.add(session.connection)
            self._disconnected.append(session.connection)

    def login(self, account: Account, ip: str, tcp_port: int, file_udp_port: int,
              connection) -> CreatedSession:
        for port in (tcp_port, file_udp_port):
            if type(port) is not int or not 1 <= port <= 65535:
                raise AccountException(1003, "INVALID_PORT")
        ip = str(ipaddress.ip_address(ip))
        with self._lock:
            self.expire()
            if connection in self._expired_connections:
                raise AccountException(1004, "SESSION_EXPIRED_RECONNECT")
            for session in self._sessions.values():
                if session.connection == connection:
                    raise AccountException(1003, "ALREADY_AUTHENTICATED")
                if session.account.user_id == account.user_id:
                    raise AccountException(1002, "ALREADY_ONLINE")
            token = secrets.token_urlsafe(32)
            while token in self._sessions:
                token = secrets.token_urlsafe(32)
            session = _Session(token, account, ip, tcp_port, file_udp_port, connection,
                               self._clock(), datetime.now(timezone.utc))
            self._sessions[token] = session
            self._changes.append(PresenceUpdate(account.username, "online"))
            return CreatedSession(token, session.peer())

    def has_session(self, connection) -> bool:
        with self._lock:
            for session in self._sessions.values():
                if session.connection == connection and not self._expired(session):
                    return True
            return False

    def _require(self, token: str, sender: int) -> _Session:
        session = self._sessions.get(token)
        if session is None:
            raise AccountException(1004, "UNAUTHENTICATED")
        if type(sender) is not int or session.account.user_id != sender:
            raise AccountException(1004, "UNAUTHENTICATED")
        if self._expired(session):
            raise AccountException(1004, "UNAUTHENTICATED")
        return session

    def authenticate_tcp(self, token: str, sender: int, connection) -> Peer:
        with self._lock:
            session = self._require(token, sender)
            if session.connection != connection:
                raise AccountException(1004, "UNAUTHENTICATED")
            return session.peer()

    def _udp_session(self, token: str, sender: int, source: tuple[str, int]) -> _Session:
        session = self._require(token, sender)
        if session.ip != source[0]:
            raise AccountException(1004, "UNAUTHENTICATED")
        if session.endpoint is not None:
            if session.endpoint != source:
                raise AccountException(1004, "UNAUTHENTICATED")
        return session

    def authenticate_udp(self, token: str, sender: int, source: tuple[str, int]) -> Peer:
        with self._lock:
            session = self._udp_session(token, sender, source)
            if session.endpoint is None:
                raise AccountException(1004, "HEARTBEAT_REQUIRED")
            return session.peer()

    def heartbeat(self, token: str, sender: int, sequence: int, source: tuple[str, int]) -> None:
        with self._lock:
            session = self._udp_session(token, sender, source)
            if type(sequence) is not int or not 1 <= sequence <= 0xFFFFFFFF:
                raise AccountException(1003, "INVALID_HEARTBEAT_SEQUENCE")
            if sequence <= session.heartbeat_seq:
                return
            session.endpoint = source
            session.heartbeat_seq = sequence
            session.last_heartbeat = self._clock()
            session.last_seen = datetime.now(timezone.utc)

    def discover(self, token: str, sender: int, source: tuple[str, int]) -> tuple[UserInfo, ...]:
        with self._lock:
            self.authenticate_udp(token, sender, source)
            users = []
            for peer in self.online_peers():
                users.append(peer.user_info())
            return tuple(users)

    def logout(self, token: str, sender: int, connection) -> None:
        with self._lock:
            self.authenticate_tcp(token, sender, connection)
            self._remove(self._sessions[token])

    def disconnect(self, connection) -> None:
        with self._lock:
            self._expired_connections.discard(connection)
            for session in self._sessions.values():
                if session.connection == connection:
                    self._remove(session)
                    break

    def expire(self) -> None:
        with self._lock:
            for session in tuple(self._sessions.values()):
                if self._expired(session):
                    self._remove(session, close_control=True)

    def online_peers(self) -> tuple[Peer, ...]:
        with self._lock:
            peers_by_id = {}
            for session in self._sessions.values():
                if not self._expired(session):
                    peers_by_id[session.account.user_id] = session.peer()

            peers = []
            for user_id in sorted(peers_by_id):
                peers.append(peers_by_id[user_id])
            return tuple(peers)

    def find_online_user(self, user_id: int) -> Peer | None:
        with self._lock:
            for session in self._sessions.values():
                if session.account.user_id == user_id and not self._expired(session):
                    return session.peer()
            return None

    def active_tokens(self) -> frozenset[str]:
        with self._lock:
            tokens = []
            for session in self._sessions.values():
                if not self._expired(session):
                    tokens.append(session.token)
            return frozenset(tokens)

    def drain_changes(self) -> tuple[PresenceUpdate, ...]:
        with self._lock:
            changes = tuple(self._changes)
            self._changes.clear()
            return changes

    def drain_disconnected_connections(self) -> tuple:
        with self._lock:
            connections = tuple(self._disconnected)
            self._disconnected.clear()
            return connections
