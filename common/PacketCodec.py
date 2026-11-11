
import struct

from .Packet import Packet
from .PacketHeader import PacketHeader
from .ProtocolConstants import ProtocolConstants
from .MessageType import MessageType


class PacketCodec:

    @staticmethod
    def _get_field(header, *method_names):
        # Supports getStreamId/getStreamID naming differences.
        for name in method_names:
            method = getattr(header, name, None)
            if callable(method):
                return method()
        raise AttributeError(f"Missing header getter: {method_names}")


    @staticmethod
    def _validate_header(version, message_type, flags,
                         stream_id, sequence_number,
                         sender_id, receiver_id):

        if version != ProtocolConstants.PROTOCOL_VERSION:
            raise ValueError(f"Unsupported protocol version: {version}")

        if not isinstance(message_type, int) or not 0 <= message_type <= 255:
            raise ValueError("Invalid message type range")

        if not MessageType.isValidMessage(message_type):
            raise ValueError(f"Unknown message type: {message_type}")

        if not isinstance(flags, int) or not 0 <= flags <= 65535:
            raise ValueError("Invalid flags range")

        for name, value in (
            ("stream_id", stream_id),
            ("sequence_number", sequence_number),
            ("sender_id", sender_id),
            ("receiver_id", receiver_id),
        ):
            if not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
                raise ValueError(f"Invalid {name} range")

    @staticmethod
    def encode(packet: Packet) -> bytes:

        if packet is None:
            raise ValueError("Packet cannot be None")

        header = packet.getHeader()
        payload = packet.getPayload()

        if header is None or payload is None:
            raise ValueError("Header and payload cannot be None")

        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError("Payload must be bytes")

        payload = bytes(payload)

        version = header.getVersion()
        message_type = header.getMessageType()

        if isinstance(message_type, str):
            message_type = int(message_type, 0)

        flags = header.getFlags()

        stream_id = PacketCodec._get_field(
            header, "getStreamId", "getStreamID"
        )
        sequence_number = header.getSequenceNumber()
        sender_id = PacketCodec._get_field(
            header, "getSenderId", "getSenderID"
        )
        receiver_id = PacketCodec._get_field(
            header, "getReceiverId", "getReceiverID"
        )
        payload_length = header.getPayloadLength()

        PacketCodec._validate_header(
            version, message_type, flags,
            stream_id, sequence_number,
            sender_id, receiver_id
        )

        if payload_length != len(payload):
            raise ValueError("Payload length mismatch")

        if len(payload) + ProtocolConstants.HEADER_SIZE > ProtocolConstants.MAX_PACKET_SIZE:
            raise ValueError("Packet exceeds maximum size")

        header_bytes = struct.pack(
            ">BBHIIIII",
            version,
            message_type,
            flags,
            stream_id,
            sequence_number,
            sender_id,
            receiver_id,
            payload_length
        )

        return header_bytes + payload

    @staticmethod
    def decode(data: bytes) -> Packet:

        if data is None:
            raise ValueError("Data cannot be None")

        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Data must be bytes")

        data = bytes(data)

        if len(data) < ProtocolConstants.HEADER_SIZE:
            raise ValueError("Incomplete header")

        if len(data) > ProtocolConstants.MAX_PACKET_SIZE:
            raise ValueError("Packet exceeds maximum size")

        (
            version,
            message_type,
            flags,
            stream_id,
            sequence_number,
            sender_id,
            receiver_id,
            payload_length
        ) = struct.unpack(
            ">BBHIIIII",
            data[:ProtocolConstants.HEADER_SIZE]
        )

        PacketCodec._validate_header(
            version, message_type, flags,
            stream_id, sequence_number,
            sender_id, receiver_id
        )

        actual_length = len(data) - ProtocolConstants.HEADER_SIZE

        if payload_length != actual_length:
            raise ValueError("Payload length mismatch")

        payload = data[ProtocolConstants.HEADER_SIZE:]

        # Constructor order differs from wire order.
        header = PacketHeader(
            version,
            message_type,
            flags,
            stream_id,
            sequence_number,
            payload_length,
            sender_id,
            receiver_id
        )

        return Packet(header, payload)
