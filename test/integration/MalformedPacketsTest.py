"""Python port of malformed-frame and packet-validation scenarios.

Run from the project root with:
    python -m unittest test.integration.MalformedPacketsTest -v
"""

import socket
import struct
import threading
import unittest

from common.MessageType import MessageType
from common.Packet import Packet
from common.PacketCodec import PacketCodec
from common.PacketHeader import PacketHeader
from common.PacketIO import PacketIO
from common.ProtocolConstants import ProtocolConstants


class MalformedPacketsTest(unittest.TestCase):
    def test_incomplete_tcp_header_is_reported_as_eof(self):
        server_side, client_side = socket.socketpair()
        with server_side, client_side:
            errors = []

            def reader():
                try:
                    PacketIO.readPacket(server_side)
                except Exception as exc:
                    errors.append(exc)

            worker = threading.Thread(target=reader)
            worker.start()
            client_side.sendall(bytes(range(10)))
            client_side.close()
            worker.join(timeout=2)

            self.assertFalse(worker.is_alive())
            self.assertEqual(1, len(errors))
            self.assertIsInstance(errors[0], EOFError)

    def test_invalid_protocol_version_is_rejected(self):
        packet = Packet(PacketHeader(99, 1, 0, 0, 1, 0, 0, 0), b"")
        with self.assertRaisesRegex(ValueError, "Unsupported protocol version"):
            PacketCodec.encode(packet)

    def test_unknown_message_type_is_rejected(self):
        packet = Packet(PacketHeader(2, 0x99, 0, 0, 1, 0, 0, 0), b"")
        with self.assertRaisesRegex(ValueError, "Unknown message type"):
            PacketCodec.encode(packet)

    def test_declared_payload_larger_than_received_payload_is_eof(self):
        # The announced payload must be within the protocol limit; only then
        # does PacketIO attempt to read it and encounter the truncated stream.
        header = PacketHeader(2, MessageType.CHAT_MESSAGE, 0, 0, 1, 100, 1, 0)
        wire = header.toBytes() + b"short"
        server_side, client_side = socket.socketpair()
        with server_side, client_side:
            errors = []

            def reader():
                try:
                    PacketIO.readPacket(server_side)
                except Exception as exc:
                    errors.append(exc)

            worker = threading.Thread(target=reader)
            worker.start()
            client_side.sendall(wire)
            client_side.shutdown(socket.SHUT_WR)
            worker.join(timeout=2)

            self.assertFalse(worker.is_alive())
            self.assertEqual(1, len(errors))
            self.assertIsInstance(errors[0], EOFError)

    def test_oversized_packet_is_rejected_before_encoding(self):
        payload = bytes(ProtocolConstants.MAX_PACKET_SIZE)
        header = PacketHeader(2, MessageType.CHAT_MESSAGE, 0, 0, 1, len(payload), 1, 0)
        with self.assertRaisesRegex(ValueError, "maximum size"):
            PacketCodec.encode(Packet(header, payload))


if __name__ == "__main__":
    unittest.main()
