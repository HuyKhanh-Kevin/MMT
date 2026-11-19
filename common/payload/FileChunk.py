"""Binary FILE_CHUNK payload model with canonical UUIDv4 string file IDs."""

from dataclasses import dataclass
from common.ProtocolConstants import ProtocolConstants
from common.payload.FileID import validate_file_id


@dataclass(frozen=True)
class FileChunk:
    file_id: str
    chunk_order: int
    payload_data: bytes

    def __post_init__(self) -> None:
        validate_file_id(self.file_id)

        # Preserve the signed 32-bit nonnegative chunk index semantics from Java.
        if type(self.chunk_order) is not int or not 0 <= self.chunk_order <= 0x7FFFFFFF:
            raise ValueError("chunk_order must be in the range 0..2147483647")

        if not isinstance(self.payload_data, (bytes, bytearray)):
            raise TypeError("payload_data must be bytes or bytearray")
        data = bytes(self.payload_data)
        if len(data) > ProtocolConstants.MAX_CHUNK_DATA_SIZE:
            raise ValueError("Chunk payload exceeds 1024 bytes")
        object.__setattr__(self, "payload_data", data)

    @property
    def payload_length(self) -> int:
        return len(self.payload_data)

    # Legacy Java-style method names for other converted modules.
    def getFileID(self) -> str:
        return self.file_id

    def getChunkOrder(self) -> int:
        return self.chunk_order

    def getPayloadLength(self) -> int:
        return self.payload_length

    def getPayloadData(self) -> bytes:
        return self.payload_data
