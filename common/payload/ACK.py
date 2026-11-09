import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ACK:
    ack_stream_id: int
    ack_seq_num: int

    def __post_init__(self):
        if type(self.ack_stream_id) is not int:
            raise TypeError("ack_stream_id must be an integer")

        if type(self.ack_seq_num) is not int:
            raise TypeError("ack_seq_num must be an integer")

    def get_ack_stream_id(self) -> int:
        return self.ack_stream_id

    def get_ack_seq_num(self) -> int:
        return self.ack_seq_num