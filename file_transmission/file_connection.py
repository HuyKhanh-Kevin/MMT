import socket
import threading


class FileConnection:
    def __init__(self):
        peer_tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        file_udp_socket = None

        try:
            peer_tcp_socket.bind(("0.0.0.0", 0))
            peer_tcp_socket.listen(10)
            peer_tcp_socket.settimeout(1.0)

            file_udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            file_udp_socket.bind(("0.0.0.0", 0))
            file_udp_socket.settimeout(1.0)
        except OSError:
            try:
                if file_udp_socket is not None:
                    file_udp_socket.close()
            finally:
                peer_tcp_socket.close()
            raise

        self.peer_tcp_socket = peer_tcp_socket
        self.file_udp_socket = file_udp_socket

        self.stop_event = threading.Event()

        self.peer_tcp_connections: dict[str, socket.socket] = {}

    def start_accepting(self) -> None:
        threading.Thread(target=self.peer_accept, name="peer-listener", daemon=True).start()

    def peer_accept(self) -> None:
        while not self.stop_event.is_set():
            try:
                connection, address = self.peer_tcp_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                if self.stop_event.is_set():
                    break
                raise

            self.peer_tcp_connections[address[0]] = connection

    def connect_peer(self, peer_ip: str, peer_tcp_port: int) -> None:
        if self.peer_tcp_connections.get(peer_ip, None) is None:
            tmp_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                tmp_connection.connect((peer_ip, peer_tcp_port))
            except OSError:
                tmp_connection.close()
                raise
            connection = tmp_connection
            self.peer_tcp_connections[peer_ip] = connection

    def get_peer_tcp_port(self) -> int:
        return self.peer_tcp_socket.getsockname()[1]

    def get_file_udp_port(self) -> int:
        return self.file_udp_socket.getsockname()[1]

    def get_peer_tcp_connection(self, peer_ip: str) -> socket.socket | None:
        return self.peer_tcp_connections.get(peer_ip, None)

    def remove_peer_connection(self, peer_ip: str) -> None:
        if self.get_peer_tcp_connection(peer_ip) is not None:
            self.peer_tcp_connections.pop(peer_ip)

    def close_connection(self) -> None:
        self.stop_event.set()
        self.file_udp_socket.close()

        for connection in self.peer_tcp_connections.values():
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()

        try:
            self.peer_tcp_socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.peer_tcp_socket.close()