"""Account TCP control and UDP discovery server using only Python's stdlib."""

import argparse
import logging
from pathlib import Path
import socket
import threading
import uuid

from common.ControlPackets import ControlPackets
from common.MessageType import MessageType
from common.PacketIO import PacketIO
from common.UdpPacketIO import UdpPacketIO
from server.account_request_handler import AccountRequestHandler
from server.account_store import AccountStore
from server.online_directory import OnlineDirectory
from server.session_registry import SessionRegistry

LOG = logging.getLogger(__name__)


class TrackerServer:
    def __init__(self, host="127.0.0.1", tcp_port=5000, udp_port=5000,
                 account_file="data/python_accounts.json", *, timeout=15.0,
                 max_connections=64, idle_timeout=120.0):
        if type(max_connections) is not int or max_connections < 1 or idle_timeout <= 0:
            raise ValueError("Invalid server limits")
        self.accounts = AccountStore(account_file)
        self.sessions = SessionRegistry(timeout)
        self.directory = OnlineDirectory()
        self.handler = AccountRequestHandler(self.accounts, self.sessions, self.directory)
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._publish_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max_connections)
        self._connections = {}
        self._workers = set()
        self._loops = []
        self._started = False
        self._closed = False
        self._presence_sequence = 0
        self._idle_timeout = idle_timeout
        self._tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self._tcp.bind((host, tcp_port))
            self._tcp.listen(max_connections)
            self._tcp.settimeout(0.2)
            self._udp.bind((host, udp_port))
            self._udp.settimeout(0.2)
        except BaseException:
            self._tcp.close()
            self._udp.close()
            raise

    @property
    def tcp_port(self):
        return self._tcp.getsockname()[1]

    @property
    def udp_port(self):
        return self._udp.getsockname()[1]

    def start(self):
        with self._lock:
            if self._closed:
                raise RuntimeError("Server is closed")
            if self._started:
                return self
            self._started = True
            for name, target in (("accept", self._accept_loop), ("udp", self._udp_loop),
                                 ("maintenance", self._maintenance_loop)):
                thread = threading.Thread(target=target, name=f"tracker-{name}", daemon=True)
                self._loops.append(thread)
                thread.start()
        return self

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                peer, source = self._tcp.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            if not self._slots.acquire(blocking=False):
                peer.close()
                continue
            connection = uuid.uuid4()
            thread = None
            try:
                peer.settimeout(self._idle_timeout)
                peer.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                with self._lock:
                    if self._closed:
                        peer.close()
                        self._slots.release()
                        return
                    self._connections[connection] = peer
                    thread = threading.Thread(target=self._control_loop,
                                              args=(connection, peer, source[0]),
                                              name="tracker-control", daemon=True)
                    self._workers.add(thread)
                    thread.start()
            except (OSError, RuntimeError):
                with self._lock:
                    self._connections.pop(connection, None)
                    self._workers.discard(thread)
                peer.close()
                self._slots.release()

    def _control_loop(self, connection, peer, source_ip):
        try:
            with peer:
                while not self._stop.is_set():
                    request = PacketIO.readPacket(peer)
                    if request is None:
                        break
                    response = self.handler.handle_tcp(connection, source_ip, request)
                    peer.settimeout(None if self.sessions.has_session(connection) else self._idle_timeout)
                    PacketIO.writePacket(peer, response)
                    self._publish_changes()
        except (OSError, EOFError):
            pass  # A broken/partial TCP frame ends only this client's connection.
        except Exception:
            LOG.exception("Account connection failed")
        finally:
            self.sessions.disconnect(connection)
            self._slots.release()
            self._publish_changes()
            with self._lock:
                self._connections.pop(connection, None)
                self._workers.discard(threading.current_thread())

    def _udp_loop(self):
        while not self._stop.is_set():
            try:
                received = UdpPacketIO.receivePacket(self._udp)
                response = self.handler.handle_udp(received.packet, received.source)
                if response is not None:
                    UdpPacketIO.sendPacket(self._udp, received.source, response)
                self._publish_changes()
            except (OSError, ValueError, TypeError):
                continue  # Drop unframed datagrams; no trustworthy request reference.
            except Exception:
                LOG.exception("UDP request failed")

    def _maintenance_loop(self):
        while not self._stop.wait(0.1):
            self.sessions.expire()
            for connection in self.sessions.drain_disconnected_connections():
                with self._lock:
                    peer = self._connections.get(connection)
                if peer is not None:
                    self._close_socket(peer)
            self.directory.cleanup(self.sessions.active_tokens())
            self._publish_changes()

    def _publish_changes(self):
        with self._publish_lock:
            for update in self.sessions.drain_changes():
                self._presence_sequence = self._presence_sequence % 0xFFFFFFFF + 1
                for peer in self.sessions.online_peers():
                    if peer.presence_endpoint is None or peer.username == update.username:
                        continue
                    packet = ControlPackets.create(str(MessageType.PRESENCE_UPDATE),
                                                   self._presence_sequence, 0, peer.user_id, update)
                    try:
                        UdpPacketIO.sendPacket(self._udp, peer.presence_endpoint, packet)
                    except OSError:
                        pass  # Discovery repairs missed presence notifications.

    @staticmethod
    def _close_socket(peer):
        try:
            peer.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        peer.close()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stop.set()
            self._tcp.close()
            self._udp.close()
            connections = tuple(self._connections.values())
            threads = (*self._loops, *self._workers)
        for peer in connections:
            self._close_socket(peer)
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(timeout=3)

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.close()


def main():
    parser = argparse.ArgumentParser(description="Python account/session/presence tracker")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--tcp-port", type=int, default=5000)
    parser.add_argument("--udp-port", type=int, default=5000)
    parser.add_argument("--accounts", type=Path, default=Path("data/python_accounts.json"))
    parser.add_argument("--login-timeout", type=float, default=120.0,
                        help="Idle seconds allowed before login (default: 120)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    with TrackerServer(args.host, args.tcp_port, args.udp_port, args.accounts,
                       idle_timeout=args.login_timeout) as server:
        print(f"Tracker TCP={server.tcp_port} UDP={server.udp_port}; heartbeat=5s timeout=15s", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
