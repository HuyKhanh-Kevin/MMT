from abc import ABC, abstractmethod

from common.payload.UserInfo import UserInfo


class Listener(ABC):
    @abstractmethod
    def display_user_list(self, users: list[UserInfo]) -> None: pass

    @abstractmethod
    def display_message(self, sender_id, message) -> None: pass

    @abstractmethod
    def display_signup_response(self, status, reason) -> None: pass

    @abstractmethod
    def display_login_response(self, status, reason) -> None: pass

    @abstractmethod
    def display_logout_response(self, status) -> None: pass

    @abstractmethod
    def display_error(self, code, message) -> None: pass