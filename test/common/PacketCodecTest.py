"""Tests for common/PacketCodec.py with message types 1..20.

Run from project root (D:/MMT):
    python -m unittest test.common.PacketCodecTest -v
"""

import struct
import unittest

from common.MessageType import MessageType
from common.Packet import Packet
from common.PacketCodec import PacketCodec
from common.PacketHeader import PacketHeader
from common.ProtocolConstants import ProtocolConstants


def _message_type_code(value):
    """Accept numeric or hex-string message constants during Java-to-Python migration."""
    return int(value, 0) if isinstance(value, str) else int(value)


def _header(packet):
    return packet.header if hasattr(packet, "header") else packet.getHeader()


def _payload(packet):
    return packet.payload if hasattr(packet, "payload") else packet.getPayload()


HEADER_FIELDS = {
    "version": ("version", "getVersion"),
    "message_type": ("message_type", "messageType", "getMessageType"),
    "flags": ("flags", "getFlags"),
    "stream_id": ("stream_id", "streamID", "getStreamID", "getStreamId"),
    "sequence_number": ("sequence_number", "sequenceNumber", "getSequenceNumber"),
    "payload_length": ("payload_length", "payloadLength", "getPayloadLength"),
    "sender_id": ("sender_id", "senderID", "getSenderID", "getSenderId"),
    "receiver_id": ("receiver_id", "receiverID", "getReceiverID", "getReceiverId"),
}


def _read_field(header, names):
    for name in names:
        if hasattr(header, name):
            value = getattr(header, name)
            return value() if callable(value) else value
    raise AttributeError(f"Cannot find any of these header fields: {names}")


class PacketCodecTest(unittest.TestCase):
    @staticmethod
    def packet(payload: bytes) -> Packet:
        # Constructor order: payload_length BEFORE sender_id and receiver_id.
        return Packet(
            PacketHeader(
                2,
                _message_type_code(MessageType.CHAT_MESSAGE),
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
        expected_header = _header(expected)
        actual_header = _header(actual)
        for field_name, aliases in HEADER_FIELDS.items():
            with self.subTest(field=field_name):
                self.assertEqual(
                    _read_field(expected_header, aliases),
                    _read_field(actual_header, aliases),
                )
        self.assertEqual(_payload(expected), _payload(actual))

    def test_round_trip_preserves_every_field_and_binary_payload(self):
        original = self.packet(bytes([0, 1, 127, 128, 255]))
        decoded = PacketCodec.decode(PacketCodec.encode(original))
        self.assert_packet_equals(original, decoded)

    def test_wire_matches_independent_24_byte_big_endian_example(self):
        expected_wire = bytes.fromhex(
            "020312340102030405060708111213142122232400000003616263"
        )
        original = self.packet(b"abc")
        self.assertEqual(24, ProtocolConstants.HEADER_SIZE)
        self.assertEqual(expected_wire, PacketCodec.encode(original))
        self.assert_packet_equals(original, PacketCodec.decode(expected_wire))

    def test_zero_length_payload_round_trip(self):
        original = self.packet(b"")
        encoded = PacketCodec.encode(original)
        self.assertEqual(24, len(encoded))
        self.assert_packet_equals(original, PacketCodec.decode(encoded))

    def test_packet_size_boundary(self):
        # PacketCodec checks the outer envelope; JSON has its own size cap.
        at_limit = PacketCodec.encode(self.packet(bytes(1176)))
        self.assertEqual(1200, len(at_limit))
        self.assertEqual(1176, len(_payload(PacketCodec.decode(at_limit))))

        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.encode(self.packet(bytes(1177)))

        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.decode(bytes(1201))

    def test_reject_null_and_incomplete_header(self):
        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.encode(None)
        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.decode(None)
        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.decode(bytes(23))

    def test_reject_mismatch_on_encode(self):
        original = Packet(
            PacketHeader(2, 3, 0, 1, 1, 99, 1, 2),
            bytes(3),
        )
        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.encode(original)

    def test_reject_negative_or_mismatched_length_on_decode(self):
        for length in (-1, 2, 4):
            with self.subTest(payload_length=length):
                wire = bytearray(PacketCodec.encode(self.packet(bytes(3))))
                struct.pack_into(">i", wire, 20, length)
                with self.assertRaises((ValueError, TypeError)):
                    PacketCodec.decode(bytes(wire))

    def test_reject_unknown_version_and_message_type(self):
        wrong_version = bytearray(PacketCodec.encode(self.packet(b"")))
        wrong_version[0] = 99
        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.decode(bytes(wrong_version))

        wrong_type = bytearray(PacketCodec.encode(self.packet(b"")))
        wrong_type[1] = 21  # Current protocol only defines message types 1..20.
        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.decode(bytes(wrong_type))

        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.encode(Packet(PacketHeader(99, 3, 0, 0, 0, 0, 0, 0), b""))
        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.encode(Packet(PacketHeader(2, 21, 0, 0, 0, 0, 0, 0), b""))

        # 9 = FILE_CHUNK in the current protocol and must be accepted.
        file_chunk_packet = Packet(
            PacketHeader(2, MessageType.FILE_CHUNK, 0, 0, 0, 0, 0, 0), b""
        )
        self.assert_packet_equals(
            file_chunk_packet,
            PacketCodec.decode(PacketCodec.encode(file_chunk_packet))
        )

    def test_unsigned_flags_boundary(self):
        for flags in (0, 65535):
            with self.subTest(flags=flags):
                original = Packet(PacketHeader(2, 3, flags, 0, 0, 0, 0, 0), b"")
                self.assert_packet_equals(original, PacketCodec.decode(PacketCodec.encode(original)))

        # Python PacketHeader may reject invalid flags during construction
        # rather than waiting for PacketCodec.encode(), and either is fine.
        for flags in (-1, 65536):
            with self.subTest(flags=flags):
                with self.assertRaises((ValueError, TypeError)):
                    original = Packet(PacketHeader(2, 3, flags, 0, 0, 0, 0, 0), b"")
                    PacketCodec.encode(original)

    def test_packet_payload_is_immutable(self):
        # Java byte[] is mutable, hence its defensive-copy test.
        # In Python, bytes is immutable: keeping the same bytes object is safe.
        original = bytes([1, 2, 3])
        packet = self.packet(original)
        self.assertIsInstance(_payload(packet), bytes)
        with self.assertRaises(TypeError):
            original[0] = 9
        with self.assertRaises(TypeError):
            _payload(packet)[1] = 9
        self.assertEqual(bytes([1, 2, 3]), _payload(packet))


if __name__ == "__main__":
    unittest.main()
