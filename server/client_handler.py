from common.PacketIO import read_packet
from common.MessageType import MessageType

class ClientHandler:
    def __init__(self, session, session_manager):
        self.session = session
        self.session_manager = session_manager

    def handle(self):
        sock = self.session.sock
        try:
            while True:
                # Đọc packet sử dụng PacketIO của Khánh
                packet = read_packet(sock)
                if packet is None:
                    break

                msg_type = packet.getHeader().getMessageType()

                # Phối hợp với Ca: Chuyển tiếp tin nhắn Chat (0x03)
                if msg_type == MessageType.CHAT_MESSAGE or msg_type == 0x03:
                    self.relay_chat_message(packet)
                # Ghép các Handler nghiệp vụ của Đông
                else:
                    self.dispatch_to_dong_handlers(packet)

        except (ConnectionResetError, BrokenPipeError, EOFError, OSError):
            print(f"[SERVER] Client {self.session.addr} ngắt kết nối an toàn.")
        except Exception as e:
            print(f"[SERVER] Lỗi xử lý Client: {e}")
        finally:
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
        pass