from dataclasses import dataclass

@dataclass(frozen=True)
class LogoutRequest:
    session_id: str

    def __post_init__(self):
        if not isinstance(self.session_id, str):
            raise TypeError("session_id must be a string")
        if not self.session_id:
            raise ValueError("session_id must not be empty")

    def get_session_id(self) -> str:
        return self.session_id