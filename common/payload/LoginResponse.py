from dataclasses import dataclass, asdict
from typing import Optional


@dataclass(frozen=True)
class LoginResponse:
    status: str
    session_id: Optional[str] = None
    user_id: Optional[int] = None
    reason: Optional[str] = None

    def __post_init__(self):

        if type(self.status) is not str or self.status not in ("success", "failed"):
            raise ValueError("Invalid login status")


        if self.session_id is not None and not isinstance(self.session_id, str):
            raise TypeError("session_id must be a string")

        if self.user_id is not None and type(self.user_id) is not int:
            raise TypeError("user_id must be an integer")

        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError("reason must be a string")


        if self.status == "success":
            if not self.session_id or not self.session_id.strip():
                raise ValueError("Successful login requires a valid session_id")

            if self.user_id is None or not (1 <= self.user_id <= 0xFFFFFFFF):
                raise ValueError("Successful login requires a valid user_id")

            if self.reason is not None:
                raise ValueError("Successful login must not have a reason")


        else:
            if self.session_id is not None or self.user_id is not None:
                raise ValueError("Failed login must not contain session_id or user_id")

            if not self.reason or not self.reason.strip():
                raise ValueError("Failed login requires a reason")

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
        return asdict(self)
