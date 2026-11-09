
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorFile:
    file_id: str
    error_code: int
    error_message: str

    def __post_init__(self):
        if not isinstance(self.file_id, str):
            raise TypeError("file_id must be a string")

        if type(self.error_code) is not int:
            raise TypeError("error_code must be an integer")

        if not isinstance(self.error_message, str):
            raise TypeError("error_message must be a string")
