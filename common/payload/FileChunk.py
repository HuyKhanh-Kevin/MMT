
from dataclasses import dataclass
from common.ProtocolConstants import ProtocolConstants
from common.payload.FileID import validate_file_id


@dataclass(frozen=True)
class FileChunk:
    file_id: str
    payload_data: bytes

    def __post_init__(self) -> None:
        validate_file_id(self.file_id)

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

    def getPayloadLength(self) -> int:
        return self.payload_length

    def getPayloadData(self) -> bytes:
        return self.payload_data
