import hashlib
import os
import threading

from pathlib import Path

from common.ProtocolConstants import ProtocolConstants

class FileIO:
    def __init__(self):
        self.source = None
        self.lock = threading.Lock()

    def open_source(self, file_path: str) -> tuple[str, int]:
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
            return file_name, file_size

    def calculate_hash(self) -> str:
        with self.lock:
            if self.source is None:
                raise RuntimeError("No file is currently open")

            original_position: int = self.source.tell()
            try:
                self.source.seek(0)
                hasher = hashlib.sha256()

                while block := self.source.read(1024 * 1024):
                    hasher.update(block)

                return hasher.hexdigest()
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