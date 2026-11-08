import socket
import struct
import ProtocolConstants
from common import MessageType

from common import Packet
from common import PacketHeader
from common import ProtocolConstants


class PacketCodec:
    def __init__(self):
        pass

    @staticmethod
    def encode(packet):
        if packet == None:
            raise ValueError("Packet cannot be None")
        
        header = packet.getHeader()
        payload = packet.getPayload()

        if header == None:
            raise ValueError("Header cannot be None")

        if payload == None:
            raise ValueError("Payload cannot be None")

        if len(payload) != header.getPayloadLength():
            raise ValueError("Payload length does not match header")

        if len(payload) > ProtocolConstants.MAX_PACKET_SIZE - ProtocolConstants.HEADER_SIZE:
            raise ValueError("Payload length is less than header size")

        if header.getVersion() != ProtocolConstants.PROTOCOL_VERSION:
            raise ValueError("Unsupported protocol version" + header.getVersion())

        if MessageType.isValidMessageType() == False:
            raise ValueError("Invalid message type" + header.getMessageType())

        if header.getVersion() < 0 or header.getVersion() > 255:
            raise ValueError("Header version is outside its unsigned range")

        if header.getMessageType() < 0 or header.getMessageType() > 255:
            raise ValueError("Header message type is outside its unsigned range")

        if header.getFlags() < 0 or header.getFlags() > 65535:
            raise ValueError("Header flags is outside its unsigned range")

        if header.getPayloadLength() < 0 or header.getPayloadLength() > ProtocolConstants.MAX_PAYLOAD_SIZE:
            raise ValueError("Header payload length is outside its unsigned range")


        header_bytes = struct.pack(
            ">BBHIIIII",
            header.getVersion(),
            header.getMessageType(),
            header.getFlags(),
            header.getStreamId(),
            header.getSequenceNumber(),
            header.getSenderId(),
            header.getReceiverId(),
            len(payload)
        )

        packet_bytes = header_bytes + payload

        return packet_bytes


class PacketCodec:

    @staticmethod
    def decode(data: bytes) -> Packet:
        if data is None:
            raise ValueError("Data must not be null")

        if not isinstance(data, bytes):
            raise TypeError("Data must be bytes")

        if len(data) < ProtocolConstants.HEADER_SIZE:
            raise ValueError("Incomplete header")

        if len(data) > ProtocolConstants.MAX_PACKET_SIZE:
            raise ValueError("Packet is too large")

        # Decode 24-byte header using Big-Endian
        (
            version,
            messageType,
            flags,
            streamID,
            sequenceNumber,
            senderID,
            receiverID,
            payloadLength
        ) = struct.unpack(
            ">BBHIIIII",
            data[:ProtocolConstants.HEADER_SIZE]
        )

        # Validate protocol version
        if version != ProtocolConstants.VERSION:
            raise ValueError(
                f"Unsupported protocol version: {version}"
            )

        # Validate payload length
        remaining = len(data) - ProtocolConstants.HEADER_SIZE

        if payloadLength != remaining:
            raise ValueError(
                "Payload length does not match received data"
            )

        # Validate message type
        if not MessageType.isValidMessageType(messageType):
            raise ValueError(
                f"Unknown message type: {messageType}"
            )

        # Extract payload
        payload = data[ProtocolConstants.HEADER_SIZE:]

        # Construct PacketHeader
        header = PacketHeader(
            version,
            messageType,
            flags,
            streamID,
            sequenceNumber,
            payloadLength,
            senderID,
            receiverID
        )

        return Packet(header, payload)
