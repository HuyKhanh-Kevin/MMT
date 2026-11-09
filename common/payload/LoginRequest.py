from dataclasses import dataclass

@dataclass(frozen=True)
class LoginRequest:
    username: str
    password: str
    tcp_port: int
    udp_port: int

    def __post_init__(self):
        if not isinstance(self.username, str):
            raise TypeError("username must be a string")
        if not self.username:
            raise ValueError("username must not be empty")

        if not isinstance(self.password, str):
            raise TypeError("password must be a string")
        if not self.password:
            raise ValueError("password must not be empty")

        if not isinstance(self.tcp_port, int):
            raise TypeError("tcp_port must be an integer")
        if self.tcp_port < 0 or self.tcp_port > 65535:
            raise ValueError("tcp_port must be a valid port number")

        if not isinstance(self.udp_port, int):
            raise TypeError("udp_port must be an integer")
        if self.udp_port < 0 or self.udp_port > 65535:
            raise ValueError("udp_port must be a valid port number")

    def get_username(self) -> str:
        return self.username

    def get_password(self) -> str:
        return self.password

    def get_tcp_port(self) -> int:
        return self.tcp_port

    def get_udp_port(self) -> int:
        return self.udp_port