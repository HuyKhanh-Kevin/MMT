import threading
import time
from common.PacketIO import PacketIO

class ClientSession:
    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.user_id = 0
        self.username = ""
        self.tcp_port = addr[1] if addr else 0
        self.udp_port = 0
        self.last_heartbeat = time.time()
        self.lock = threading.Lock()

    def update_heartbeat(self):
        with self.lock:
            self.last_heartbeat = time.time()

    def send_packet(self, packet):
        with self.lock:
            if self.sock and not self.sock._closed:
                PacketIO.writePacket(self.sock, packet)

class SessionManager:
    def __init__(self):
        self.active_sessions = {}
        self.lock = threading.Lock()

    def register_user(self, user_id, session):
        with self.lock:
            session.user_id = user_id
            self.active_sessions[user_id] = session

    def remove_session(self, session):
        with self.lock:
            if session.user_id != 0 and session.user_id in self.active_sessions:
                del self.active_sessions[session.user_id]

    def get_session(self, user_id):
        with self.lock:
            return self.active_sessions.get(user_id)

    def get_all_sessions(self):
        with self.lock:
            return list(self.active_sessions.values())

    def update_user_heartbeat(self, user_id):
        with self.lock:
            session = self.active_sessions.get(user_id)
            if session:
                session.update_heartbeat()

    def cleanup_inactive_sessions(self, timeout=15):
        now = time.time()
        with self.lock:
            expired = [
                uid for uid, session in self.active_sessions.items()
                if now - session.last_heartbeat > timeout
            ]
            for uid in expired:
                session = self.active_sessions.pop(uid, None)
                if session and session.sock:
                    try:
                        session.sock.close()
                    except Exception:
                        pass