"""Tests for PacketHeader field validation and unsigned wire encoding.

Run from the project root with:
    python -m unittest test.common.PacketHeaderTest -v
"""

import struct
import unittest

from common.PacketHeader import PacketHeader


FIELD_WIDTHS = {
    "version": 8,
    "messageType": 8,
    "flags": 16,
    "streamID": 32,
    "sequenceNumber": 32,
    "payloadLength": 32,
    "senderID": 32,
    "receiverID": 32,
}

DEFAULT_FIELDS = {
    "version": 2,
    "messageType": 3,
    "flags": 0,
    "streamID": 0,
    "sequenceNumber": 0,
    "payloadLength": 0,
    "senderID": 0,
    "receiverID": 0,
}


def make_header(**overrides):
    values = {**DEFAULT_FIELDS, **overrides}
    return PacketHeader(**values)


class PacketHeaderTest(unittest.TestCase):
    def test_size_and_format_match_protocol_header(self):
        self.assertEqual(24, PacketHeader.SIZE)
        self.assertEqual(PacketHeader.SIZE, struct.calcsize(PacketHeader.FORMAT))

    def test_each_field_accepts_unsigned_minimum_and_maximum(self):
        for field, bits in FIELD_WIDTHS.items():
            with self.subTest(field=field, value=0):
                self.assertEqual(0, getattr(make_header(**{field: 0}), field))

            maximum = (1 << bits) - 1
            with self.subTest(field=field, value=maximum):
                self.assertEqual(
                    maximum,
                    getattr(make_header(**{field: maximum}), field),
                )

    def test_each_field_rejects_values_outside_unsigned_range(self):
        for field, bits in FIELD_WIDTHS.items():
            for value in (-1, 1 << bits):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, field):
                        make_header(**{field: value})

    def test_each_field_rejects_non_integer_values_and_booleans(self):
        for field in FIELD_WIDTHS:
            for value in (None, "1", 1.5, True, False):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, field):
                        make_header(**{field: value})

    def test_wire_bytes_use_unsigned_big_endian_field_order(self):
        header = PacketHeader(
            version=2,
            messageType=3,
            flags=0x1234,
            streamID=0x01020304,
            sequenceNumber=0x05060708,
            payloadLength=0x31323334,
            senderID=0x11121314,
            receiverID=0x21222324,
        )
        expected = bytes.fromhex(
            "020312340102030405060708111213142122232431323334"
        )

        self.assertEqual(expected, header.toBytes())

    def test_from_bytes_round_trip_preserves_all_fields(self):
        original = PacketHeader(
            version=2,
            messageType=20,
            flags=0xFFFF,
            streamID=0xFFFFFFFF,
            sequenceNumber=0x80000000,
            payloadLength=0xFFFFFFFF,
            senderID=0x01020304,
            receiverID=0xA0B0C0D0,
        )

        decoded = PacketHeader.fromBytes(original.toBytes())

        for field in FIELD_WIDTHS:
            with self.subTest(field=field):
                self.assertEqual(getattr(original, field), getattr(decoded, field))

    def test_from_bytes_rejects_incomplete_header(self):
        for length in (0, 1, PacketHeader.SIZE - 1):
            with self.subTest(length=length):
                with self.assertRaisesRegex(ValueError, "Data too short"):
                    PacketHeader.fromBytes(bytes(length))


if __name__ == "__main__":
    unittest.main()
