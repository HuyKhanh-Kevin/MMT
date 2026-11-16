from dataclasses import dataclass

@dataclass(frozen=True)
class LoginRequest:
    username: str
    password: str
    tcp_port: int
    file_udp_port: int

    def __post_init__(self):
        if (
            not isinstance(self.username, str)
            or not 1 <= len(self.username) <= 32
            or not self.username.isascii()
        ):
            raise ValueError("Invalid username")

        if not isinstance(self.password, str) or not self.password:
            raise ValueError("Invalid password")

        for port in (self.tcp_port, self.file_udp_port):
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError("Invalid port")
    def get_username(self) -> str:
        return self.username

    def get_password(self) -> str:
        return self.password

    def get_tcp_port(self) -> int:
        return self.tcp_port

    def get_file_udp_port(self) -> int:
        return self.file_udp_port

    def get_udp_port(self) -> int:

        return self.file_udp_port
