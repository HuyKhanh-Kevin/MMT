
from common.JsonPayloadCodec import JsonPayloadCodec
from common.Packet import Packet
from common.PacketHeader import PacketHeader
from common.ProtocolConstants import ProtocolConstants


class ControlPackets:

    @staticmethod
    def create(
        type: str,
        sequence: int,
        sender: int,
        receiver: int,
        value: object
    ) -> Packet:

        # Serialize JSON payload into bytes
        payload = JsonPayloadCodec.encode(value)

        # Equivalent to Java Integer.decode(type)
        message_type = int(type, 0)

        header = PacketHeader(
            ProtocolConstants.PROTOCOL_VERSION,
            message_type,
            0,               # flags
            0,               # streamID (control stream)
            sequence,
            len(payload),
            sender,
            receiver
        )

        return Packet(header, payload)
