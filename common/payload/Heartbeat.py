from dataclasses import dataclass

@dataclass(frozen=True)
class Heartbeat:
    session_id: str
    heartbeat_seq_num: int


    def get_heartbeat_seq_num(self) -> int:
        return self.heartbeat_seq_num

    def get_session_id(self) -> str:
        return self.session_id