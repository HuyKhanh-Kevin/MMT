
from dataclasses import dataclass


@dataclass(frozen=True)
class SignupResponse:
    status: str
    reason: str | None

    def __post_init__(self):
        if not isinstance(self.status, str):
            raise TypeError("Status must be a string")

        if self.status not in ("success", "failed"):
            raise ValueError("Status must be 'success' or 'failed'")

        if self.status == "success":
            if self.reason is not None:
                raise ValueError(
                    "Reason must be null when signup succeeds"
                )

        if self.status == "failed":
            if (
                not isinstance(self.reason, str)
                or not self.reason.strip()
            ):
                raise ValueError(
                    "Reason must not be blank when signup fails"
                )

    def get_status(self) -> str:
        return self.status

    def get_reason(self) -> str | None:
        return self.reason