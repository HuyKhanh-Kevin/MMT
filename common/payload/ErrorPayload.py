
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorPayload:
    error_code: int
    error_message: str
    related_stream_id: int = 0
    related_sequence_number: int = 0

    def __post_init__(self):
        if type(self.related_stream_id) is not int:
            raise TypeError("related_stream_id must be an integer")

        if type(self.related_sequence_number) is not int:
            raise TypeError("related_sequence_number must be an integer")

        if self.related_stream_id < 0:
            raise ValueError("related_stream_id cannot be negative")

        if self.related_sequence_number < 0:
            raise ValueError("related_sequence_number cannot be negative")

    def get_error_code(self) -> int:
        return self.error_code

    def get_error_message(self) -> str:
        return self.error_message

    def get_related_stream_id(self) -> int:
        return self.related_stream_id

    def get_related_sequence_number(self) -> int:
        return self.related_sequence_number