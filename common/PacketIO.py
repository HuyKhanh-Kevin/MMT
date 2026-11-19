
import socket
import struct

from common.Packet import Packet
from common import PacketCodec
from common import ProtocolConstants


class PacketIO:

    @staticmethod
    def read_exact(sock: socket.socket, n: int) -> bytes:
        """Read exactly n bytes unless connection closes."""

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

        # sendall ensures all bytes are submitted to TCP
        sock.sendall(data)

    @staticmethod
    def readPacket(
        sock: socket.socket
    ) -> Packet | None:

        # 1. Read full header
        header_size = ProtocolConstants.HEADER_SIZE

        try:
            header = PacketIO.read_exact(sock, header_size)
        except EOFError as e:
            raise EOFError(
                "Connection closed during header"
            ) from e

        if len(header) == 0:
            return None

        # 2. Read payload length at offset 20
        payload_length = struct.unpack_from(
            "!I", header, 20
        )[0]

        if (
            payload_length >
            ProtocolConstants.MAX_PACKET_SIZE - header_size
        ):
            raise OSError("Invalid payload length")

        # 3. Read exact payload
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

        # 4. Decode packet
        try:
            return PacketCodec.decode(header + payload)
        except (ValueError, TypeError) as e:
            raise OSError("Invalid packet") from e
