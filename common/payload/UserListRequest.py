
from dataclasses import dataclass


@dataclass(frozen=True)
class UserListRequest:
    session_id: str
    cursor: str | None = None

    def __post_init__(self):
        if not isinstance(self.session_id, str):
            raise TypeError("session_id must be a string")

        if not self.session_id:
            raise ValueError("session_id must not be empty")

        if self.cursor is not None:
            if not isinstance(self.cursor, str):
                raise TypeError("cursor must be a string or None")

    def get_session_id(self) -> str:
        return self.session_id

    def get_cursor(self) -> str | None:
        return self.cursor