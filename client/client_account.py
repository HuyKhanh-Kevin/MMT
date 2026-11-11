import socket
import threading

from client.client_listener import Listener
from common.JsonPayloadCodec import JsonPayloadCodec
from common.MessageType import MessageType
from common.Packet import Packet
from common.PacketHeader import PacketHeader
from common.PacketIO import PacketIO
from common.ProtocolConstants import ProtocolConstants
from common.UdpPacketIO import UdpPacketIO
from common.payload.ChatMessage import ChatMessage
from common.payload.Heartbeat import Heartbeat
from common.payload.LoginRequest import LoginRequest
from common.payload.LoginResponse import LoginResponse
from common.payload.LogoutRequest import LogoutRequest
from common.payload.LogoutResponse import LogoutResponse
from common.payload.SignupRequest import SignupRequest
from common.payload.SignupResponse import SignupResponse
from common.payload.UserListRequest import UserListRequest


class Client:
    def __init__(self, server_ip, server_port, udp_port, peer_tcp_port, file_udp_port):
        self.id = 0
        self.session_id = None

        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        udp_socket = None

        try:
            tcp_socket.connect((server_ip, server_port))

            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.bind(("0.0.0.0", 0))
            udp_socket.settimeout(1.0)

            server_udp_address = (socket.gethostbyname(server_ip), udp_port)
        except OSError:
            try:
                if udp_socket is not None:
                    udp_socket.close()
            finally:
                tcp_socket.close()
            raise

        self.tcp_socket = tcp_socket
        self.udp_socket = udp_socket
        self.server_udp_address = server_udp_address

        self.peer_tcp_port = peer_tcp_port
        self.file_udp_port = file_udp_port

        self.authenticated = False
        self.running = True

        self.listener : Listener

        self.counter_lock = threading.Lock()
        self.tcp_sequence_num = 1
        self.udp_sequence_num = 1
        self.heartbeat_sequence_num = 1

        self.stream_lock = threading.Lock()
        self.outgoing_stream: dict[int, int] = {}
        self.stream_id = 0

        self.stop_event = threading.Event()
        self.heartbeat_thread = None

    def get_authenticated(self) -> bool:
        return self.authenticated

    def get_running(self) -> bool:
        return self.running

    def set_listener(self, listener: Listener) -> None:
        self.listener = listener

    def next_tcp_sequence(self) -> int:
        with self.counter_lock:
            value = self.tcp_sequence_num
            self.tcp_sequence_num += 1
            return value

    def next_udp_sequence(self) -> int:
        with self.counter_lock:
            value = self.udp_sequence_num
            self.udp_sequence_num += 1
            return value

    def next_heartbeat_sequence(self) -> int:
        with self.counter_lock:
            value = self.heartbeat_sequence_num
            self.heartbeat_sequence_num += 1
            return value

    def get_outgoing_stream(self, receiver: int) -> int:
        with self.stream_lock:
            if receiver not in self.outgoing_stream:
                self.outgoing_stream[receiver] = self.stream_id
                self.stream_id += 1
            return self.outgoing_stream[receiver]

    def close_connection(self) -> None:
        self.authenticated = False
        self.running = False

        self.stop_event.set()

        self.udp_socket.close()

        try:
            self.tcp_socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

        self.tcp_socket.close()

    def start_receiving(self) -> None:
        threading.Thread(target=self.tcp_receive_loop, name="tcp-receiver", daemon=True).start()
        threading.Thread(target=self.udp_receive_loop, name="udp-receiver", daemon=True).start()

    def tcp_receive_loop(self) -> None:
        try:
            while self.running:
                packet = PacketIO.readPacket(self.tcp_socket)

                if packet is None:
                    break

                header = packet.getHeader()

                if header.getMessageType() == MessageType.SIGNUP_RESPONSE:
                    try:
                        response: SignupResponse = JsonPayloadCodec.decode(packet.getPayload(), SignupResponse)
                    except (ValueError, TypeError): continue

                    self.listener.display_signup_response(response.get_status(), response.get_reason())

                elif header.getMessageType() == MessageType.LOGIN_RESPONSE:
                    try:
                        response: LoginResponse = JsonPayloadCodec.decode(packet.getPayload(), LoginResponse)
                    except (ValueError, TypeError): continue

                    if response.status == "success":
                        self.id = response.user_id
                        self.session_id = response.session_id
                        self.authenticated = True
                        self.start_heartbeat()
                    self.listener.display_login_response(response.status, response.reason)

                elif header.getMessageType() == MessageType.LOGOUT_RESPONSE:
                    try:
                        response: LogoutResponse = JsonPayloadCodec.decode(packet.getPayload(), LogoutResponse)
                    except (ValueError, TypeError): continue

                    if response.status == "success":
                        self.close_connection()
                    self.listener.display_logout_response(response.status)

                elif header.getMessageType() == MessageType.CHAT_MESSAGE:
                    try:
                        response: ChatMessage = JsonPayloadCodec.decode(packet.getPayload(), ChatMessage)
                    except (ValueError, TypeError): continue

                    self.listener.display_message(header.getSenderID(), response.text)

        except (OSError, EOFError) as error:
            if self.running:
                print(f"TCP receive error: {error}")
        finally:
            self.close_connection()

    def udp_receive_loop(self) -> None:
        while self.running:
            try:
                received = UdpPacketIO.receivePacket(self.udp_socket)
                packet = received.packet
                source = received.source

                if packet is None or source != self.server_udp_address:
                    continue

            except socket.timeout:
                continue
            except OSError as error:
                if self.running:
                    print(f"UDP receive error: {error}")
                continue

    def send_tcp_packet(self, packet: Packet):
        PacketIO.writePacket(self.tcp_socket, packet)

    def send_udp_packet(self, packet: Packet):
        UdpPacketIO.sendPacket(self.udp_socket, self.server_udp_address, packet)

    def start_heartbeat(self) -> None:
        if self.heartbeat_thread is not None and self.heartbeat_thread.is_alive():
            return
        self.heartbeat_thread = threading.Thread(target=self.heartbeat_loop, name="heartbeat", daemon=True)
        self.heartbeat_thread.start()

    def heartbeat_loop(self) -> None:
        while not self.stop_event.wait(5):
            if self.authenticated:
                try:
                    self.send_udp_packet(self.create_heartbeat_packet())
                except OSError as error:
                    print(f"Heartbeat error: {error}")

    def create_signup_packet(self, username: str, password: str) -> Packet:
        signup_request = SignupRequest(username, password)
        try:
            payload = JsonPayloadCodec.encode(signup_request)
        except ValueError as error:
            print(f"Signup error: {error}")
            raise
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.SIGNUP_REQUEST, 0, self.get_outgoing_stream(0), self.next_tcp_sequence(), len(payload), 0, 0)
        return Packet(header, payload)

    def create_login_packet(self, username: str, password: str) -> Packet:
        if self.authenticated:
            raise RuntimeError("You are already logged in")
        login_request = LoginRequest(username, password, self.peer_tcp_port, self.file_udp_port)
        try:
            payload = JsonPayloadCodec.encode(login_request)
        except ValueError as error:
            print(f"Login error: {error}")
            raise
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.LOGIN_REQUEST, 0, self.get_outgoing_stream(0), self.next_tcp_sequence(), len(payload), 0, 0)
        return Packet(header, payload)

    def create_logout_packet(self) -> Packet:
        if not self.authenticated:
            raise RuntimeError("You must login before logout")
        logout_request = LogoutRequest(self.session_id)
        try:
            payload = JsonPayloadCodec.encode(logout_request)
        except ValueError as error:
            print(f"Logout error: {error}")
            raise
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.LOGOUT_REQUEST, 0, self.get_outgoing_stream(0), self.next_tcp_sequence(), len(payload), self.id, 0)
        return Packet(header, payload)

    def create_user_list_packet(self, cursor: str | None = None) -> Packet:
        if not self.authenticated:
            raise RuntimeError("You must login before requesting user list")
        user_list_request = UserListRequest(self.session_id, cursor)
        try:
            payload = JsonPayloadCodec.encode(user_list_request)
        except ValueError as error:
            print(f"User list error: {error}")
            raise
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.USER_LIST_REQUEST, 0, self.get_outgoing_stream(0), self.next_udp_sequence(), len(payload), self.id, 0)
        return Packet(header, payload)

    def create_private_message_packet(self, receiver: int, message: str) -> Packet:
        if not self.authenticated:
            raise RuntimeError("You must login before sending messages")
        chat_message = ChatMessage(message)
        try:
            payload = JsonPayloadCodec.encode(chat_message)
        except ValueError as error:
            print(f"Private chat message error: {error}")
            raise
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.CHAT_MESSAGE, 0, self.get_outgoing_stream(receiver), self.next_tcp_sequence(), len(payload), self.id, receiver)
        return Packet(header, payload)

    def create_global_message_packet(self, message: str) -> Packet:
        if not self.authenticated:
            raise RuntimeError("You must login before sending messages")
        chat_message = ChatMessage(message)
        try:
            payload = JsonPayloadCodec.encode(chat_message)
        except ValueError as error:
            print(f"Global chat message error: {error}")
            raise
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.CHAT_MESSAGE, 0, self.get_outgoing_stream(0), self.next_tcp_sequence(), len(payload), self.id, 0)
        return Packet(header, payload)

    def create_heartbeat_packet(self) -> Packet:
        heartbeat = Heartbeat(self.session_id, self.next_heartbeat_sequence())
        try:
            payload = JsonPayloadCodec.encode(heartbeat)
        except ValueError as error:
            print(f"Heartbeat error: {error}")
            raise
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.HEARTBEAT, 0, self.get_outgoing_stream(0), self.next_udp_sequence(), len(payload), self.id, 0)
        return Packet(header, payload)

    def exit_program(self):
        if self.running:
            self.close_connection()