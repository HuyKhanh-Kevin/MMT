import json
from common.PacketIO import PacketIO
from common.MessageType import MessageType

class ClientHandler:
    def __init__(self, session, session_manager):
        self.session = session
        self.session_manager = session_manager

    def handle(self):
        sock = self.session.sock
        try:
            while True:
                packet = PacketIO.readPacket(sock)
                if packet is None:
                    break

                msg_type = packet.getHeader().getMessageType()

                if msg_type == MessageType.CHAT_MESSAGE or msg_type == 0x03:
                    self.relay_chat_message(packet)
                else:
                    self.dispatch_to_dong_handlers(packet)

        except (ConnectionResetError, BrokenPipeError, EOFError, OSError):
            pass
        except Exception:
            pass
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
                for target in self.session_manager.get_all_sessions():
                    if target.user_id != self.session.user_id:
                        target.send_packet(packet)
            else:
                target = self.session_manager.get_session(receiver_id)
                if target:
                    target.send_packet(packet)
        except Exception:
            pass

    def dispatch_to_dong_handlers(self, packet):
        pass