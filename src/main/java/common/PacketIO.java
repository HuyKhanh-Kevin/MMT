package src.main.java.common;

import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class PacketIO {
    private PacketIO() {}

    public static void writePacket(OutputStream out, Packet packet)
            throws IOException {

        byte[] data = PacketCodec.encode(packet);
        out.write(data);
        out.flush();
    }

    public static Packet readPacket(InputStream in)
            throws IOException {

        // 1. Đọc đủ header hoặc dừng khi kết nối đã đóng.
        byte[] headerBytes =
                in.readNBytes(ProtocolConstants.HEADER_SIZE);

        if (headerBytes.length == 0) {
            return null; // Kết nối đóng trước khi bắt đầu packet mới.
        }

        if (headerBytes.length < ProtocolConstants.HEADER_SIZE) {
            throw new EOFException("Connection closed during header");
        }

        // 2. Lấy payloadLength tại offset 20.
        ByteBuffer headerBuffer = ByteBuffer.wrap(headerBytes);
        headerBuffer.order(ByteOrder.BIG_ENDIAN);

        int payloadLength = headerBuffer.getInt(20);

        if (payloadLength < 0
                || payloadLength >
                ProtocolConstants.MAX_PACKET_SIZE
                - ProtocolConstants.HEADER_SIZE) {
            throw new IOException("Invalid payload length");
        }

        // 3. Đọc đủ payload.
        byte[] payload = in.readNBytes(payloadLength);

        if (payload.length != payloadLength) {
            throw new EOFException("Connection closed during payload");
        }

        // 4. Ghép header + payload để decode.
        ByteBuffer packetBuffer = ByteBuffer.allocate(
                ProtocolConstants.HEADER_SIZE + payloadLength
        );

        packetBuffer.put(headerBytes);
        packetBuffer.put(payload);

        try {
            return PacketCodec.decode(packetBuffer.array());
        } catch (IllegalArgumentException e) {
            throw new IOException("Invalid packet", e);
        }
    }
}