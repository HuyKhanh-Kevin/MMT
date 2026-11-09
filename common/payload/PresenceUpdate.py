from dataclasses import dataclass

@dataclass(frozen=True)
class PresenceUpdate:
    username: str
    user_id: str