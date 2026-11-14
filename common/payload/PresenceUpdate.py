from dataclasses import dataclass

@dataclass(frozen=True)
class PresenceUpdate:
    username: str
    status: str

    def __post_init__(self):
        if (not isinstance(self.username, str) or not self.username.isascii()
                or not 1 <= len(self.username) <= 32):
            raise ValueError("Invalid presence username")
        if self.status not in ("online", "offline"):
            raise ValueError("Presence status must be online or offline")
