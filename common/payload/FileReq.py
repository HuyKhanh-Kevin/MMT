
from dataclasses import dataclass

from common.payload.FileID import validate_file_id


@dataclass(frozen=True)
class FileReq:
    file_id: str
    file_name: str
    file_size: int
    checksum: str
    sender_udp_port: int

    def __post_init__(self):
        validate_file_id(self.file_id)

        if not isinstance(self.file_name, str) or not self.file_name:
            raise ValueError("File name must be a non-empty string")

        if type(self.file_size) is not int or self.file_size < 0:
            raise ValueError("File size must be a non-negative integer")

        if not isinstance(self.checksum, str) or not self.checksum:
            raise ValueError("Checksum must be a non-empty string")

        if type(self.sender_udp_port) is not int or not 1 <= self.sender_udp_port <= 65535:
            raise ValueError("Sender UDP port must be between 1 and 65535")

    def get_file_id(self) -> str:
        return self.file_id

    def get_file_name(self) -> str:
        return self.file_name

    def get_file_size(self) -> int:
        return self.file_size

    def get_checksum(self) -> str:
        return self.checksum

    def get_sender_udp_port(self) -> int:
        return self.sender_udp_port
