"""Account API using the project's TCP/UDP packet protocol and shared payloads."""

from __future__ import annotations

import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty, Full
from dataclasses import dataclass
from typing import Callable

from common.ControlPackets import ControlPackets
from common.JsonPayloadCodec import JsonPayloadCodec
from common.MessageType import MessageType
from common.Packet import Packet
from common.PacketIO import PacketIO
from common.UdpPacketIO import UdpPacketIO
from common.payload.ErrorPayload import ErrorPayload
from common.payload.Heartbeat import Heartbeat
from common.payload.LoginRequest import LoginRequest
from common.payload.LoginResponse import LoginResponse
from common.payload.LogoutRequest import LogoutRequest
from common.payload.LogoutResponse import LogoutResponse
from common.payload.PresenceUpdate import PresenceUpdate
from common.payload.SignupRequest import SignupRequest
from common.payload.SignupResponse import SignupResponse
from common.payload.UserInfo import UserInfo
from common.payload.UserListRequest import UserListRequest
from common.payload.UserListResponse import UserListResponse
from client.PeerEndpoint import PeerEndpoint


@dataclass
class _LoginState:
    token: str
    user_id: int
    heartbeat_sequence: int = 0


class AccountRequestError(OSError):
    """A structured tracker rejection, distinct from a transport failure."""

    def __init__(self, code: int, reason: str):
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


class AccountClient:
    """Account/session/discovery client with concurrent TCP/UDP readers."""

    def __init__(
        self,
        host: str,
        server_tcp_port: int,
        server_udp_port: int,
        peer_tcp_port: int,
        file_udp_port: int,
    ) -> None:
        for name, port in (
            ("server_tcp_port", server_tcp_port),
            ("server_udp_port", server_udp_port),
            ("peer_tcp_port", peer_tcp_port),
            ("file_udp_port", file_udp_port),
        ):
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError(f"Invalid {name}")

        self.peer_tcp_port = peer_tcp_port
        self.file_udp_port = file_udp_port

        self._state_lock = threading.RLock()
        self._request_lock = threading.RLock()
        self._pending_lock = threading.Lock()
        self._sequence_lock = threading.Lock()
        self._tcp_send_lock = threading.Lock()
        self._stopped = threading.Event()

        self._sequence = 0
        self._login: _LoginState | None = None
        self._closed = False
        self._heartbeats_enabled = True
        self._presence_listener: Callable[[PresenceUpdate], None] = lambda _: None
        self._users_listener = None
        self._refresh_users = threading.Event()

        # _request_lock allows one account request at a time. Readers deliver
        # its reply through a queue; heartbeat/presence do not wait for replies.
        self._pending = None
        self._users_thread = None
        self._callbacks = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="account-presence"
        )

        # TCP is connection-oriented and blocking; only the background reader calls recv().
        try:
            self._tcp = socket.create_connection((host, server_tcp_port), timeout=3.0)
            self._tcp.settimeout(None)
            self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp.bind(("0.0.0.0", 0))
            self._udp.settimeout(0.5)  # allows receiver to observe close()
            # Use the TCP peer address, so hostname resolution remains consistent.
            self._server_udp = (self._tcp.getpeername()[0], server_udp_port)
        except Exception:
            if hasattr(self, "_tcp"):
                self._tcp.close()
            if hasattr(self, "_udp"):
                self._udp.close()
            self._callbacks.shutdown(wait=False, cancel_futures=True)
            raise

        self._tcp_reader = threading.Thread(
            target=self._receive_control_loop, name="account-tcp-reader", daemon=True
        )
        self._udp_reader = threading.Thread(
            target=self._receive_udp_loop, name="account-udp-reader", daemon=True
        )
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, name="account-heartbeat", daemon=True
        )
        self._tcp_reader.start()
        self._udp_reader.start()
        self._heartbeat_thread.start()

    @property
    def is_authenticated(self) -> bool:
        with self._state_lock:
            return self._login is not None

    @property
    def is_connected(self) -> bool:
        with self._state_lock:
            return not self._closed

    @property
    def user_id(self) -> int:
        with self._state_lock:
            return self._login.user_id if self._login is not None else 0

    @property
    def session_id(self) -> str | None:
        with self._state_lock:
            return self._login.token if self._login is not None else None

    def on_presence(self, listener: Callable[[PresenceUpdate], None]) -> None:
        if not callable(listener):
            raise TypeError("Presence listener must be callable")
        with self._state_lock:
            self._presence_listener = listener

    def on_users(self, listener: Callable[[tuple[UserInfo, ...]], None]) -> None:
        """Publish complete snapshots on presence and every 5s to repair UDP loss."""
        if not callable(listener):
            raise TypeError("User-list listener must be callable")
        with self._state_lock:
            if self._closed:
                raise OSError("Client is closed")
            self._users_listener = listener
            if self._users_thread is None:
                self._users_thread = threading.Thread(
                    target=self._users_loop, name="account-users", daemon=True
                )
                self._users_thread.start()
        self._refresh_users.set()

    def signup(self, username: str, password: str) -> SignupResponse:
        with self._request_lock:
            self._require_logged_out()
            packet = self._control(
                MessageType.SIGNUP_REQUEST,
                MessageType.SIGNUP_RESPONSE,
                0,
                SignupRequest(username, password),
            )
            return JsonPayloadCodec.decode(packet.payload, SignupResponse)

    def login(self, username: str, password: str) -> LoginResponse:
        with self._request_lock:
            self._require_logged_out()
            packet = self._control(
                MessageType.LOGIN_REQUEST,
                MessageType.LOGIN_RESPONSE,
                0,
                LoginRequest(username, password, self.peer_tcp_port, self.file_udp_port),
            )
            response = JsonPayloadCodec.decode(packet.payload, LoginResponse)
            if response.status == "success":
                if response.session_id is None or response.user_id is None:
                    raise OSError("Incomplete login response")
                with self._state_lock:
                    if self._closed:
                        raise OSError("Server closed the connection; reconnect")
                    self._login = _LoginState(response.session_id, response.user_id)
                # Register the UDP source port immediately, just as the Java client does.
                self._send_heartbeat()
                self._refresh_users.set()
            return response

    def logout(self) -> None:
        with self._request_lock:
            current = self._require_login()
            try:
                response = self._control(
                    MessageType.LOGOUT_REQUEST,
                    MessageType.LOGOUT_RESPONSE,
                    current.user_id,
                    LogoutRequest(current.token),
                )
                JsonPayloadCodec.decode(response.payload, LogoutResponse)
            finally:
                with self._state_lock:
                    if self._login is current:
                        self._login = None
                self._refresh_users.set()

    def online_users(self) -> tuple[UserInfo, ...]:
        """Retrieve all discovery pages, retrying each lost UDP request 3 times."""
        # An expired/evicted cursor invalidates the entire snapshot. Never append
        # a new first page to an old partial result; restart once, then surface it.
        for attempt in range(2):
            try:
                return self._online_users_snapshot()
            except AccountRequestError as exc:
                if attempt or exc.code != 1003 or exc.reason != "INVALID_CURSOR":
                    raise

    def _online_users_snapshot(self) -> tuple[UserInfo, ...]:
        with self._request_lock:
            current = self._require_login()
            users: list[UserInfo] = []
            seen_cursors: set[str] = set()
            cursor: str | None = None

            while True:
                request = ControlPackets.create(
                    str(MessageType.USER_LIST_REQUEST),
                    self._next_sequence(),
                    current.user_id,
                    0,
                    UserListRequest(current.token, cursor),
                )
                response = self._request_udp(request)
                if response.header.messageType != MessageType.USER_LIST_RESPONSE:
                    raise OSError("Unexpected discovery response")

                page = JsonPayloadCodec.decode(response.payload, UserListResponse)
                users.extend(page.users)
                cursor = page.next_cursor
                if cursor is None:
                    break
                if cursor in seen_cursors:
                    raise OSError("Repeated discovery cursor")
                seen_cursors.add(cursor)

            return tuple(users)

    def peer_endpoint(self, user_id: int) -> PeerEndpoint:
        """Resolve a peer's addresses from a freshly fetched user list."""
        if type(user_id) is not int or not 1 <= user_id <= 0xFFFFFFFF:
            raise ValueError("Invalid user ID")
        user = next((u for u in self.online_users() if u.user_id == user_id), None)
        if user is None:
            raise OSError("2001: RECIPIENT_OFFLINE")
        address = socket.gethostbyname(user.ip)
        return PeerEndpoint(
            user_id=user.user_id,
            username=user.username,
            tcp=(address, user.tcp_port),
            file_udp=(address, user.file_udp_port),
        )

    def set_heartbeats_enabled(self, enabled: bool) -> None:
        if type(enabled) is not bool:
            raise TypeError("enabled must be a boolean")
        with self._state_lock:
            self._heartbeats_enabled = enabled

    def _begin_request(self, transport, reference):
        with self._pending_lock:
            if self._stopped.is_set():
                raise OSError("Client is closed")
            replies = Queue(maxsize=1)
            self._pending = (transport, reference, replies)
            return replies

    @staticmethod
    def _put_reply(replies, value):
        try:
            replies.put_nowait(value)
        except Full:
            pass  # Ignore duplicate replies or a close after the reply arrived.

    def _deliver_reply(self, transport, packet):
        with self._pending_lock:
            if self._pending is None:
                return False
            expected_transport, reference, replies = self._pending
            if transport != expected_transport or packet.header.sequenceNumber != reference:
                return False
            self._put_reply(replies, packet)
            return True

    @staticmethod
    def _wait_reply(replies, timeout):
        try:
            reply = replies.get(timeout=timeout)
        except Empty:
            raise TimeoutError("No reply before timeout") from None
        if isinstance(reply, OSError):
            raise reply
        return reply

    def _control(
        self, message_type: int, expected_type: int,
        sender_id: int, body: object,
    ) -> Packet:
        request = ControlPackets.create(
            str(message_type), self._next_sequence(), sender_id, 0, body
        )
        reference = request.header.sequenceNumber
        replies = self._begin_request("tcp", reference)

        try:
            with self._state_lock:
                if self._closed:
                    raise OSError("Connection is closed; reconnect")
            with self._tcp_send_lock:
                PacketIO.writePacket(self._tcp, request)
            response = self._wait_reply(replies, 5.0)
        except (OSError, TimeoutError) as exc:
            # A failed/expired TCP control exchange makes this connection unusable.
            self.close()
            raise OSError("Control connection failed; reconnect") from exc
        finally:
            with self._pending_lock:
                self._pending = None

        header = response.header
        if (
            header.senderID != 0
            or header.streamID != 0
            or header.sequenceNumber != reference
        ):
            raise OSError("Unmatched control response")
        if header.messageType == MessageType.ERROR:
            if header.receiverID != sender_id:
                raise OSError("Wrong control response recipient")
            self._check_error(response)
        if header.messageType != expected_type:
            raise OSError("Unexpected response")
        if header.messageType == MessageType.LOGIN_RESPONSE:
            login = JsonPayloadCodec.decode(response.payload, LoginResponse)
            expected_receiver = login.user_id or 0
        else:
            expected_receiver = sender_id
        if header.receiverID != expected_receiver:
            raise OSError("Wrong control response recipient")
        return response

    def _receive_control_loop(self) -> None:
        try:
            while not self._stopped.is_set():
                response = PacketIO.readPacket(self._tcp)
                if response is None:
                    return
                header = response.header
                if self._handle_application_packet(response):
                    continue
                if header.senderID != 0 or header.streamID != 0 or header.flags != 0:
                    raise OSError("Invalid control response header")
                if not self._deliver_reply("tcp", response):
                    raise OSError("Unexpected control response")
        except (OSError, EOFError, ValueError, TypeError):
            pass
        finally:
            # Detect server EOF even when the UI is idle.
            self.close()

    def _handle_application_packet(self, packet: Packet) -> bool:
        """Extension point for the main client; account replies stay correlated here."""
        return False

    def _request_udp(self, request: Packet) -> Packet:
        reference = request.header.sequenceNumber
        replies = self._begin_request("udp", reference)

        try:
            if not self.is_connected:
                raise OSError("Connection is closed; reconnect")
            for _ in range(3):
                # Re-establish registration if the initial UDP heartbeat was lost.
                # Discovery itself never refreshes the server's session deadline.
                self._send_heartbeat()
                UdpPacketIO.sendPacket(self._udp, self._server_udp, request)
                try:
                    response = self._wait_reply(replies, 1.0)
                except TimeoutError:
                    continue
                if response.header.messageType == MessageType.ERROR:
                    error = JsonPayloadCodec.decode(response.payload, ErrorPayload)
                    if error.error_message == "HEARTBEAT_REQUIRED":
                        replies = self._begin_request("udp", reference)
                        continue
                self._check_error(response)
                return response
            raise TimeoutError("Discovery timed out after 3 attempts")
        finally:
            with self._pending_lock:
                self._pending = None

    def _receive_udp_loop(self) -> None:
        while not self._stopped.is_set():
            try:
                received = UdpPacketIO.receivePacket(self._udp)
            except socket.timeout:
                continue
            except (OSError, ValueError, TypeError):
                if self._stopped.is_set():
                    return
                continue  # ignore an invalid datagram; TCP remains alive

            if received.source != self._server_udp:
                continue
            packet = received.packet
            header = packet.header
            with self._state_lock:
                current = self._login
            if (
                current is None
                or header.senderID != 0
                or header.receiverID != current.user_id
                or header.streamID != 0
                or header.flags != 0
            ):
                continue

            if header.messageType == MessageType.PRESENCE_UPDATE:
                try:
                    update = JsonPayloadCodec.decode(packet.payload, PresenceUpdate)
                except (ValueError, TypeError, UnicodeError, RecursionError):
                    continue
                self._refresh_users.set()
                try:
                    self._callbacks.submit(self._notify_presence, current, update)
                except RuntimeError:  # callback executor has shut down
                    pass
            else:
                self._deliver_reply("udp", packet)

    def _notify_presence(self, current: _LoginState, update: PresenceUpdate) -> None:
        with self._state_lock:
            if self._closed or self._login is not current:
                return
            listener = self._presence_listener
        try:
            listener(update)
        except Exception:
            pass  # a UI callback exception must not stop receiving packets

    def _heartbeat_loop(self) -> None:
        while not self._stopped.wait(5.0):
            self._send_heartbeat()

    def _users_loop(self) -> None:
        while not self._stopped.is_set():
            self._refresh_users.wait(5.0)
            self._refresh_users.clear()
            with self._state_lock:
                current = self._login
                listener = self._users_listener
            if self._stopped.is_set():
                return
            if listener is None:
                continue
            try:
                users = self.online_users() if current else ()
                self._callbacks.submit(self._notify_users, current, users)
            except (OSError, ValueError, RuntimeError):
                continue  # Next refresh retries; a transient UDP loss is not logout.

    def _notify_users(self, current, users) -> None:
        with self._state_lock:
            if self._closed or self._login is not current:
                return
            listener = self._users_listener
        try:
            if listener is not None:
                listener(users)
        except Exception:
            pass

    def _send_heartbeat(self) -> None:
        with self._state_lock:
            current = self._login
            if self._closed or current is None or not self._heartbeats_enabled:
                return
            current.heartbeat_sequence += 1
            count = current.heartbeat_sequence
        if count > 0xFFFFFFFF:
            return  # session renewal required
        try:
            request = ControlPackets.create(
                str(MessageType.HEARTBEAT),
                self._next_sequence(),
                current.user_id,
                0,
                Heartbeat(current.token, count),
            )
            UdpPacketIO.sendPacket(self._udp, self._server_udp, request)
        except (OSError, ValueError):
            pass  # server enforces heartbeat deadline

    def _check_error(self, packet: Packet) -> None:
        if packet.header.messageType != MessageType.ERROR:
            return
        error = JsonPayloadCodec.decode(packet.payload, ErrorPayload)
        # 1004 is UNAUTHENTICATED in the team's common/error_code.py registry.
        if error.error_code == 1004:
            with self._state_lock:
                self._login = None
        raise AccountRequestError(error.error_code, error.error_message)

    def _next_sequence(self) -> int:
        with self._sequence_lock:
            if self._sequence >= 0xFFFFFFFF:
                raise RuntimeError("Packet reference space exhausted; reconnect")
            self._sequence += 1
            return self._sequence

    def _require_login(self) -> _LoginState:
        with self._state_lock:
            if self._closed:
                raise OSError("Client is closed")
            if self._login is None:
                raise OSError("Login required")
            return self._login

    def _require_logged_out(self) -> None:
        with self._state_lock:
            if self._closed:
                raise OSError("Client is closed")
            if self._login is not None:
                raise OSError("Already logged in")

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            self._login = None
            self._stopped.set()
            self._refresh_users.set()

        for sock in (self._tcp, self._udp):
            try:
                if sock is self._tcp:
                    sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

        with self._pending_lock:
            if self._pending is not None:
                self._put_reply(self._pending[2], OSError("Client is closed"))
        try:
            self._callbacks.submit(self._notify_closed_users)
        except RuntimeError:
            pass
        self._callbacks.shutdown(wait=False)

    def _notify_closed_users(self):
        # Older queued snapshots self-discard after close; the final empty list
        # tells a UI to remove stale online users when the tracker disappears.
        listener = self._users_listener
        try:
            if listener is not None:
                listener(())
        except Exception:
            pass

    def __enter__(self) -> AccountClient:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
