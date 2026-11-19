import threading
from common.PacketIO import PacketIO

class ClientSession:
    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.user_id = 0
        self.username = ""
        self.lock = threading.Lock()  # Đồng bộ gửi dữ liệu, tránh xung đột giữa các luồng

    def send_packet(self, packet):
        """Đồng bộ việc ghi packet khi nhiều luồng cùng gửi tới một client"""
        with self.lock:
            if self.sock and not self.sock._closed:
                PacketIO.writePacket(self.sock, packet)

class SessionManager:
    def __init__(self):
        self.active_sessions = {}  # user_id -> ClientSession
        self.lock = threading.Lock()

    def register_user(self, user_id, session):
        with self.lock:
            session.user_id = user_id
            self.active_sessions[user_id] = session
            print(f"[SERVER] User registered: ID={user_id} ({session.username})")

    def remove_session(self, session):
        with self.lock:
            if session.user_id != 0 and session.user_id in self.active_sessions:
                del self.active_sessions[session.user_id]
                print(f"[SERVER] User disconnected: ID={session.user_id}")

    def get_session(self, user_id):
        with self.lock:
            return self.active_sessions.get(user_id)

    def get_all_sessions(self):
        with self.lock:
            return list(self.active_sessions.values())