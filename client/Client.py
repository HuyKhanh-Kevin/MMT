"""Python conversion of the Java Client for the MMT project.

Place at client/client.py. Uses standard TCP/UDP sockets; replace the TCP
transport with a StreapRous adapter if your project requires its raw TCP API.
"""

import itertools
import socket
import threading
from enum import Enum

from common.packet import Packet
from common.packet_header import PacketHeader
from common.packet_io import PacketIO
from common.udp_packet_io import UdpPacketIO
from common.json_payload_codec import JsonPayloadCodec
from common.protocol_constants import ProtocolConstants
from common.message_type import MessageType

from common.payload.signup_request import SignupRequest
from common.payload.signup_response import SignupResponse
from common.payload.login_request import LoginRequest
from common.payload.login_response import LoginResponse
from common.payload.logout_request import LogoutRequest
from common.payload.logout_response import LogoutResponse
from common.payload.user_list_request import UserListRequest
from common.payload.user_list_response import UserListResponse
from common.payload.chat_message import ChatMessage
from common.payload.error_payload import ErrorPayload
from common.payload.heartbeat import Heartbeat


class Client:
    def __init__(
        self,
        server_ip: str,
        server_port: int,
        udp_port: int,
        peer_tcp_port: int,
        file_udp_port: int,
    ):
        self.id = 0
        self.session_id: str | None = None
        self.authenticated = False
        self.listener = None

        self.peer_tcp_port = peer_tcp_port
        self.file_udp_port = file_udp_port
        self._stop_event = threading.Event()
        self._counter_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._tcp_send_lock = threading.Lock()

        self._outgoing_streams: dict[int, int] = {}
        self._stream_ids = itertools.count(1)
        self._tcp_sequences = itertools.count(1)
        self._udp_sequences = itertools.count(1)
        self._heartbeat_sequences = itertools.count(1)
        self._heartbeat_thread: threading.Thread | None = None
        self._tcp_thread: threading.Thread | None = None
        self._udp_thread: threading.Thread | None = None

        self._tcp_socket = socket.create_connection((server_ip, server_port))
        try:
            self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_socket.bind(("0.0.0.0", 0))
            self._udp_socket.settimeout(1.0)
            self._server_udp_address = (socket.gethostbyname(server_ip), udp_port)
        except Exception:
            self._tcp_socket.close()
            raise

    @staticmethod
    def _type_value(message_type) -> int:
        """Support integer, integer-valued Enum, or numeric string constants."""
        value = message_type.value if isinstance(message_type, Enum) else message_type
        if isinstance(value, str):
            return int(value, 16) if value.lower().startswith("0x") else int(value)
        return int(value)

    @property
    def running(self) -> bool:
        return not self._stop_event.is_set()

    def set_listener(self, listener) -> None:
        self.listener = listener

    def _notify(self, method: str, *args) -> None:
        if self.listener is not None:
            getattr(self.listener, method)(*args)

    def _next_counter(self, counter) -> int:
        with self._counter_lock:
            value = next(counter)
        if value > 0xFFFFFFFF:
            raise OverflowError("32-bit sequence/stream counter exhausted")
        return value

    def _outgoing_stream_id(self, receiver_id: int) -> int:
        with self._counter_lock:
            if receiver_id not in self._outgoing_streams:
                value = next(self._stream_ids)
                if value > 0xFFFFFFFF:
                    raise OverflowError("32-bit stream IDs exhausted")
                self._outgoing_streams[receiver_id] = value
            return self._outgoing_streams[receiver_id]

    def start_receiving(self) -> None:
        if self._tcp_thread is not None or not self.running:
            return
        self._tcp_thread = threading.Thread(
            target=self._receive_tcp_loop, name="tcp-receiver", daemon=True
        )
        self._udp_thread = threading.Thread(
            target=self._receive_udp_loop, name="udp-receiver", daemon=True
        )
        self._tcp_thread.start()
        self._udp_thread.start()

    def close_connection(self) -> None:
        with self._close_lock:
            if self._stop_event.is_set():
                return
            self._stop_event.set()
            self.authenticated = False
            self.session_id = None

            try:
                self._tcp_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._tcp_socket.close()
            self._udp_socket.close()

    def _receive_tcp_loop(self) -> None:
        try:
            while self.running:
                packet = PacketIO.readPacket(self._tcp_socket)
                if packet is None:
                    break
                self._handle_tcp_packet(packet)
        except (OSError, EOFError, ValueError, TypeError) as exc:
            if self.running:
                print(f"TCP receive error: {exc}")
        finally:
            self.close_connection()

    def _handle_tcp_packet(self, packet: Packet) -> None:
        message_type = packet.header.messageType
        payload = packet.payload

        if message_type == self._type_value(MessageType.SIGNUP_RESPONSE):
            response = JsonPayloadCodec.decode(payload, SignupResponse)
            self._notify("display_signup_response", response.status, response.reason)

        elif message_type == self._type_value(MessageType.LOGIN_RESPONSE):
            response = JsonPayloadCodec.decode(payload, LoginResponse)
            if response.status == "success":
                if response.user_id is None or response.session_id is None:
                    raise ValueError("Successful login response missing user_id/session_id")
                self.id = response.user_id
                self.session_id = response.session_id
                self.authenticated = True
                self._start_heartbeat()
            self._notify("display_login_response", response.status, response.reason)

        elif message_type == self._type_value(MessageType.LOGOUT_RESPONSE):
            response = JsonPayloadCodec.decode(payload, LogoutResponse)
            if response.status == "success":
                self.close_connection()
                self._notify("display_logout_response")

        elif message_type == self._type_value(MessageType.CHAT_MESSAGE):
            message = JsonPayloadCodec.decode(payload, ChatMessage)
            self._notify("display_message", packet.header.senderID, message.text)

        elif message_type == self._type_value(MessageType.ERROR):
            error = JsonPayloadCodec.decode(payload, ErrorPayload)
            self._notify("display_error", error.error_code, error.error_message)

    def _receive_udp_loop(self) -> None:
        while self.running:
            try:
                received = UdpPacketIO.receivePacket(self._udp_socket)
                if received.source != self._server_udp_address:
                    continue

                packet = received.packet
                message_type = packet.header.messageType
                if message_type == self._type_value(MessageType.USER_LIST_RESPONSE):
                    response = JsonPayloadCodec.decode(
                        packet.payload, UserListResponse
                    )
                    self._notify("display_user_list", response.users)
                elif message_type == self._type_value(MessageType.ERROR):
                    error = JsonPayloadCodec.decode(packet.payload, ErrorPayload)
                    self._notify("display_error", error.error_code, error.error_message)

            except socket.timeout:
                continue
            except (OSError, ValueError, TypeError) as exc:
                if self.running:
                    print(f"UDP receive error: {exc}")
                if self._udp_socket.fileno() == -1:
                    break

    def send_tcp_packet(self, packet: Packet) -> None:
        with self._tcp_send_lock:
            PacketIO.writePacket(self._tcp_socket, packet)

    def send_udp_packet(self, packet: Packet) -> None:
        UdpPacketIO.sendPacket(self._udp_socket, self._server_udp_address, packet)

    def _start_heartbeat(self) -> None:
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            return

        def heartbeat_loop():
            while not self._stop_event.wait(5.0):
                if not self.authenticated:
                    continue
                try:
                    self.send_udp_packet(self.create_heartbeat_packet())
                except (OSError, ValueError) as exc:
                    if self.running:
                        print(f"Heartbeat error: {exc}")

        self._heartbeat_thread = threading.Thread(
            target=heartbeat_loop, name="heartbeat", daemon=True
        )
        self._heartbeat_thread.start()

    def _build_json_packet(
        self,
        message_type,
        value,
        *,
        sender_id: int = 0,
        receiver_id: int = 0,
        stream_id: int = 0,
        udp: bool = False,
    ) -> Packet:
        payload = JsonPayloadCodec.encode(value)
        counter = self._udp_sequences if udp else self._tcp_sequences
        sequence = self._next_counter(counter)
        header = PacketHeader(
            ProtocolConstants.VERSION,
            self._type_value(message_type),
            0,  # flags
            stream_id,
            sequence,
            len(payload),
            sender_id,
            receiver_id,
        )
        return Packet(header, payload)

    def _require_login(self, action: str) -> None:
        if not self.authenticated or self.session_id is None:
            raise RuntimeError(f"You must log in before {action}")

    def create_signup_packet(self, username: str, password: str) -> Packet:
        return self._build_json_packet(
            MessageType.SIGNUP_REQUEST, SignupRequest(username, password)
        )

    def create_login_packet(self, username: str, password: str) -> Packet:
        if self.authenticated:
            raise RuntimeError("You are already logged in")
        return self._build_json_packet(
            MessageType.LOGIN_REQUEST,
            LoginRequest(username, password, self.peer_tcp_port, self.file_udp_port),
        )

    def create_logout_packet(self) -> Packet:
        self._require_login("logging out")
        return self._build_json_packet(
            MessageType.LOGOUT_REQUEST,
            LogoutRequest(self.session_id),
            sender_id=self.id,
        )

    def create_online_users_list_packet(self) -> Packet:
        self._require_login("requesting online users")
        return self._build_json_packet(
            MessageType.USER_LIST_REQUEST,
            UserListRequest(self.session_id),
            sender_id=self.id,
            udp=True,
        )

    def create_private_chat_packet(self, receiver_id: int, text: str) -> Packet:
        self._require_login("sending private messages")
        return self._build_json_packet(
            MessageType.CHAT_MESSAGE,
            ChatMessage(text),
            sender_id=self.id,
            receiver_id=receiver_id,
            stream_id=self._outgoing_stream_id(receiver_id),
        )

    def create_global_chat_packet(self, text: str) -> Packet:
        self._require_login("sending global messages")
        return self._build_json_packet(
            MessageType.CHAT_MESSAGE,
            ChatMessage(text),
            sender_id=self.id,
            receiver_id=0,
            stream_id=self._outgoing_stream_id(0),
        )

    def create_heartbeat_packet(self) -> Packet:
        self._require_login("sending a heartbeat")
        heartbeat_sequence = self._next_counter(self._heartbeat_sequences)
        return self._build_json_packet(
            MessageType.HEARTBEAT,
            Heartbeat(self.session_id, heartbeat_sequence),
            sender_id=self.id,
            udp=True,
        )

    def exit_program(self) -> None:
        self.close_connection()
