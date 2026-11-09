from dataclasses import dataclass

@dataclass(frozen=True)
class FileChunk:
    file_id: str
    chunk_order: int
    chunk_data: bytes

    def __post_init__(self):
        if not isinstance(self.file_id, str):
            raise TypeError("file_id must be a string")
        if not self.file_id:
            raise ValueError("file_id must not be empty")

        if type(self.chunk_order) is not int:
            raise TypeError("chunk_order must be an integer")
        if self.chunk_order < 0:
            raise ValueError("chunk_order must be non-negative")

        if type(self.chunk_data) is not bytes:
            raise TypeError("chunk_data must be bytes")
        if len(self.chunk_data) > 1024 * 1024:
            raise ValueError("chunk_data must not exceed 1 MB")

    def get_file_id(self) -> str:
        return self.file_id

    def get_chunk_order(self) -> int:
        return self.chunk_order

    def get_chunk_data(self) -> bytes:
        return self.chunk_data