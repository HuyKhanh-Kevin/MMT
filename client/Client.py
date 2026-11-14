"""Main-client compatibility API backed by one Python AccountClient session.

Account operations may be called directly or through the existing create/send
methods. Account sends now wait for their correlated reply. Chat packet builders
remain available; the application's chat router is a separate module.
"""

import itertools
import threading

from client.AccountClient import AccountClient
from common.ControlPackets import ControlPackets
from common.JsonPayloadCodec import JsonPayloadCodec
from common.MessageType import MessageType
from common.PacketIO import PacketIO
from common.Packet import Packet
from common.PacketHeader import PacketHeader
from common.ProtocolConstants import ProtocolConstants
from common.payload.ChatMessage import ChatMessage
from common.payload.ErrorPayload import ErrorPayload
from common.payload.Heartbeat import Heartbeat
from common.payload.LoginRequest import LoginRequest
from common.payload.LogoutRequest import LogoutRequest
from common.payload.SignupRequest import SignupRequest
from common.payload.UserListRequest import UserListRequest


class Client(AccountClient):
    def __init__(self, server_ip, server_port, udp_port, peer_tcp_port, file_udp_port):
        self.listener = None
        self._stream_lock = threading.Lock()
        self._outgoing_streams = {}
        self._stream_ids = itertools.count(1)
        super().__init__(server_ip, server_port, udp_port, peer_tcp_port, file_udp_port)
        self.on_presence(lambda update: self._notify("display_presence", update))

    @property
    def id(self):
        return self.user_id

    @property
    def authenticated(self):
        return self.is_authenticated

    @property
    def running(self):
        return self.is_connected

    def set_listener(self, listener):
        self.listener = listener
        self.on_users(lambda users: self._notify("display_user_list", list(users)))

    def _notify(self, method, *args):
        callback = getattr(self.listener, method, None)
        if callable(callback):
            try:
                callback(*args)
            except Exception:
                pass  # A UI exception must not tear down the account connection.

    def start_receiving(self):
        """Readers already start in AccountClient; never create a second reader."""

    def close_connection(self):
        self.close()

    def exit_program(self):
        self.close()

    def signup(self, username, password):
        response = super().signup(username, password)
        self._notify("display_signup_response", response.status, response.reason)
        return response

    def login(self, username, password):
        response = super().login(username, password)
        self._notify("display_login_response", response.status, response.reason)
        return response

    def logout(self):
        super().logout()
        self._notify("display_logout_response")

    def _account_packet(self, kind, body, sender=0):
        return ControlPackets.create(str(kind), self._next_sequence(), sender, 0, body)

    def create_signup_packet(self, username, password):
        self._require_logged_out()
        return self._account_packet(MessageType.SIGNUP_REQUEST, SignupRequest(username, password))

    def create_login_packet(self, username, password):
        self._require_logged_out()
        return self._account_packet(MessageType.LOGIN_REQUEST, LoginRequest(
            username, password, self.peer_tcp_port, self.file_udp_port))

    def create_logout_packet(self):
        current = self._require_login()
        return self._account_packet(MessageType.LOGOUT_REQUEST,
                                    LogoutRequest(current.token), current.user_id)

    def create_online_users_list_packet(self):
        current = self._require_login()
        return self._account_packet(MessageType.USER_LIST_REQUEST,
                                    UserListRequest(current.token, None), current.user_id)

    def create_heartbeat_packet(self):
        with self._state_lock:
            current = self._require_login()
            if current.heartbeat_sequence >= 0xFFFFFFFF:
                raise RuntimeError("Heartbeat sequence exhausted; reconnect")
            current.heartbeat_sequence += 1
            return self._account_packet(MessageType.HEARTBEAT,
                                        Heartbeat(current.token, current.heartbeat_sequence),
                                        current.user_id)

    def _validate_account_packet(self, packet, expected_sender):
        h = packet.header
        if h.flags or h.streamID or h.receiverID or h.senderID != expected_sender:
            raise ValueError("Invalid account request header")

    def _validate_session_body(self, packet, cls):
        current = self._require_login()
        self._validate_account_packet(packet, current.user_id)
        body = JsonPayloadCodec.decode(packet.payload, cls)
        if body.session_id != current.token:
            raise ValueError("Stale account request; create a new packet after login")
        return body

    def send_tcp_packet(self, packet):
        kind = packet.header.messageType
        with self._request_lock:
            if kind == MessageType.SIGNUP_REQUEST:
                self._validate_account_packet(packet, 0)
                body = JsonPayloadCodec.decode(packet.payload, SignupRequest)
                return self.signup(body.username, body.password)
            if kind == MessageType.LOGIN_REQUEST:
                self._validate_account_packet(packet, 0)
                body = JsonPayloadCodec.decode(packet.payload, LoginRequest)
                if (body.tcp_port, body.file_udp_port) != (self.peer_tcp_port, self.file_udp_port):
                    raise ValueError("Login ports must match this client's listening ports")
                return self.login(body.username, body.password)
            if kind == MessageType.LOGOUT_REQUEST:
                self._validate_session_body(packet, LogoutRequest)
                return self.logout()
            # Preserve the existing chat send API on the same authenticated TCP.
            current = self._require_login()
            if kind != MessageType.CHAT_MESSAGE or packet.header.senderID != current.user_id:
                raise ValueError("Unsupported TCP request")
            with self._tcp_send_lock:
                PacketIO.writePacket(self._tcp, packet)

    def send_udp_packet(self, packet):
        with self._request_lock:
            if packet.header.messageType == MessageType.USER_LIST_REQUEST:
                self._validate_session_body(packet, UserListRequest)
                users = self.online_users()
                self._notify("display_user_list", list(users))
                return users
            if packet.header.messageType == MessageType.HEARTBEAT:
                self._validate_session_body(packet, Heartbeat)
                # Use the single heartbeat scheduler/counter, including pause().
                self._send_heartbeat()
                return None
            raise ValueError("Unsupported account UDP request")

    def _outgoing_stream_id(self, receiver_id):
        with self._stream_lock:
            if receiver_id not in self._outgoing_streams:
                value = next(self._stream_ids)
                if value > 0xFFFFFFFF:
                    raise OverflowError("Stream IDs exhausted")
                self._outgoing_streams[receiver_id] = value
            return self._outgoing_streams[receiver_id]

    def create_private_chat_packet(self, receiver_id, text):
        current = self._require_login()
        payload = JsonPayloadCodec.encode(ChatMessage(text))
        return Packet(PacketHeader(ProtocolConstants.PROTOCOL_VERSION, MessageType.CHAT_MESSAGE,
                                   0, self._outgoing_stream_id(receiver_id), self._next_sequence(),
                                   len(payload), current.user_id, receiver_id), payload)

    def create_global_chat_packet(self, text):
        return self.create_private_chat_packet(0, text)

    def _handle_application_packet(self, packet):
        # Demultiplex existing chat callbacks without opening another account
        # session or letting unsolicited messages consume pending auth replies.
        h = packet.header
        if h.messageType == MessageType.CHAT_MESSAGE:
            if not self.is_authenticated or h.receiverID not in (0, self.user_id):
                raise ValueError("Wrong application packet recipient")
            body = JsonPayloadCodec.decode(packet.payload, ChatMessage)
            self._callbacks.submit(self._notify, "display_message", h.senderID, body.text)
            return True
        if h.messageType == MessageType.ERROR and h.streamID != 0:
            if h.senderID != 0 or h.receiverID != self.user_id:
                raise ValueError("Wrong application error recipient")
            body = JsonPayloadCodec.decode(packet.payload, ErrorPayload)
            self._callbacks.submit(self._notify, "display_error", body.error_code, body.error_message)
            return True
        return False
