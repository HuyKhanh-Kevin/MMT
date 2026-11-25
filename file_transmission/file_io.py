import hashlib
import os
import threading

from pathlib import Path

from common.ProtocolConstants import ProtocolConstants

class FileIO:
    def __init__(self):
        self.file_name = None
        self.file_size = None
        self.file_checksum = None

        self.source = None
        self.destination = None
        self.lock = threading.Lock()

    def open_source(self, file_path: str) -> None:
        with self.lock:
            if self.source is not None:
                raise RuntimeError("File is already open")

            path = Path(file_path)
            source = open(file_path, 'rb')

            file_name = path.name
            try:
                file_size = os.fstat(source.fileno()).st_size
            except OSError:
                source.close()
                raise

            self.source = source
            self.file_name = file_name
            self.file_size = file_size

    def calculate_hash(self) -> None:
        with self.lock:
            if self.source is None:
                raise RuntimeError("No file is currently open")

            original_position: int = self.source.tell()
            try:
                self.source.seek(0)
                hasher = hashlib.sha256()

                while block := self.source.read(1024 * 1024):
                    hasher.update(block)

                self.file_checksum = hasher.hexdigest()
            finally:
                self.source.seek(original_position)

    def read_chunk(self, chunk_index: int, total_chunks: int) -> bytes:
        if not 0 <= chunk_index < total_chunks:
            raise ValueError("Invalid chunk index")

        with self.lock:
            if self.source is None:
                raise RuntimeError("No file is currently open")

            self.source.seek(chunk_index * ProtocolConstants.MAX_CHUNK_DATA_SIZE)
            return self.source.read(ProtocolConstants.MAX_CHUNK_DATA_SIZE)

    def close_source(self) -> None:
        with self.lock:
            if self.source is not None:
                self.source.close()
                self.source = None

    def open_destination(self, file_path: str | Path) -> None:
        with self.lock:
            if self.destination is not None:
                raise RuntimeError("File is already open")

            self.destination = open(file_path, 'x+b')

    def verify_checksum(self, checksum: str) -> bool:
        with self.lock:
            if self.destination is None:
                raise RuntimeError("No file is currently open")

            original_position: int = self.destination.tell()
            try:
                self.destination.seek(0)
                hasher = hashlib.sha256()

                while block := self.destination.read(1024 * 1024):
                    hasher.update(block)

                return hasher.hexdigest() == checksum
            finally:
                self.destination.seek(original_position)

    def write_chunk(self, chunk_index: int, total_chunks: int, file_size: int, chunk_data: bytes) -> None:
        with self.lock:
            if not 0 <= chunk_index < total_chunks:
                raise ValueError("Invalid chunk index")

            if self.destination is None:
                raise RuntimeError("No file is currently open")

            chunk_size = ProtocolConstants.MAX_CHUNK_DATA_SIZE
            expected_size = min(chunk_size, file_size - chunk_index * chunk_size)

            if len(chunk_data) != expected_size:
                raise ValueError("Invalid chunk data length")

            self.destination.seek(chunk_index * chunk_size)
            self.destination.write(chunk_data)

    def close_destination(self) -> None:
        with self.lock:
            if self.destination is not None:
                self.destination.close()
                self.destination = None