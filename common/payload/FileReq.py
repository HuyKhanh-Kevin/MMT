
from dataclasses import dataclass


@dataclass(frozen=True)
class FileReq:
    file_id: int
    file_name: str
    file_size: int
    total_chunks: int
    checksum: str

    def __post_init__(self):
        if type(self.file_id) is not int or self.file_id < 0:
            raise ValueError("Invalid file ID")

        if not isinstance(self.file_name, str) or not self.file_name:
            raise ValueError("File name must be a non-empty string")

        if type(self.file_size) is not int or self.file_size < 0:
            raise ValueError("File size must be a non-negative integer")

        if type(self.total_chunks) is not int or self.total_chunks < 0:
            raise ValueError("Total chunks must be non-negative")

        if not isinstance(self.checksum, str) or not self.checksum:
            raise ValueError("Checksum must be a non-empty string")

    def get_file_id(self) -> int:
        return self.file_id

    def get_file_name(self) -> str:
        return self.file_name

    def get_file_size(self) -> int:
        return self.file_size

    def get_total_chunks(self) -> int:
        return self.total_chunks

    def get_checksum(self) -> str:
        return self.checksum