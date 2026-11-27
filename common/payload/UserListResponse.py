from dataclasses import dataclass, field
from typing import Sequence

from common.payload.UserInfo import UserInfo


@dataclass(frozen=True)
class UserListResponse:
    users: tuple[UserInfo, ...]
    next_cursor: str | None = None

    def __post_init__(self):
        if self.users is None:
            raise ValueError("Users must not be null")

        if not isinstance(self.users, (list, tuple)):
            raise TypeError("Users must be a list or tuple")

        if not all(isinstance(user, UserInfo) for user in self.users):
            raise TypeError("All users must be UserInfo objects")

        if self.next_cursor is not None:
            if not isinstance(self.next_cursor, str):
                raise TypeError("next_cursor must be a string or None")


        object.__setattr__(
            self,
            "users",
            tuple(self.users)
        )

    def get_users(self) -> tuple[UserInfo, ...]:
        return self.users

    def get_next_cursor(self) -> str | None:
        return self.next_cursor
