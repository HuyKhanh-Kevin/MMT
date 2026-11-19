"""Python port of the file chunking, corruption, and ordering scenarios.

Run from the project root with:
    python -m unittest test.integration.FileIntegrityTest -v
"""

import hashlib
import math
import unittest

from common.ErrorCode import ErrorCode


CHUNK_SIZE = 1024


def split_chunks(data: bytes, chunk_size: int = CHUNK_SIZE) -> list[tuple[int, bytes]]:
    return [
        (index, data[start : start + chunk_size])
        for index, start in enumerate(range(0, len(data), chunk_size))
    ]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FileIntegrityTest(unittest.TestCase):
    def test_normal_file_chunking_and_reassembly(self):
        content = (
            "Distributed Streaming File Transfer Test Content "
            "HCMUT Computer Networks Assignment 1 - Chunking and Verification "
        ).encode("utf-8") * 25
        chunks = split_chunks(content)

        self.assertEqual(math.ceil(len(content) / CHUNK_SIZE), len(chunks))
        self.assertTrue(all(len(chunk) <= CHUNK_SIZE for _, chunk in chunks))
        self.assertEqual(content, b"".join(chunk for _, chunk in chunks))
        self.assertEqual(sha256(content), sha256(b"".join(c for _, c in chunks)))

    def test_corrupted_chunk_triggers_file_hash_mismatch_code(self):
        content = "Secure Network Programming Assignment HCMUT".encode() * 30
        expected_hash = sha256(content)
        chunks = split_chunks(content, 500)
        corrupted = bytearray(chunks[1][1])
        corrupted[10] ^= 0xFF
        received = chunks[0][1] + bytes(corrupted) + b"".join(
            chunk for _, chunk in chunks[2:]
        )

        self.assertNotEqual(expected_hash, sha256(received))
        triggered = (
            0 if expected_hash == sha256(received)
            else ErrorCode.get_error_code(3002).code
        )
        self.assertEqual(3002, triggered)

    def test_out_of_order_chunks_reassemble_by_chunk_index(self):
        chunks = [
            (0, b"Chunk0-Data | "),
            (1, b"Chunk1-Data | "),
            (2, b"Chunk2-Data | "),
            (3, b"Chunk3-Data"),
        ]
        expected = b"".join(data for _, data in chunks)
        received_out_of_order = [chunks[i] for i in (2, 0, 3, 1)]
        rebuilt = b"".join(data for _, data in sorted(received_out_of_order))

        self.assertEqual(sha256(expected), sha256(rebuilt))


if __name__ == "__main__":
    unittest.main()
