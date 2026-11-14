"""Tests for UUID consistency across file-transfer payloads and chunks.

Run from the project root with:
    python -m unittest test.common.FileTransferPayloadTest -v
"""

import struct
import unittest
import uuid

from common.FileChunkCodec import FileChunkCodec
from common.JsonPayloadCodec import JsonPayloadCodec
from common.ProtocolConstants import ProtocolConstants
from common.payload.FileAccept import FileAccept
from common.payload.FileChunk import FileChunk
from common.payload.FileDone import FileDone
from common.payload.FileReject import FileReject
from common.payload.FileReq import FileReq
from common.payload.FileID import new_file_id
from common.payload.ReqResend import ReqResend


FILE_ID = "550e8400-e29b-41d4-a716-446655440000"


class FileTransferPayloadTest(unittest.TestCase):
    def test_one_uuid_is_shared_by_all_file_control_payloads(self):
        file_id = new_file_id()
        payloads = (
            FileReq(file_id, "document.txt", 12, 1, "abc123"),
            FileAccept(file_id),
            FileReject(file_id, 3001, "Too large"),
            FileDone(file_id),
            ReqResend(file_id, False, [1, 3]),
        )

        for payload in payloads:
            with self.subTest(payload=type(payload).__name__):
                self.assertEqual(file_id, payload.file_id)
                decoded = JsonPayloadCodec.decode(
                    JsonPayloadCodec.encode(payload), type(payload)
                )
                self.assertEqual(payload, decoded)

    def test_file_req_getter_returns_the_uuid_string(self):
        request = FileReq(FILE_ID, "document.txt", 12, 1, "abc123")
        self.assertEqual(FILE_ID, request.get_file_id())
        self.assertIsInstance(request.get_file_id(), str)

    def test_all_file_control_payloads_reject_non_v4_ids(self):
        invalid_ids = (
            "not-a-uuid",
            "550e8400-e29b-11d4-a716-446655440000",  # UUIDv1
            "550E8400-E29B-41D4-A716-446655440000",  # Non-canonical case
        )
        for file_id in invalid_ids:
            for factory in (
                lambda value: FileReq(value, "document.txt", 12, 1, "abc"),
                FileAccept,
                lambda value: FileReject(value, 3001, "Rejected"),
                FileDone,
                lambda value: ReqResend(value, False, []),
            ):
                with self.subTest(file_id=file_id, factory=factory):
                    with self.assertRaises(ValueError):
                        factory(file_id)

    def test_file_chunk_metadata_is_uuid16_order4_length4(self):
        chunk = FileChunk(FILE_ID, 7, b"abc")
        encoded = FileChunkCodec.encode(chunk)
        expected_metadata = struct.pack(
            ">16sII", uuid.UUID(FILE_ID).bytes, 7, 3
        )

        self.assertEqual(24, ProtocolConstants.CHUNK_METADATA_SIZE)
        self.assertEqual(expected_metadata, encoded[:24])
        self.assertEqual(b"abc", encoded[24:])
        self.assertEqual(27, len(encoded))

        decoded = FileChunkCodec.decode(encoded)
        self.assertEqual(chunk, decoded)
        self.assertEqual(FILE_ID, decoded.file_id)

    def test_file_chunk_accepts_generated_uuid_and_boundary_payload_sizes(self):
        file_id = new_file_id()
        for data in (b"", b"x", bytes(ProtocolConstants.MAX_CHUNK_DATA_SIZE)):
            with self.subTest(size=len(data)):
                original = FileChunk(file_id, 0x7FFFFFFF, data)
                decoded = FileChunkCodec.decode(FileChunkCodec.encode(original))
                self.assertEqual(original, decoded)

    def test_file_chunk_codec_rejects_invalid_metadata(self):
        with self.assertRaises(ValueError):
            FileChunkCodec.decode(bytes(23))

        # UUIDv1 bytes are not valid file transfer IDs.
        v1_id = uuid.uuid1()
        invalid_version = struct.pack(
            ">16sII", v1_id.bytes, 0, 0
        )
        with self.assertRaises(ValueError):
            FileChunkCodec.decode(invalid_version)

        bad_length = struct.pack(
            ">16sII", uuid.UUID(FILE_ID).bytes, 0, 1
        )
        with self.assertRaises(ValueError):
            FileChunkCodec.decode(bad_length)

        with self.assertRaises(ValueError):
            FileChunk(FILE_ID, -1, b"")
        with self.assertRaises(ValueError):
            FileChunk(FILE_ID, 0, bytes(ProtocolConstants.MAX_CHUNK_DATA_SIZE + 1))


if __name__ == "__main__":
    unittest.main()
