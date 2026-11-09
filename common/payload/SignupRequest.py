
from dataclasses import dataclass


@dataclass(frozen=True)
class SignupRequest:
    username: str
    password: str

    def __post_init__(self):
        if (
            not isinstance(self.username, str)
            or not 1 <= len(self.username) <= 32
            or not self.username.isascii()
        ):
            raise ValueError(
                "Username must contain 1–32 ASCII characters"
            )

        if not isinstance(self.password, str):
            raise TypeError("Password must be a string")

        if not self.password:
            raise ValueError("Password must not be null or empty")

    def get_username(self) -> str:
        return self.username

    def get_password(self) -> str:
        return self.password

    