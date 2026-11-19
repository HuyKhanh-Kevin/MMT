
import socket
import struct

from common.Packet import Packet
from common.PacketCodec import PacketCodec
from common.ProtocolConstants import ProtocolConstants


class PacketIO:

    @staticmethod
    def read_exact(sock: socket.socket, n: int) -> bytes:
        data = bytearray()

        while len(data) < n:
            chunk = sock.recv(n - len(data))

            if not chunk:
                if len(data) == 0:
                    return b""

                raise EOFError(
                    "Connection closed while reading data"
                )

            data.extend(chunk)

        return bytes(data)

    @staticmethod
    def writePacket(
        sock: socket.socket,
        packet: Packet
    ) -> None:
        data = PacketCodec.encode(packet)

        sock.sendall(data)

    @staticmethod
    def readPacket(
        sock: socket.socket
    ) -> Packet | None:

        header_size = ProtocolConstants.HEADER_SIZE

        try:
            header = PacketIO.read_exact(sock, header_size)
        except EOFError as e:
            raise EOFError(
                "Connection closed during header"
            ) from e

        if len(header) == 0:
            return None

        payload_length = struct.unpack_from(
            "!I", header, 20
        )[0]

        if (
            payload_length >
            ProtocolConstants.MAX_PACKET_SIZE - header_size
        ):
            raise OSError("Invalid payload length")

        try:
            payload = PacketIO.read_exact(
                sock, payload_length
            )
        except EOFError as e:
            raise EOFError(
                "Connection closed during payload"
            ) from e

        if len(payload) != payload_length:
            raise EOFError(
                "Connection closed during payload"
            )

        try:
            return PacketCodec.decode(header + payload)
        except (ValueError, TypeError) as e:
            raise OSError("Invalid packet") from e
