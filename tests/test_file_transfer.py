"""
tests.test_file_transfer
~~~~~~~~~~~~~~~~~~~~~~~~

Integration tests for the file streaming and transfer protocol.

Tests cover:
- FileReq, FileAccept, FileReject, and FileDone models
- FileChunkCodec binary serialization and deserialization
- File chunking and reassembly with SHA-256 integrity check
- Handling out-of-order chunks
- Detection of corrupted chunks and error reporting

Run from project root:
    python -m unittest tests.test_file_transfer -v
"""

import hashlib
import math
import unittest
import uuid

from common.ErrorCode import ErrorCode
from common.FileChunkCodec import FileChunkCodec
from common.MessageType import MessageType
from common.Packet import Packet
from common.PacketCodec import PacketCodec
from common.PacketHeader import PacketHeader
from common.ProtocolConstants import ProtocolConstants
from common.payload.ErrorFile import ErrorFile
from common.payload.FileAccept import FileAccept
from common.payload.FileChunk import FileChunk
from common.payload.FileDone import FileDone
from common.payload.FileReject import FileReject
from common.payload.FileReq import FileReq


def _sha256(data: bytes) -> str:
    """Helper: compute hex SHA-256 digest of bytes."""
    return hashlib.sha256(data).hexdigest()


class TestFileControlPayloads(unittest.TestCase):
    """Tests for FileReq, FileAccept, FileReject, and FileDone control payloads."""

    def setUp(self):
        self.file_id = str(uuid.uuid4())

    def test_file_req_valid(self):
        """FileReq initializes properly with valid metadata."""
        content = b"Sample file payload for assignment"
        checksum = _sha256(content)
        req = FileReq(
            file_id=self.file_id,
            file_name="assignment.pdf",
            file_size=len(content),
            total_chunks=1,
            checksum=checksum,
            sender_udp_port=6001,
        )
        self.assertEqual(self.file_id, req.file_id)
        self.assertEqual("assignment.pdf", req.file_name)
        self.assertEqual(len(content), req.file_size)
        self.assertEqual(1, req.total_chunks)
        self.assertEqual(checksum, req.checksum)

    def test_file_req_rejects_invalid_file_id(self):
        """FileReq rejects non-UUIDv4 strings."""
        with self.assertRaises(ValueError):
            FileReq(
                file_id="invalid-uuid",
                file_name="test.txt",
                file_size=10,
                total_chunks=1,
                checksum="abc",
                sender_udp_port=6001,
            )

    def test_file_accept_valid(self):
        """FileAccept accepts a valid file_id."""
        accept = FileAccept(file_id=self.file_id, buffer_size=11000)
        self.assertEqual(self.file_id, accept.file_id)

    def test_file_reject_valid(self):
        """FileReject contains error code and message."""
        reject = FileReject(
            file_id=self.file_id,
            error_code=3001,
            error_message="Storage quota exceeded",
        )
        self.assertEqual(self.file_id, reject.file_id)
        self.assertEqual(3001, reject.error_code)
        self.assertEqual("Storage quota exceeded", reject.error_message)

    def test_file_done_valid(self):
        """FileDone holds the completed transfer file_id."""
        done = FileDone(file_id=self.file_id)
        self.assertEqual(self.file_id, done.get_file_id())


class TestFileChunkCodec(unittest.TestCase):
    """Tests for FileChunkCodec binary serialization."""

    def setUp(self):
        self.file_id = str(uuid.uuid4())

    def test_chunk_codec_roundtrip(self):
        """A FileChunk encoded to binary must decode back identically."""
        chunk_data = b"Arbitrary chunk content up to 1024 bytes"
        original = FileChunk(
            file_id=self.file_id,
            payload_data=chunk_data,
        )
        raw_wire = FileChunkCodec.encode(original)
        # Expected size: 20 bytes metadata (16 UUID + 4 length) + payload
        self.assertEqual(20 + len(chunk_data), len(raw_wire))

        decoded = FileChunkCodec.decode(raw_wire)
        self.assertEqual(original.file_id, decoded.file_id)
        self.assertEqual(original.payload_data, decoded.payload_data)

    def test_chunk_codec_max_size(self):
        """1024 bytes (MAX_CHUNK_DATA_SIZE) must encode successfully."""
        max_data = b"X" * ProtocolConstants.MAX_CHUNK_DATA_SIZE
        chunk = FileChunk(self.file_id, max_data)
        encoded = FileChunkCodec.encode(chunk)
        decoded = FileChunkCodec.decode(encoded)
        self.assertEqual(max_data, decoded.payload_data)

    def test_chunk_codec_rejects_oversized_payload(self):
        """Chunk data exceeding 1024 bytes must be rejected."""
        oversized = b"X" * (ProtocolConstants.MAX_CHUNK_DATA_SIZE + 1)
        with self.assertRaises(ValueError):
            FileChunk(self.file_id, oversized)

    def test_chunk_codec_rejects_truncated_metadata(self):
        """Truncated binary chunk must be rejected."""
        with self.assertRaises(ValueError):
            FileChunkCodec.decode(b"too_short")


class TestFileIntegrityAndReassembly(unittest.TestCase):
    """End-to-end file chunking, transmission, reordering, and verification."""

    def setUp(self):
        self.file_id = str(uuid.uuid4())
        # Multi-chunk sample payload: 3500 bytes (> 3 chunks of 1024)
        self.original_data = (
            b"HCMUT Computer Network Assignment 1 - Distributed Streaming Application\n"
            b"Raw TCP Socket File Transfer Chunking Test\n"
        ) * 35
        self.expected_checksum = _sha256(self.original_data)

    def _split_into_file_chunks(self, data: bytes, chunk_size: int = 1024) -> list[FileChunk]:
        chunks = []
        for order, offset in enumerate(range(0, len(data), chunk_size)):
            chunk_bytes = data[offset : offset + chunk_size]
            chunks.append(FileChunk(self.file_id, chunk_bytes))
        return chunks

    def test_normal_chunking_and_reassembly(self):
        """File is correctly partitioned into chunks and rebuilt with matched SHA-256."""
        chunks = self._split_into_file_chunks(self.original_data)
        self.assertEqual(math.ceil(len(self.original_data) / 1024), len(chunks))

        # Encode and decode each chunk
        wire_chunks = [FileChunkCodec.encode(c) for c in chunks]
        decoded_chunks = [FileChunkCodec.decode(w) for w in wire_chunks]

        # Reassemble
        rebuilt_data = b"".join(c.payload_data for c in decoded_chunks)
        self.assertEqual(self.original_data, rebuilt_data)
        self.assertEqual(self.expected_checksum, _sha256(rebuilt_data))

    def test_out_of_order_chunks_reassemble_correctly(self):
        chunks = self._split_into_file_chunks(self.original_data)
        packets = []
        for sequence, chunk in enumerate(chunks):
            payload = FileChunkCodec.encode(chunk)
            packet = Packet(PacketHeader(2, MessageType.FILE_CHUNK, 1, 1,
                                         sequence, len(payload), 1, 2), payload)
            packets.append(PacketCodec.decode(PacketCodec.encode(packet)))
        packets.reverse()
        packets.sort(key=lambda packet: packet.header.sequenceNumber)
        rebuilt_data = b"".join(FileChunkCodec.decode(packet.payload).payload_data
                                for packet in packets)
        self.assertEqual(self.expected_checksum, _sha256(rebuilt_data))

    def test_corrupted_chunk_fails_checksum_verification(self):
        """Corrupting a single bit in a chunk changes the final checksum."""
        chunks = self._split_into_file_chunks(self.original_data)

        # Corrupt one byte in the second chunk
        corrupted_payload = bytearray(chunks[1].payload_data)
        corrupted_payload[0] ^= 0xFF
        corrupted_chunk = FileChunk(self.file_id, bytes(corrupted_payload))

        rebuilt_corrupted = (
            chunks[0].payload_data
            + corrupted_chunk.payload_data
            + b"".join(c.payload_data for c in chunks[2:])
        )

        self.assertNotEqual(self.expected_checksum, _sha256(rebuilt_corrupted))


if __name__ == "__main__":
    unittest.main()
