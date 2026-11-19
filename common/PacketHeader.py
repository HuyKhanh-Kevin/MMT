
import struct
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class PacketHeader:
    version: int
    messageType: int
    flags: int
    streamID: int
    sequenceNumber: int
    payloadLength: int
    senderID: int
    receiverID: int

    SIZE: ClassVar[int] = 24

    FORMAT: ClassVar[str] = "!BBHIIIII"

    def __post_init__(self):
        fields = {
            "version": (self.version, 8),
            "messageType": (self.messageType, 8),
            "flags": (self.flags, 16),
            "streamID": (self.streamID, 32),
            "sequenceNumber": (self.sequenceNumber, 32),
            "payloadLength": (self.payloadLength, 32),
            "senderID": (self.senderID, 32),
            "receiverID": (self.receiverID, 32),
        }

        for name, (value, bits) in fields.items():
            if type(value) is not int or not 0 <= value < (1 << bits):
                raise ValueError(f"Invalid {name}: {value}")

    def toBytes(self) -> bytes:
        return struct.pack(
            self.FORMAT,
            self.version,
            self.messageType,
            self.flags,
            self.streamID,
            self.sequenceNumber,
            self.senderID,
            self.receiverID,
            self.payloadLength
        )

    @classmethod
    def fromBytes(cls, data: bytes):
        if len(data) < cls.SIZE:
            raise ValueError(
                f"Data too short: {len(data)} bytes"
            )

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
            cls.FORMAT, data[:cls.SIZE]
        )

        return cls(
            version,
            messageType,
            flags,
            streamID,
            sequenceNumber,
            payloadLength,
            senderID,
            receiverID
        )

    def getVersion(self):
        return self.version

    def getMessageType(self):
        return self.messageType

    def getFlags(self):
        return self.flags

    def getStreamID(self):
        return self.streamID

    def getSequenceNumber(self):
        return self.sequenceNumber

    def getPayloadLength(self):
        return self.payloadLength

    def getSenderID(self):
        return self.senderID

    def getReceiverID(self):
        return self.receiverID

    def __str__(self):
        return (
            f"PacketHeader{{ver={self.version}, "
            f"type=0x{self.messageType:02X}, "
            f"flags=0x{self.flags:04X}, "
            f"stream={self.streamID}, "
            f"seq={self.sequenceNumber}, "
            f"sender={self.senderID}, "
            f"receiver={self.receiverID}, "
            f"payloadLen={self.payloadLength}}}"
        )
