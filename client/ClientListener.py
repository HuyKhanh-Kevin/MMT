
from abc import ABC, abstractmethod

from common.payload.user_info import UserInfo
from common.payload.presence_update import PresenceUpdate


class ClientListener(ABC):

    def display_presence(self, update: PresenceUpdate) -> None:
        """Optional hint; display_user_list receives reconciled snapshots."""
        pass

    @abstractmethod
    def display_user_list(self, users: list[UserInfo]) -> None:
        pass

    @abstractmethod
    def display_message(self, sender_id: int, message: str) -> None:
        pass

    @abstractmethod
    def display_signup_response(
        self, status: str, reason: str | None
    ) -> None:
        pass

    @abstractmethod
    def display_login_response(
        self, status: str, reason: str | None
    ) -> None:
        pass

    @abstractmethod
    def display_logout_response(self) -> None:
        pass

    @abstractmethod
    def display_error(self, code: int, message: str) -> None:
        pass
