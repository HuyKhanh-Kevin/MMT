import socket
import threading
from server.session_manager import SessionManager, ClientSession
from server.client_handler import ClientHandler

class TCPServer:
    def __init__(self, host="0.0.0.0", port=8080):
        self.host = host
        self.port = port
        self.session_manager = SessionManager()

    def start(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((self.host, self.port))
        server_sock.listen(20)

        print("==================================================")
        print(f"[SERVER] TCP Server đang lắng nghe tại: {self.host}:{self.port}")
        print("==================================================")

        try:
            while True:
                client_sock, client_addr = server_sock.accept()
                print(f"[SERVER] Nhận kết nối mới từ: {client_addr}")

                session = ClientSession(client_sock, client_addr)
                handler = ClientHandler(session, self.session_manager)

                client_thread = threading.Thread(target=handler.handle, daemon=True)
                client_thread.start()
        except KeyboardInterrupt:
            print("\n[SERVER] Đang dừng Server...")
        finally:
            server_sock.close()

if __name__ == "__main__":
    server = TCPServer(port=8080)
    server.start()