
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMessage:
    text: str

    def __post_init__(self):
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")

        if not self.text:
            raise ValueError("text must not be empty")

        if len(self.text.encode("utf-8")) > 1000:
            raise ValueError("text must not exceed 1000 UTF-8 bytes")
