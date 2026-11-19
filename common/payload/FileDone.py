from dataclasses import dataclass

from common.payload.FileID import validate_file_id

@dataclass(frozen=True)
class FileDone:
    file_id: str

    def __post_init__(self):
        validate_file_id(self.file_id)

    def get_file_id(self) -> str:
        return self.file_id
