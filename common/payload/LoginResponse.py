
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass(frozen=True)
class LoginResponse:
    status: str
    session_id: Optional[str] = None
    user_id: Optional[int] = None
    reason: Optional[str] = None

    def __post_init__(self):
        if self.status not in ("success", "failed"):
            raise ValueError("Invalid login status")

        if self.session_id is not None and not isinstance(self.session_id, str):
            raise TypeError("session_id must be a string")

        if self.user_id is not None and type(self.user_id) is not int:
            raise TypeError("user_id must be an integer")

        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError("reason must be a string")

    @classmethod
    def from_result(
        cls,
        success: bool,
        session_id: Optional[str] = None,
        user_id: Optional[int] = None,
        reason: Optional[str] = None
    ):
        if type(success) is not bool:
            raise TypeError("success must be a boolean")

        return cls(
            status="success" if success else "failed",
            session_id=session_id if success else None,
            user_id=user_id if success else None,
            reason=None if success else reason
        )

    @property
    def is_success(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> dict:
        return {
            key: value
            for key, value in asdict(self).items()
            if value is not None
        }
