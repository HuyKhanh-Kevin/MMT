
import socket
from dataclasses import dataclass

from .packet import Packet
from .packet_codec import PacketCodec
from .protocol_constants import ProtocolConstants


@dataclass(frozen=True)
class ReceivedPacket:
    packet: Packet
    source: tuple[str, int]


class UdpPacketIO:

    @staticmethod
    def sendPacket(
        sock: socket.socket,
        destination: tuple[str, int],
        packet: Packet
    ) -> None:

        data = PacketCodec.encode(packet)

        sock.sendto(data, destination)

    @staticmethod
    def receivePacket(
        sock: socket.socket
    ) -> ReceivedPacket:

        # Add 1 byte to detect oversized UDP packets
        buffer_size = ProtocolConstants.MAX_PACKET_SIZE + 1

        data, source = sock.recvfrom(buffer_size)

        if len(data) > ProtocolConstants.MAX_PACKET_SIZE:
            raise OSError("UDP packet is too large")

        try:
            packet = PacketCodec.decode(data)
        except ValueError as e:
            raise OSError("Invalid UDP packet") from e

        return ReceivedPacket(packet, source)
