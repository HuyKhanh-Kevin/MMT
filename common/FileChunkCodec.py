
import struct

from .protocol_constants import ProtocolConstants
from .payload.file_chunk import FileChunk


class FileChunkCodec:
    FORMAT = ">III"  # Big-Endian, 3 unsigned integers (12 bytes)

    @staticmethod
    def encode(chunk: FileChunk) -> bytes:
        if chunk is None:
            raise ValueError("FileChunk must not be null")

        file_id = chunk.getFileID()
        chunk_index = chunk.getChunkOrder()
        data = chunk.getPayloadData()

        if not isinstance(file_id, int) or not 0 <= file_id <= 0x7FFFFFFF:
            raise ValueError("Invalid file ID")

        if not isinstance(chunk_index, int) or not 0 <= chunk_index <= 0x7FFFFFFF:
            raise ValueError("Invalid chunk index")

        if not isinstance(data, bytes):
            raise TypeError("Chunk data must be bytes")

        if len(data) > ProtocolConstants.MAX_CHUNK_DATA_SIZE:
            raise ValueError("Chunk data is too large")

        metadata = struct.pack(
            FileChunkCodec.FORMAT,
            file_id,
            chunk_index,
            len(data)
        )

        return metadata + data

    @staticmethod
    def decode(data: bytes) -> FileChunk:
        if data is None:
            raise ValueError("Chunk bytes must not be null")

        if not isinstance(data, bytes):
            raise TypeError("Chunk must be bytes")

        metadata_size = ProtocolConstants.CHUNK_METADATA_SIZE

        if len(data) < metadata_size:
            raise ValueError("Incomplete chunk metadata")

        if len(data) > (
            metadata_size + ProtocolConstants.MAX_CHUNK_DATA_SIZE
        ):
            raise ValueError("Chunk is too large")

        file_id, chunk_index, payload_length = struct.unpack(
            FileChunkCodec.FORMAT,
            data[:metadata_size]
        )

        payload = data[metadata_size:]

        if file_id > 0x7FFFFFFF:
            raise ValueError("Invalid file ID")

        if chunk_index > 0x7FFFFFFF:
            raise ValueError("Invalid chunk index")

        if (
            payload_length > ProtocolConstants.MAX_CHUNK_DATA_SIZE
            or payload_length != len(payload)
        ):
            raise ValueError("Invalid chunk payload length")

        return FileChunk(file_id, chunk_index, payload)
