from common.PacketIO import PacketIO
from common.MessageType import MessageType
from common.JsonPayloadCodec import JsonPayloadCodec
from common.payload.LoginResponse import LoginResponse

class ClientHandler:
    def __init__(self, session, session_manager, account_handler, sessions, connection):
        self.session = session
        self.session_manager = session_manager
        self.account_handler = account_handler
        self.sessions = sessions
        self.connection = connection

    def handle_packet(self, packet):
        if packet.header.messageType == MessageType.CHAT_MESSAGE:
            if (not self.sessions.has_session(self.connection)
                    or packet.header.senderID != self.session.user_id):
                return self.account_handler.error(packet, 1004, "UNAUTHENTICATED")
            self.relay_chat_message(packet)
            return None
        return self.dispatch_to_dong_handlers(packet)

    def handle(self):
        sock = self.session.sock
        try:
            while True:
                # Đọc packet sử dụng PacketIO của Khánh
                packet = PacketIO.readPacket(sock)
                if packet is None:
                    break

                response = self.handle_packet(packet)
                if response is not None:
                    self.session.send_packet(response)

        except (ConnectionResetError, BrokenPipeError, EOFError, OSError):
            print(f"[SERVER] Client {self.session.addr} ngắt kết nối an toàn.")
        except Exception as e:
            print(f"[SERVER] Lỗi xử lý Client: {e}")
        finally:
            self.sessions.disconnect(self.connection)
            self.session_manager.remove_session(self.session)
            try:
                sock.close()
            except Exception:
                pass

    def relay_chat_message(self, packet):
        receiver_id = packet.getHeader().getReceiverID()

        try:
            if receiver_id == 0:
                # Chat Broadcast
                for target in self.session_manager.get_all_sessions():
                    if target.user_id != self.session.user_id:
                        target.send_packet(packet)
            else:
                # Chat Private
                target = self.session_manager.get_session(receiver_id)
                if target:
                    target.send_packet(packet)
                else:
                    print(f"[SERVER] User {receiver_id} đang offline.")
        except Exception as e:
            print(f"[SERVER] Lỗi chuyển tiếp chat: {e}")

    def dispatch_to_dong_handlers(self, packet):
        response = self.account_handler.handle_tcp(
            self.connection, self.session.addr[0], packet)
        if response.header.messageType == MessageType.LOGIN_RESPONSE:
            result = JsonPayloadCodec.decode(response.payload, LoginResponse)
            if result.status == "success":
                self.session_manager.register_user(result.user_id, self.session)
        if not self.sessions.has_session(self.connection):
            self.session_manager.remove_session(self.session)
            self.session.user_id = 0
        return response
