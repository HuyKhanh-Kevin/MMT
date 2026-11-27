from dataclasses import dataclass


@dataclass(frozen=True)
class UserInfo:
    username: str
    status: str
    user_id: int
    ip: str
    tcp_port: int
    file_udp_port: int

    def __post_init__(self):
        if (
            not isinstance(self.username, str)
            or not 1 <= len(self.username) <= 32
            or not self.username.isascii()
        ):
            raise ValueError(
                "Username must contain 1-32 ASCII characters"
            )

        if self.status != "online":
            raise ValueError("Status must be online")


        if (
            type(self.user_id) is not int
            or not 1 <= self.user_id <= 0xFFFFFFFF
        ):
            raise ValueError(
                "User ID must be between 1 and 4294967295"
            )


        if (
            not isinstance(self.ip, str)
            or not self.ip.strip()
        ):
            raise ValueError("Invalid peer IP")


        if (
            type(self.tcp_port) is not int
            or not 1 <= self.tcp_port <= 65535
            or type(self.file_udp_port) is not int
            or not 1 <= self.file_udp_port <= 65535
        ):
            raise ValueError("Invalid peer endpoint")
