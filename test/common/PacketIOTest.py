"""Socket-only equivalent of the 9 Java PacketIO tests.

Save as test/common/PacketIOTest.py and run from the project root:
    python -m unittest test.common.PacketIOTest -v
"""

import socket
import struct
import unittest
from concurrent.futures import ThreadPoolExecutor

from common.MessageType import MessageType
from common.Packet import Packet
from common.PacketCodec import PacketCodec
from common.PacketHeader import PacketHeader
from common.PacketIO import PacketIO
from common.ProtocolConstants import ProtocolConstants


class FakeSocket:
    """Socket test double that guarantees short recv() calls and records sendall()."""

    def __init__(self, incoming: bytes = b"", max_read: int | None = None):
        self.incoming = incoming
        self.offset = 0
        self.max_read = max_read
        self.recv_calls = 0
        self.sent = bytearray()
        self.send_calls = 0

    def recv(self, size: int) -> bytes:
        self.recv_calls += 1
        if self.max_read is not None:
            size = min(size, self.max_read)
        end = min(self.offset + size, len(self.incoming))
        chunk = self.incoming[self.offset:end]
        self.offset = end
        return chunk

    def sendall(self, data: bytes) -> None:
        self.send_calls += 1
        self.sent.extend(data)


class PacketIOTest(unittest.TestCase):
    @staticmethod
    def packet(payload: bytes) -> Packet:
        # Constructor order: payload_length BEFORE sender_id and receiver_id.
        return Packet(
            PacketHeader(
                ProtocolConstants.PROTOCOL_VERSION,
                MessageType.CHAT_MESSAGE,
                0x1234,
                0x01020304,
                0x05060708,
                len(payload),
                0x11121314,
                0x21222324,
            ),
            payload,
        )

    def assert_packet_equals(self, expected: Packet, actual: Packet) -> None:
        self.assertIsNotNone(actual)
        self.assertEqual(PacketCodec.encode(expected), PacketCodec.encode(actual))

    def test_packet_split_into_many_small_reads(self):
        original = self.packet(bytes([1, 2, 3, 4, 5, 6, 7]))
        wire = PacketCodec.encode(original)
        for max_read in (1, 2, 5, 7):
            with self.subTest(max_read=max_read):
                sock = FakeSocket(wire, max_read=max_read)
                self.assert_packet_equals(original, PacketIO.readPacket(sock))
                self.assertGreater(sock.recv_calls, 2)
                self.assertIsNone(PacketIO.readPacket(sock))

    def test_several_packets_in_one_stream_remain_separate(self):
        packets = (
            self.packet(bytes([1, 2])),
            self.packet(b""),
            self.packet(bytes([9, 8, 7])),
        )
        writer = FakeSocket()
        for packet in packets:
            PacketIO.writePacket(writer, packet)

        for max_read in (None, 3):
            with self.subTest(max_read=max_read):
                reader = FakeSocket(bytes(writer.sent), max_read=max_read)
                for packet in packets:
                    self.assert_packet_equals(packet, PacketIO.readPacket(reader))
                self.assertIsNone(PacketIO.readPacket(reader))

    def test_clean_eof_returns_none(self):
        self.assertIsNone(PacketIO.readPacket(FakeSocket()))

    def test_eof_during_header_throws(self):
        with self.assertRaises(EOFError):
            PacketIO.readPacket(FakeSocket(bytes(23)))

    def test_eof_during_payload_throws(self):
        wire = PacketCodec.encode(self.packet(bytes(3)))
        with self.assertRaises(EOFError):
            PacketIO.readPacket(FakeSocket(wire[:-1]))

    def test_bad_length_rejected_before_reading_payload(self):
        for length in (-1, 1177, 2**31 - 1):
            with self.subTest(payload_length=length):
                wire = bytearray(PacketCodec.encode(self.packet(b"")))
                struct.pack_into(">i", wire, 20, length)
                sock = FakeSocket(bytes(wire))
                with self.assertRaises(OSError):
                    PacketIO.readPacket(sock)
                self.assertEqual(sock.recv_calls, 1, "Must reject after header")

    def test_malformed_header_becomes_os_error(self):
        wire = bytearray(PacketCodec.encode(self.packet(b"")))
        wire[1] = 21  # Current protocol: message types 1..20, including 9.
        with self.assertRaises(OSError):
            PacketIO.readPacket(FakeSocket(bytes(wire)))

    def test_writes_complete_packet(self):
        packet = self.packet(bytes([1, 2, 3]))
        sock = FakeSocket()
        PacketIO.writePacket(sock, packet)
        self.assertEqual(bytes(sock.sent), PacketCodec.encode(packet))
        self.assertEqual(sock.send_calls, 1)

    def test_real_tcp_loopback_echo(self):
        original = self.packet(bytes([0, 1, 255]))
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(3)

            def echo_server():
                with listener.accept()[0] as peer:
                    peer.settimeout(3)
                    incoming = PacketIO.readPacket(peer)
                    self.assertIsNotNone(incoming)
                    PacketIO.writePacket(peer, incoming)

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(echo_server)
                with socket.create_connection(listener.getsockname(), timeout=3) as client:
                    PacketIO.writePacket(client, original)
                    self.assert_packet_equals(original, PacketIO.readPacket(client))
                    self.assertIsNone(PacketIO.readPacket(client))
                future.result(timeout=5)


if __name__ == "__main__":
    unittest.main()
