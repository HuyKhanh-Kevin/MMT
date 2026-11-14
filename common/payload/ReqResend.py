from dataclasses import dataclass

from common.payload.FileID import validate_file_id


@dataclass(frozen=True)
class ReqResend:
    file_id: str
    resend_all: bool
    missing_chunk_orders: list[int]

    def __post_init__(self):
        validate_file_id(self.file_id)

        if type(self.resend_all) is not bool:
            raise TypeError("resend_all must be a boolean")

        if not isinstance(self.missing_chunk_orders, list):
            raise TypeError("missing_chunk_orders must be a list of integers")
        for order in self.missing_chunk_orders:
            if type(order) is not int:
                raise TypeError("Each item in missing_chunk_orders must be an integer")
            if order < 0:
                raise ValueError("Each item in missing_chunk_orders must be non-negative")

    def get_file_id(self) -> str:
        return self.file_id

    def get_resend_all(self) -> bool:
        return self.resend_all

    def get_missing_chunk_orders(self) -> list[int]:
        return self.missing_chunk_orders
