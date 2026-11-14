"""
tests.test_packet_codec
~~~~~~~~~~~~~~~~~~~~~~~

Integration tests for packet encoding and decoding.

Tests that the PacketCodec can correctly encode and decode packets,
preserve all header fields, and reject invalid inputs.

Run from project root:
    python -m unittest tests.test_packet_codec -v
"""

import struct
import unittest

from common.MessageType import MessageType
from common.Packet import Packet
from common.PacketCodec import PacketCodec
from common.PacketHeader import PacketHeader
from common.ProtocolConstants import ProtocolConstants


def make_packet(payload: bytes) -> Packet:
    """Helper: build a valid packet with the given payload."""
    return Packet(
        PacketHeader(
            ProtocolConstants.PROTOCOL_VERSION,
            MessageType.CHAT_MESSAGE,
            0,          # flags
            1,          # stream_id
            1,          # sequence_number
            len(payload),
            1,          # sender_id
            2,          # receiver_id
        ),
        payload,
    )


class TestPacketCodecEncode(unittest.TestCase):
    """Tests for PacketCodec.encode()."""

    def test_encode_returns_bytes(self):
        """Encoded result must be bytes."""
        result = PacketCodec.encode(make_packet(b"hello"))
        self.assertIsInstance(result, bytes)

    def test_encode_length_is_header_plus_payload(self):
        """Wire length = HEADER_SIZE + len(payload)."""
        payload = b"test"
        result = PacketCodec.encode(make_packet(payload))
        self.assertEqual(len(result), ProtocolConstants.HEADER_SIZE + len(payload))

    def test_encode_zero_payload(self):
        """Zero-length payload encodes to exactly HEADER_SIZE bytes."""
        result = PacketCodec.encode(make_packet(b""))
        self.assertEqual(len(result), ProtocolConstants.HEADER_SIZE)

    def test_encode_rejects_none(self):
        """None packet must raise an error."""
        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.encode(None)

    def test_encode_rejects_oversized_payload(self):
        """Payload that exceeds the max size must be rejected."""
        big_payload = bytes(ProtocolConstants.MAX_PACKET_SIZE)  # too large
        header = PacketHeader(
            ProtocolConstants.PROTOCOL_VERSION,
            MessageType.CHAT_MESSAGE,
            0, 1, 1, len(big_payload), 1, 2,
        )
        with self.assertRaisesRegex((ValueError, Exception), r"(?i)size|maximum"):
            PacketCodec.encode(Packet(header, big_payload))

    def test_encode_rejects_invalid_version(self):
        """Wrong protocol version must be rejected."""
        header = PacketHeader(99, MessageType.CHAT_MESSAGE, 0, 1, 1, 0, 1, 2)
        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.encode(Packet(header, b""))

    def test_encode_rejects_invalid_message_type(self):
        """Unknown message type must be rejected."""
        header = PacketHeader(
            ProtocolConstants.PROTOCOL_VERSION, 99, 0, 1, 1, 0, 1, 2
        )
        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.encode(Packet(header, b""))


class TestPacketCodecDecode(unittest.TestCase):
    """Tests for PacketCodec.decode()."""

    def test_decode_returns_packet(self):
        """decode() must return a Packet object."""
        wire = PacketCodec.encode(make_packet(b"hi"))
        result = PacketCodec.decode(wire)
        self.assertIsNotNone(result)

    def test_decode_rejects_none(self):
        """None data must raise an error."""
        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.decode(None)

    def test_decode_rejects_too_short(self):
        """Data shorter than HEADER_SIZE must be rejected."""
        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.decode(bytes(ProtocolConstants.HEADER_SIZE - 1))

    def test_decode_rejects_oversized(self):
        """Data larger than MAX_PACKET_SIZE must be rejected."""
        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.decode(bytes(ProtocolConstants.MAX_PACKET_SIZE + 1))


class TestPacketCodecRoundTrip(unittest.TestCase):
    """Tests for encode → decode round-trip correctness."""

    def _roundtrip(self, payload: bytes) -> Packet:
        return PacketCodec.decode(PacketCodec.encode(make_packet(payload)))

    def test_roundtrip_binary_payload(self):
        """Binary payload must survive encode/decode unchanged."""
        payload = bytes(range(256)) * 3  # 768 bytes of varied data
        result = self._roundtrip(payload[:ProtocolConstants.MAX_PACKET_SIZE - ProtocolConstants.HEADER_SIZE])
        self.assertEqual(payload[:ProtocolConstants.MAX_PACKET_SIZE - ProtocolConstants.HEADER_SIZE],
                         result.getPayload())

    def test_roundtrip_empty_payload(self):
        """Empty payload must survive round-trip."""
        result = self._roundtrip(b"")
        self.assertEqual(b"", result.getPayload())

    def test_roundtrip_preserves_message_type(self):
        """Message type must be preserved after encode/decode."""
        original = make_packet(b"abc")
        decoded = PacketCodec.decode(PacketCodec.encode(original))
        self.assertEqual(
            original.getHeader().getMessageType(),
            decoded.getHeader().getMessageType(),
        )

    def test_roundtrip_all_valid_message_types(self):
        """Every defined message type (1–20) must round-trip successfully."""
        for msg_type in range(1, 21):
            with self.subTest(msg_type=msg_type):
                header = PacketHeader(
                    ProtocolConstants.PROTOCOL_VERSION,
                    msg_type, 0, 1, 1, 0, 1, 2,
                )
                pkt = Packet(header, b"")
                decoded = PacketCodec.decode(PacketCodec.encode(pkt))
                self.assertEqual(msg_type, decoded.getHeader().getMessageType())


if __name__ == "__main__":
    unittest.main()
