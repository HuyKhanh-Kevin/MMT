
class ErrorCode:
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message

    def __str__(self):
        return f"ErrorCode(code={self.code}, message='{self.message}')"

    def __repr__(self):
        return self.__str__()

    @classmethod
    def get_error_code(cls, code: int):
        return cls.error_codes.get(
            code, cls(-1, "Unknown error")
        )

ErrorCode.error_codes = {
    0: ErrorCode(0, "Success"),
    1001: ErrorCode(1001, "Invalid credentials"),
    1002: ErrorCode(1002, "Username taken"),
    1003: ErrorCode(1003, "Invalid payload"),
    1004: ErrorCode(1004, "Unauthenticated request"),
    2001: ErrorCode(2001, "Recipient offline"),
    3001: ErrorCode(3001, "Message/file too large"),
    3002: ErrorCode(3002, "File hash mismatch"),
    3003: ErrorCode(3003, "Transfer timed out"),
    3004: ErrorCode(3004, "File write failed"),
    4001: ErrorCode(4001, "Decryption failed"),
    4002: ErrorCode(4002, "Window exceeded"),
    4003: ErrorCode(4003, "Rate limit exceeded"),
    5001: ErrorCode(5001, "Internal server error"),
}
