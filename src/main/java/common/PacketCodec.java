// package common;
package src.main.java.common;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class PacketCodec {
    private PacketCodec() {}

    public static byte[] encode(Packet packet) {
        if (packet == null) {
            throw new IllegalArgumentException("Packet must not be null");
        }

        PacketHeader header = packet.getHeader();
        byte[] payload = packet.getPayload();

        if (header == null || payload == null) {
            throw new IllegalArgumentException(
                    "Header and payload must not be null");
        }

        if (header.getPayloadLength() != payload.length) {
            throw new IllegalArgumentException(
                    "Payload length does not match header");
        }

        if (payload.length >
                ProtocolConstants.MAX_PACKET_SIZE
                - ProtocolConstants.HEADER_SIZE) {
            throw new IllegalArgumentException("Packet is too large");
        }

        if (header.getVersion() != ProtocolConstants.VERSION) {
            throw new IllegalArgumentException(
                    "Unsupported protocol version: " + header.getVersion());
        }

        if (!MessageType.isValid(header.getMessageType())) {
            throw new IllegalArgumentException(
                    "Unknown message type: " + header.getMessageType());
        }

        // Kiểm tra trước khi ép int xuống byte hoặc short.
        if (header.getVersion() < 0 || header.getVersion() > 255
                || header.getMessageType() < 0
                || header.getMessageType() > 255
                || header.getFlags() < 0
                || header.getFlags() > 65535) {
            throw new IllegalArgumentException(
                    "Header field is outside its unsigned range");
        }

        ByteBuffer buffer = ByteBuffer.allocate(
                ProtocolConstants.HEADER_SIZE + payload.length
        );
        buffer.order(ByteOrder.BIG_ENDIAN);

        // Header: 24 bytes.
        buffer.put((byte) header.getVersion());
        buffer.put((byte) header.getMessageType());
        buffer.putShort((short) header.getFlags());
        buffer.putInt(header.getStreamID());
        buffer.putInt(header.getSequenceNumber());
        buffer.putInt(header.getSenderID());
        buffer.putInt(header.getReceiverID());
        buffer.putInt(header.getPayloadLength());

        // Payload: đã ở dạng byte[].
        buffer.put(payload);

        return buffer.array();
    }

    public static Packet decode(byte[] data) {
        if (data == null) {
            throw new IllegalArgumentException("Data must not be null");
        }

        if (data.length < ProtocolConstants.HEADER_SIZE) {
            throw new IllegalArgumentException("Incomplete header");
        }

        if (data.length > ProtocolConstants.MAX_PACKET_SIZE) {
            throw new IllegalArgumentException("Packet is too large");
        }

        ByteBuffer buffer = ByteBuffer.wrap(data);
        buffer.order(ByteOrder.BIG_ENDIAN);

        // Đọc header theo đúng thứ tự đã encode.
        int version = Byte.toUnsignedInt(buffer.get());
        int messageType = Byte.toUnsignedInt(buffer.get());
        int flags = Short.toUnsignedInt(buffer.getShort());

        int streamID = buffer.getInt();
        int sequenceNumber = buffer.getInt();
        int senderID = buffer.getInt();
        int receiverID = buffer.getInt();
        int payloadLength = buffer.getInt();

        if (version != ProtocolConstants.VERSION) {
            throw new IllegalArgumentException(
                    "Unsupported protocol version: " + version);
        }

        // Kiểm tra trước khi cấp phát mảng.
        if (payloadLength < 0 || payloadLength != buffer.remaining()) {
            throw new IllegalArgumentException(
                    "Payload length does not match received data");
        }

        if (!MessageType.isValid(messageType)) {
            throw new IllegalArgumentException(
                    "Unknown message type: " + messageType);
        }

        byte[] payload = new byte[payloadLength];
        buffer.get(payload);

        // Theo thứ tự constructor bạn đã gửi:
        // version, messageType, flags, streamID, sequenceNumber,
        // payloadLength, senderID, receiverID.
        PacketHeader header = new PacketHeader(
                version,
                messageType,
                flags,
                streamID,
                sequenceNumber,
                payloadLength,
                senderID,
                receiverID
        );

        return new Packet(header, payload);
    }
}