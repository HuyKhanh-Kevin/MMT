
from dataclasses import dataclass


@dataclass(frozen=True)
class PeerEndpoint:
    user_id: int
    username: str
    tcp: tuple[str, int]
    file_udp: tuple[str, int]

    def __post_init__(self):
        if (
            type(self.user_id) is not int
            or not 1 <= self.user_id <= 0xFFFFFFFF
        ):
            raise ValueError("Invalid user ID")

        if not isinstance(self.username, str) or not self.username:
            raise ValueError("Invalid username")

        self._validate_address(self.tcp, "tcp")
        self._validate_address(self.file_udp, "file_udp")

    @staticmethod
    def _validate_address(address, name):
        if (
            not isinstance(address, tuple)
            or len(address) != 2
            or not isinstance(address[0], str)
            or not address[0]
            or type(address[1]) is not int
            or not 1 <= address[1] <= 65535
        ):
            raise ValueError(f"Invalid {name} address")
