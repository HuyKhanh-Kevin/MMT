"""Tests for generated and validated UUIDv4 file transfer IDs.

Run from the project root with:
    python -m unittest test.common.FileIDTest -v
"""

import unittest
import uuid

from common.FileChunkCodec import FileChunkCodec
from common.payload.FileAccept import FileAccept
from common.payload.FileChunk import FileChunk
from common.payload.FileID import new_file_id, validate_file_id


class FileIDTest(unittest.TestCase):
    def test_new_file_id_returns_canonical_uuid_v4(self):
        file_id = new_file_id()

        self.assertEqual(file_id, validate_file_id(file_id))
        self.assertEqual(str(uuid.UUID(file_id)), file_id)
        self.assertEqual(4, uuid.UUID(file_id).version)
        self.assertEqual(36, len(file_id))

    def test_validate_returns_valid_canonical_uuid_v4_unchanged(self):
        file_id = "550e8400-e29b-41d4-a716-446655440000"
        self.assertEqual(file_id, validate_file_id(file_id))

    def test_validate_rejects_non_strings_and_invalid_uuid_forms(self):
        invalid_ids = (
            None,
            123,
            "",
            "not-a-uuid",
            "550e8400e29b41d4a716446655440000",  # Not canonical form.
            "550E8400-E29B-41D4-A716-446655440000",  # Uppercase.
            "550e8400-e29b-11d4-a716-446655440000",  # UUIDv1.
            "00000000-0000-0000-0000-000000000000",
        )
        for file_id in invalid_ids:
            with self.subTest(file_id=file_id):
                with self.assertRaises((TypeError, ValueError)):
                    validate_file_id(file_id)

    def test_generated_id_is_accepted_by_file_payloads_and_chunk_codec(self):
        file_id = new_file_id()

        accepted = FileAccept(file_id)
        self.assertEqual(file_id, accepted.file_id)

        original = FileChunk(file_id, 3, b"chunk data")
        decoded = FileChunkCodec.decode(FileChunkCodec.encode(original))
        self.assertEqual(file_id, decoded.file_id)
        self.assertEqual(original, decoded)

    def test_file_payloads_reject_invalid_id(self):
        for file_id in ("bad-id", "550e8400-e29b-11d4-a716-446655440000"):
            with self.subTest(file_id=file_id):
                with self.assertRaises(ValueError):
                    FileAccept(file_id)
                with self.assertRaises(ValueError):
                    FileChunk(file_id, 0, b"")


if __name__ == "__main__":
    unittest.main()
