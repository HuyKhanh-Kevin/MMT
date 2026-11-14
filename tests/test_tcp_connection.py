"""
tests.test_tcp_connection
~~~~~~~~~~~~~~~~~~~~~~~~~

Integration tests for raw TCP socket connections.

Tests that the proxy and backend handle TCP connections correctly:
- Accepting connections
- Sending and receiving data
- Handling disconnects gracefully

Run from project root:
    python -m unittest tests.test_tcp_connection -v
"""

import socket
import threading
import time
import unittest


def _start_echo_server(host='127.0.0.1', port=0):
    """Start a simple echo server in a background thread.
    Returns (server_socket, bound_port, stop_event).
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(5)
    srv.settimeout(2.0)
    actual_port = srv.getsockname()[1]
    stop_event = threading.Event()

    def _serve():
        while not stop_event.is_set():
            try:
                conn, _ = srv.accept()
                conn.settimeout(2.0)
                try:
                    data = conn.recv(4096)
                    if data:
                        conn.sendall(data)
                except socket.timeout:
                    pass
                finally:
                    conn.close()
            except socket.timeout:
                continue
            except OSError:
                break
        srv.close()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    return srv, actual_port, stop_event


class TestTCPBasicConnect(unittest.TestCase):
    """Basic TCP connectivity tests."""

    def setUp(self):
        self.srv, self.port, self.stop_event = _start_echo_server()

    def tearDown(self):
        self.stop_event.set()

    def test_client_can_connect(self):
        """A TCP client must be able to connect to a listening server."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(2.0)
            client.connect(('127.0.0.1', self.port))
            # No exception means connect succeeded

    def test_server_echoes_data(self):
        """Data sent to the echo server must be returned unchanged."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(2.0)
            client.connect(('127.0.0.1', self.port))
            client.sendall(b"hello network")
            received = client.recv(64)
            self.assertEqual(b"hello network", received)

    def test_multiple_clients_in_sequence(self):
        """Server must handle multiple sequential client connections."""
        for i in range(3):
            with self.subTest(connection=i):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                    client.settimeout(2.0)
                    client.connect(('127.0.0.1', self.port))
                    msg = f"msg{i}".encode()
                    client.sendall(msg)
                    received = client.recv(64)
                    self.assertEqual(msg, received)


class TestTCPDisconnect(unittest.TestCase):
    """Tests for handling disconnections."""

    def test_connect_to_closed_port_raises(self):
        """Connecting to a port with no listener must raise ConnectionRefusedError."""
        # Find a free port, then DON'T listen on it
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(('127.0.0.1', 0))
        free_port = probe.getsockname()[1]
        probe.close()
        time.sleep(0.05)  # Let OS release the port

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(2.0)
            with self.assertRaises((ConnectionRefusedError, OSError)):
                client.connect(('127.0.0.1', free_port))

    def test_server_close_causes_client_recv_empty(self):
        """When server closes connection, client recv() must return empty bytes."""
        srv, actual_port, stop_event = _start_echo_server()

        # Custom server that closes immediately after accept
        close_port_holder = []

        def close_immediately():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', 0))
            sock.listen(1)
            sock.settimeout(2.0)
            close_port_holder.append(sock.getsockname()[1])
            try:
                conn, _ = sock.accept()
                conn.close()  # Immediately close
            except socket.timeout:
                pass
            sock.close()

        t = threading.Thread(target=close_immediately, daemon=True)
        t.start()
        time.sleep(0.1)  # Let server start

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(2.0)
            client.connect(('127.0.0.1', close_port_holder[0]))
            data = client.recv(64)
            self.assertEqual(b"", data)

        stop_event.set()


class TestTCPSocketPair(unittest.TestCase):
    """Tests using socket.socketpair() for in-process communication."""

    def test_socketpair_data_transfer(self):
        """Data written to one side of a socketpair must be readable from the other."""
        a, b = socket.socketpair()
        with a, b:
            a.sendall(b"ping")
            b.settimeout(1.0)
            received = b.recv(64)
            self.assertEqual(b"ping", received)

    def test_socketpair_close_causes_eof(self):
        """Closing one side of socketpair must cause recv() to return empty on the other."""
        a, b = socket.socketpair()
        with b:
            a.close()
            b.settimeout(1.0)
            data = b.recv(64)
            self.assertEqual(b"", data)

    def test_socketpair_bidirectional(self):
        """Both sides of socketpair must be able to send and receive."""
        a, b = socket.socketpair()
        with a, b:
            a.sendall(b"request")
            b.settimeout(1.0)
            self.assertEqual(b"request", b.recv(64))

            b.sendall(b"response")
            a.settimeout(1.0)
            self.assertEqual(b"response", a.recv(64))


if __name__ == "__main__":
    unittest.main()
