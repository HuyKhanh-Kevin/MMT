import socket
import threading
from server.session_manager import SessionManager, ClientSession
from server.client_handler import ClientHandler
from common.PacketIO import PacketIO
from common.MessageType import MessageType

class HybridServer:
    def __init__(self, host="0.0.0.0", port=8080):
        self.host = host
        self.port = port
        self.session_manager = SessionManager()
        self.running = True

    def listen_udp(self):
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.bind((self.host, self.port))

        while self.running:
            try:
                data, addr = udp_sock.recvfrom(2048)
                if not data:
                    continue

                packet = PacketIO.decode(data)
                msg_type = packet.getHeader().getMessageType()

                if msg_type == MessageType.HEARTBEAT or msg_type == 0x05:
                    pass
                elif msg_type == MessageType.USER_LIST_REQUEST or msg_type == 0x12:
                    response_packet = self.build_user_list_response()
                    if response_packet:
                        udp_sock.sendto(response_packet.encode(), addr)

            except Exception:
                if not self.running:
                    break

        udp_sock.close()

    def build_user_list_response(self):
        return None

    def listen_tcp(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((self.host, self.port))
        server_sock.listen(20)

        try:
            while self.running:
                client_sock, client_addr = server_sock.accept()
                session = ClientSession(client_sock, client_addr)
                handler = ClientHandler(session, self.session_manager)

                client_thread = threading.Thread(target=handler.handle, daemon=True)
                client_thread.start()
        except Exception:
            pass
        finally:
            server_sock.close()

    def start(self):
        udp_thread = threading.Thread(target=self.listen_udp, daemon=True)
        udp_thread.start()
        self.listen_tcp()

if __name__ == "__main__":
    server = HybridServer(port=8080)
    server.start()