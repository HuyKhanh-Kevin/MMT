from dataclasses import dataclass

@dataclass(frozen=True)
class FileAccept:
    file_id: str
    def __post_init__(self):
        if not isinstance(self.file_id, str):
            raise TypeError("file_id must be a string")
        if not self.file_id:
            raise ValueError("file_id must not be empty")

    def get_file_id(self) -> str:
        return self.file_id