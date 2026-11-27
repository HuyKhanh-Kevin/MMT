import argparse
import threading

from server.client_handler import ClientHandler
from server.session_manager import ClientSession, SessionManager
from server.tracker_server import TrackerServer


class TCPServer(TrackerServer):
    def __init__(self, host="0.0.0.0", port=8080, udp_port=5000,
                 account_file="data/python_accounts.json", **options):
        self.session_manager = SessionManager()
        self._client_handlers = {}
        super().__init__(host, port, udp_port, account_file, **options)

    def _handle_tcp(self, connection, source_ip, request):
        with self._lock:
            handler = self._client_handlers.get(connection)
            if handler is None:
                peer = self._connections[connection]
                session = ClientSession(peer, peer.getpeername())
                handler = ClientHandler(session, self.session_manager,
                                        self.handler, self.sessions, connection)
                self._client_handlers[connection] = handler
        return handler.handle_packet(request)

    def _send_response(self, connection, peer, response):
        self._client_handlers[connection].session.send_packet(response)

    def _disconnect(self, connection):
        with self._lock:
            handler = self._client_handlers.pop(connection, None)
        if handler is not None:
            self.session_manager.remove_session(handler.session)
        super()._disconnect(connection)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", "--tcp-port", type=int, default=8080)
    parser.add_argument("--udp-port", type=int, default=5000)
    parser.add_argument("--accounts", default="data/python_accounts.json")
    args = parser.parse_args()
    with TCPServer(args.host, args.port, args.udp_port, args.accounts) as server:
        print(f"Server TCP={server.tcp_port} UDP={server.udp_port}", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
