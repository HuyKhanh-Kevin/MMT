from dataclasses import dataclass

@dataclass(frozen=True)
class LogoutResponse:
    status : str

    def __post_init__(self):
        if not isinstance(self.status, str):
            raise TypeError("status must be a string")
        if self.status != "success":
            raise ValueError("Logout status must be success")

    def get_status(self) -> str:
        return self.status
