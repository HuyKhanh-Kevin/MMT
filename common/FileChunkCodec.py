import struct
import uuid

from .ProtocolConstants import ProtocolConstants
from .payload.FileChunk import FileChunk


class FileChunkCodec:
    _FORMAT = ">16sII"
    _METADATA_SIZE = struct.calcsize(_FORMAT)

    @staticmethod
    def encode(chunk: FileChunk) -> bytes:
        if not isinstance(chunk, FileChunk):
            raise TypeError("chunk must be a FileChunk")
        if FileChunkCodec._METADATA_SIZE != ProtocolConstants.CHUNK_METADATA_SIZE:
            raise ValueError("CHUNK_METADATA_SIZE does not match the codec")

        data = chunk.payload_data
        if len(data) > ProtocolConstants.MAX_CHUNK_DATA_SIZE:
            raise ValueError("Chunk payload exceeds maximum size")
        file_id_bytes = uuid.UUID(chunk.file_id).bytes
        metadata = struct.pack(
            FileChunkCodec._FORMAT,
            file_id_bytes,
            len(data),
        )
        return metadata + data

    @staticmethod
    def decode(raw: bytes) -> FileChunk:
        if not isinstance(raw, (bytes, bytearray)):
            raise TypeError("raw must be bytes or bytearray")
        if FileChunkCodec._METADATA_SIZE != ProtocolConstants.CHUNK_METADATA_SIZE:
            raise ValueError("CHUNK_METADATA_SIZE does not match the codec")

        raw = bytes(raw)
        metadata_size = ProtocolConstants.CHUNK_METADATA_SIZE
        if len(raw) < metadata_size:
            raise ValueError("Incomplete chunk metadata")
        if len(raw) > metadata_size + ProtocolConstants.MAX_CHUNK_DATA_SIZE:
            raise ValueError("Chunk is too large")

        file_id_bytes, chunk_order, payload_length = struct.unpack(
            FileChunkCodec._FORMAT, raw[:metadata_size]
        )
        data = raw[metadata_size:]
        if chunk_order > 0x7FFFFFFF:
            raise ValueError("Invalid chunk order")
        if payload_length > ProtocolConstants.MAX_CHUNK_DATA_SIZE:
            raise ValueError("Chunk payload exceeds maximum size")
        if payload_length != len(data):
            raise ValueError("Payload length does not match the data")

        identifier = uuid.UUID(bytes=file_id_bytes)
        if identifier.version != 4:
            raise ValueError("file_id in chunk is not a UUIDv4")
        return FileChunk(str(identifier), chunk_order, data)
