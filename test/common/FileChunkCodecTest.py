"""UUIDv4 version of the original FileChunkCodecTest.java test cases.

Run at project root: python -m unittest test.common.FileChunkCodecTest -v
"""

import random
import struct
import unittest
import uuid

from common.FileChunkCodec import FileChunkCodec
from common.ProtocolConstants import ProtocolConstants
from common.payload.FileChunk import FileChunk


FILE_ID = "550e8400-e29b-41d4-a716-446655440000"  # Valid UUIDv4
FILE_ID_BYTES = uuid.UUID(FILE_ID).bytes


class FileChunkCodecTest(unittest.TestCase):
    def test_wire_matches_24_byte_metadata_example(self):
        expected = bytes.fromhex(
            "550e8400e29b41d4a716446655440000"
            "00000007"  # chunk_order = 7
            "00000003"  # payload_length = 3
            "616263"    # payload_data = 'abc'
        )
        chunk = FileChunk(FILE_ID, 7, b"abc")
        self.assertEqual(24, ProtocolConstants.CHUNK_METADATA_SIZE)
        self.assertEqual(expected, FileChunkCodec.encode(chunk))
        decoded = FileChunkCodec.decode(expected)
        self.assertEqual(FILE_ID, decoded.file_id)
        self.assertEqual(7, decoded.chunk_order)
        self.assertEqual(3, decoded.payload_length)
        self.assertEqual(b"abc", decoded.payload_data)

    def test_round_trips_boundary_sizes(self):
        for size in (0, 1, 1024):
            with self.subTest(size=size):
                data = random.Random(42).randbytes(size)
                chunk = FileChunk(FILE_ID, 7, data)
                wire = FileChunkCodec.encode(chunk)
                self.assertEqual(24 + size, len(wire))
                self.assertEqual(chunk, FileChunkCodec.decode(wire))
                self.assertLessEqual(
                    ProtocolConstants.HEADER_SIZE + len(wire),
                    ProtocolConstants.MAX_PACKET_SIZE,
                )

    def test_rejects_bad_length_and_oversize(self):
        with self.assertRaises(ValueError):
            FileChunkCodec.decode(bytes(23))
        with self.assertRaises(ValueError):
            FileChunkCodec.decode(bytes(24 + 1025))
        with self.assertRaises(ValueError):
            FileChunk(FILE_ID, 0, bytes(1025))

        for payload_length in (-1, 3, 1025):
            with self.subTest(payload_length=payload_length):
                malformed = struct.pack(">16sii", FILE_ID_BYTES, 0, payload_length)
                with self.assertRaises(ValueError):
                    FileChunkCodec.decode(malformed)

    def test_rejects_negative_chunk_order_on_both_paths(self):
        with self.assertRaises(ValueError):
            FileChunk(FILE_ID, -1, b"")
        malformed = struct.pack(">16sii", FILE_ID_BYTES, -1, 0)
        with self.assertRaises(ValueError):
            FileChunkCodec.decode(malformed)

    def test_rejects_invalid_uuid(self):
        for invalid_id in (42, "42", "file_001", "", str(uuid.uuid1())):
            with self.subTest(invalid_id=invalid_id):
                with self.assertRaises((TypeError, ValueError)):
                    FileChunk(invalid_id, 0, b"")

        # All-zero bytes are not an RFC 4122 UUIDv4.
        malformed = struct.pack(">16sII", b"\x00" * 16, 0, 0)
        with self.assertRaises(ValueError):
            FileChunkCodec.decode(malformed)

    def test_payload_is_immutable(self):
        data = bytearray(b"abc")
        chunk = FileChunk(FILE_ID, 0, data)
        data[0] = 90
        self.assertEqual(b"abc", chunk.payload_data)
        with self.assertRaises(TypeError):
            chunk.payload_data[0] = 90


if __name__ == "__main__":
    unittest.main()
