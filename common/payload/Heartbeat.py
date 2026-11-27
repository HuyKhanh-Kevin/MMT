from dataclasses import dataclass

@dataclass(frozen=True)
class Heartbeat:
    session_id: str
    heartbeat_seq: int

    def __post_init__(self):
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise ValueError("session_id must not be blank")
        if type(self.heartbeat_seq) is not int or not 1 <= self.heartbeat_seq <= 0xFFFFFFFF:
            raise ValueError("heartbeat_seq must be in 1..4294967295")

    @property
    def heartbeat_seq_num(self) -> int:

        return self.heartbeat_seq


    def get_heartbeat_seq_num(self) -> int:
        return self.heartbeat_seq

    def get_session_id(self) -> str:
        return self.session_id
