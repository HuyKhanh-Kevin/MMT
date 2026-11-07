package src.main.java.common;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetSocketAddress;
import java.util.Arrays;

public final class UdpPacketIO {
    private UdpPacketIO() {}

    // Giữ cả packet và địa chỉ bên gửi để có thể phản hồi.
    public record ReceivedPacket(
            Packet packet,
            InetSocketAddress source
    ) {}

    public static void sendPacket(
            DatagramSocket socket,
            InetSocketAddress destination,
            Packet packet
    ) throws IOException {

        byte[] data = PacketCodec.encode(packet);

        DatagramPacket datagram = new DatagramPacket(
                data,
                data.length,
                destination
        );

        socket.send(datagram);
    }

    public static ReceivedPacket receivePacket(
            DatagramSocket socket
    ) throws IOException {

        // Thêm 1 byte để phát hiện datagram vượt giới hạn.
        byte[] buffer = new byte[
                ProtocolConstants.MAX_PACKET_SIZE + 1
        ];

        DatagramPacket datagram = new DatagramPacket(
                buffer,
                buffer.length
        );

        socket.receive(datagram);

        if (datagram.getLength() >
                ProtocolConstants.MAX_PACKET_SIZE) {
            throw new IOException("UDP packet is too large");
        }

        // Chỉ lấy những bytes thực sự nhận được.
        byte[] data = Arrays.copyOfRange(
                datagram.getData(),
                datagram.getOffset(),
                datagram.getOffset() + datagram.getLength()
        );

        Packet packet;

        try {
            packet = PacketCodec.decode(data);
        } catch (IllegalArgumentException e) {
            throw new IOException("Invalid UDP packet", e);
        }

        InetSocketAddress source = new InetSocketAddress(
                datagram.getAddress(),
                datagram.getPort()
        );

        return new ReceivedPacket(packet, source);
    }
}