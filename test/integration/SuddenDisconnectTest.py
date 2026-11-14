"""Python port of clean, reset, and concurrent TCP disconnect scenarios.

Run from the project root with:
    python -m unittest test.integration.SuddenDisconnectTest -v
"""

import socket
import struct
import threading
import time
import unittest

from common.MessageType import MessageType
from common.Packet import Packet
from common.PacketHeader import PacketHeader
from common.PacketIO import PacketIO
from common.ProtocolConstants import ProtocolConstants


def reset_and_close(sock: socket.socket) -> None:
    # SO_LINGER(1, 0) requests an abortive close (TCP RST).
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("hh", 1, 0))
    sock.sendall(b"\x01\x02\x03\x04\x05")
    sock.close()


class SuddenDisconnectTest(unittest.TestCase):
    def test_immediate_client_disconnect_is_clean_eof(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(2)
            client = socket.create_connection(listener.getsockname(), timeout=2)
            client.close()
            peer, _ = listener.accept()
            with peer:
                self.assertIsNone(PacketIO.readPacket(peer))

    def test_mid_frame_reset_terminates_reader(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(2)
            client = socket.create_connection(listener.getsockname(), timeout=2)
            peer, _ = listener.accept()
            peer.settimeout(2)
            result = []

            def read_frame():
                try:
                    result.append(PacketIO.readPacket(peer))
                except (EOFError, OSError) as exc:
                    result.append(exc)

            worker = threading.Thread(target=read_frame)
            worker.start()
            reset_and_close(client)
            worker.join(timeout=2)

            self.assertFalse(worker.is_alive())
            self.assertEqual(1, len(result))
            self.assertIsInstance(result[0], (EOFError, OSError))
            peer.close()

    def test_five_concurrent_disconnects_do_not_block_a_valid_client(self):
        client_count = 5
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(client_count + 1)
            listener.settimeout(3)
            handled = []
            handled_lock = threading.Lock()
            workers = []

            def handle(peer):
                try:
                    peer.settimeout(2)
                    PacketIO.readPacket(peer)
                except (EOFError, OSError):
                    pass
                finally:
                    peer.close()
                    with handled_lock:
                        handled.append(True)

            def accept_n(count):
                for _ in range(count):
                    peer, _ = listener.accept()
                    worker = threading.Thread(target=handle, args=(peer,))
                    worker.start()
                    workers.append(worker)

            acceptor = threading.Thread(target=accept_n, args=(client_count,))
            acceptor.start()
            clients = []
            for _ in range(client_count):
                client = socket.create_connection(listener.getsockname(), timeout=2)
                clients.append(client)
            for client in clients:
                reset_and_close(client)
            acceptor.join(timeout=3)
            for worker in workers:
                worker.join(timeout=2)

            self.assertEqual(client_count, len(handled))

            valid_acceptor = threading.Thread(target=accept_n, args=(1,))
            valid_acceptor.start()
            with socket.create_connection(listener.getsockname(), timeout=2) as healthy:
                packet = Packet(
                    PacketHeader(
                        ProtocolConstants.PROTOCOL_VERSION,
                        MessageType.HEARTBEAT,
                        0,
                        1,
                        1,
                        4,
                        1,
                        0,
                    ),
                    b"PING",
                )
                PacketIO.writePacket(healthy, packet)
            valid_acceptor.join(timeout=3)
            for worker in workers[client_count:]:
                worker.join(timeout=2)
            self.assertEqual(client_count + 1, len(handled))


if __name__ == "__main__":
    unittest.main()
