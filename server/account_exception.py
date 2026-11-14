"""Expected application errors, separate from transport failures."""


class AccountException(Exception):
    def __init__(self, code: int, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason
