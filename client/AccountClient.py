"""Python port of AccountClient.java for the MMT protocol.

Place at client/account_client.py.
Uses ordinary TCP/UDP sockets, PacketIO/UdpPacketIO and the migrated payloads.
Not a StreapRous raw-socket client: a transport adapter is needed for that.
"""

from __future__ import annotations

import socket
import threading
from concurrent.futures import Future, InvalidStateError, ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from common.control_packets import ControlPackets
from common.json_payload_codec import JsonPayloadCodec
from common.message_type import MessageType
from common.packet import Packet
from common.packet_io import PacketIO
from common.udp_packet_io import UdpPacketIO
from common.payload.error_payload import ErrorPayload
from common.payload.heartbeat import Heartbeat
from common.payload.login_request import LoginRequest
from common.payload.login_response import LoginResponse
from common.payload.logout_request import LogoutRequest
from common.payload.presence_update import PresenceUpdate
from common.payload.signup_request import SignupRequest
from common.payload.signup_response import SignupResponse
from common.payload.user_info import UserInfo
from common.payload.user_list_request import UserListRequest
from common.payload.user_list_response import UserListResponse
from client.peer_endpoint import PeerEndpoint


@dataclass
class _LoginState:
    token: str
    user_id: int
    heartbeat_sequence: int = 0


def _message_type_value(value: int | str | Enum) -> int:
    """Accept message-type constants as int, IntEnum or decimal/hex string."""
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, str):
        return int(value, 0)
    if type(value) is int:
        return value
    raise TypeError(f"Unsupported message type: {value!r}")


def _control_type_string(value: int | str | Enum) -> str:
    """ControlPackets.create was ported from Java accepting a numeric string."""
    return f"0x{_message_type_value(value):02X}"


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

        self._pending_tcp: dict[int, Future[Packet]] = {}
        self._pending_udp: dict[int, Future[Packet]] = {}
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
            return response

    def logout(self) -> None:
        with self._request_lock:
            current = self._require_login()
            try:
                self._control(
                    MessageType.LOGOUT_REQUEST,
                    MessageType.LOGOUT_RESPONSE,
                    current.user_id,
                    LogoutRequest(current.token),
                )
            finally:
                with self._state_lock:
                    if self._login is current:
                        self._login = None

    def online_users(self) -> tuple[UserInfo, ...]:
        """Retrieve all discovery pages, retrying each lost UDP request 3 times."""
        with self._request_lock:
            current = self._require_login()
            users: list[UserInfo] = []
            seen_cursors: set[str] = set()
            cursor: str | None = None

            while True:
                request = ControlPackets.create(
                    _control_type_string(MessageType.USER_LIST_REQUEST),
                    self._next_sequence(),
                    current.user_id,
                    0,
                    UserListRequest(current.token, cursor),
                )
                response = self._request_udp(request)
                if response.header.messageType != _message_type_value(
                    MessageType.USER_LIST_RESPONSE
                ):
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

    def _control(
        self, message_type: int | str | Enum, expected_type: int | str | Enum,
        sender_id: int, body: object,
    ) -> Packet:
        request = ControlPackets.create(
            _control_type_string(message_type), self._next_sequence(), sender_id, 0, body
        )
        reference = request.header.sequenceNumber
        future: Future[Packet] = Future()
        with self._pending_lock:
            self._pending_tcp[reference] = future

        try:
            with self._state_lock:
                if self._closed:
                    raise OSError("Connection is closed; reconnect")
            with self._tcp_send_lock:
                PacketIO.writePacket(self._tcp, request)
            response = future.result(timeout=5.0)
        except (OSError, TimeoutError) as exc:
            # A failed/expired TCP control exchange makes this connection unusable.
            self.close()
            raise OSError("Control connection failed; reconnect") from exc
        finally:
            with self._pending_lock:
                self._pending_tcp.pop(reference, None)

        header = response.header
        if (
            header.senderID != 0
            or header.streamID != 0
            or header.sequenceNumber != reference
        ):
            raise OSError("Unmatched control response")
        self._check_error(response)
        if header.messageType != _message_type_value(expected_type):
            raise OSError("Unexpected response")
        return response

    def _receive_control_loop(self) -> None:
        try:
            while not self._stopped.is_set():
                response = PacketIO.readPacket(self._tcp)
                if response is None:
                    return
                header = response.header
                if header.senderID != 0 or header.streamID != 0 or header.flags != 0:
                    raise OSError("Invalid control response header")
                with self._pending_lock:
                    future = self._pending_tcp.get(header.sequenceNumber)
                if future is None:
                    raise OSError("Unexpected control response")
                try:
                    future.set_result(response)
                except InvalidStateError:
                    pass  # close() or another receiver already resolved the future
        except (OSError, EOFError, ValueError, TypeError):
            pass
        finally:
            # Detect server EOF even when the UI is idle.
            self.close()

    def _request_udp(self, request: Packet) -> Packet:
        reference = request.header.sequenceNumber
        future: Future[Packet] = Future()
        with self._pending_lock:
            self._pending_udp[reference] = future

        try:
            if not self.is_connected:
                raise OSError("Connection is closed; reconnect")
            for _ in range(3):
                UdpPacketIO.sendPacket(self._udp, self._server_udp, request)
                try:
                    response = future.result(timeout=1.0)
                except TimeoutError:
                    continue
                self._check_error(response)
                return response
            raise TimeoutError("Discovery timed out after 3 attempts")
        finally:
            with self._pending_lock:
                self._pending_udp.pop(reference, None)

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

            if header.messageType == _message_type_value(MessageType.PRESENCE_UPDATE):
                try:
                    update = JsonPayloadCodec.decode(packet.payload, PresenceUpdate)
                except (ValueError, TypeError, UnicodeError):
                    continue
                try:
                    self._callbacks.submit(self._notify_presence, current, update)
                except RuntimeError:  # callback executor has shut down
                    pass
            else:
                with self._pending_lock:
                    future = self._pending_udp.get(header.sequenceNumber)
                if future is not None:
                    try:
                        future.set_result(packet)
                    except InvalidStateError:
                        pass

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
                _control_type_string(MessageType.HEARTBEAT),
                self._next_sequence(),
                current.user_id,
                0,
                Heartbeat(current.token, count),
            )
            UdpPacketIO.sendPacket(self._udp, self._server_udp, request)
        except (OSError, ValueError):
            pass  # server enforces heartbeat deadline

    def _check_error(self, packet: Packet) -> None:
        if packet.header.messageType != _message_type_value(MessageType.ERROR):
            return
        error = JsonPayloadCodec.decode(packet.payload, ErrorPayload)
        # 1004 is UNAUTHENTICATED in the team's common/error_code.py registry.
        if error.error_code == 1004:
            with self._state_lock:
                self._login = None
        raise OSError(f"{error.error_code}: {error.error_message}")

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
            futures = list(self._pending_tcp.values()) + list(self._pending_udp.values())
            self._pending_tcp.clear()
            self._pending_udp.clear()
        for future in futures:
            try:
                future.set_exception(OSError("Client is closed"))
            except InvalidStateError:
                pass
        self._callbacks.shutdown(wait=False, cancel_futures=True)

    def __enter__(self) -> AccountClient:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
