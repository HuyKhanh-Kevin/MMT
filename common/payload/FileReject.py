from common.payload.FileID import validate_file_id
from dataclass import dataclass

@dataclass(frozen=True)
class FileReject:
    file_id: str
    error_code: int
    error_message: str

    def __post_init__(self):
        validate_file_id(self.file_id)
        if not isinstance(self.file_id, str):
            raise TypeError("file_id must be a string")

        if type(self.error_code) is not int:
            raise TypeError("error_code must be an integer")

        if not isinstance(self.error_message, str):
            raise TypeError("error_message must be a string")

    def get_file_id(self) -> str:
        return self.file_id

    def get_error_code(self) -> int:
        return self.error_code

    def get_error_message(self) -> str:
        return self.error_message