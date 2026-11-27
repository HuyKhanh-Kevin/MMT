import socket
import threading
import json
import time
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
                sender_id = packet.getHeader().getSenderID()

                if msg_type == MessageType.HEARTBEAT or msg_type == 0x05:
                    if sender_id > 0:
                        self.session_manager.update_user_heartbeat(sender_id)

                elif msg_type == MessageType.USER_LIST_REQUEST or msg_type == 0x12:
                    response_bytes = self.build_user_list_response()
                    if response_bytes:
                        udp_sock.sendto(response_bytes, addr)

            except Exception:
                if not self.running:
                    break

        udp_sock.close()

    def monitor_heartbeats(self):
        while self.running:
            time.sleep(5)
            self.session_manager.cleanup_inactive_sessions(timeout=15)

    def build_user_list_response(self):
        try:
            users_info = []
            for session in self.session_manager.get_all_sessions():
                users_info.append({
                    "user_id": session.user_id,
                    "username": session.username,
                    "status": "online",
                    "ip": session.addr[0] if session.addr else "127.0.0.1",
                    "tcp_port": session.tcp_port
                })
            
            payload = json.dumps({"users": users_info, "next_cursor": None}).encode('utf-8')
            return payload
        except Exception:
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

        monitor_thread = threading.Thread(target=self.monitor_heartbeats, daemon=True)
        monitor_thread.start()

        self.listen_tcp()

if __name__ == "__main__":
    server = HybridServer(port=8080)
    server.start()