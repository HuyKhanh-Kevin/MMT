package src.main.java.common;

import java.nio.ByteBuffer;

public class PacketHeader {

    public static final int SIZE = 24;

    public final int version; 
    public final int messageType;
    public final int flags; 
    public final long streamId; 
    public final long sequenceNumber;
    public final long senderId;
    public final long receiverId;
    public final long payloadLength;

    public PacketHeader(int version, int messageType, int flags,
                        long streamId, long sequenceNumber,
                        long senderId, long receiverId, long payloadLength) {
        this.version = version;
        this.messageType = messageType;
        this.flags = flags;
        this.streamId = streamId;
        this.sequenceNumber = sequenceNumber;
        this.senderId = senderId;
        this.receiverId = receiverId;
        this.payloadLength = payloadLength;
    }

    public byte[] toBytes() {
        ByteBuffer buf = ByteBuffer.allocate(SIZE);
        buf.put((byte) version);
        buf.put((byte) messageType);
        buf.putShort((short) flags);
        buf.putInt((int) streamId);
        buf.putInt((int) sequenceNumber);
        buf.putInt((int) senderId);
        buf.putInt((int) receiverId);
        buf.putInt((int) payloadLength);
        return buf.array();
    }

    public static PacketHeader fromBytes(byte[] data) {
        if (data.length < SIZE) {
            throw new IllegalArgumentException("Data too short: " + data.length + " bytes");
        }
        ByteBuffer buf = ByteBuffer.wrap(data);
        int version        = buf.get() & 0xFF;
        int messageType    = buf.get() & 0xFF;
        int flags          = buf.getShort() & 0xFFFF;
        long streamId      = buf.getInt() & 0xFFFFFFFF;
        long seqNum        = buf.getInt() & 0xFFFFFFFF;
        long senderId      = buf.getInt() & 0xFFFFFFFF;
        long receiverId    = buf.getInt() & 0xFFFFFFFF;
        long payloadLength = buf.getInt() & 0xFFFFFFFF;
        return new PacketHeader(version, messageType, flags,
                streamId, seqNum, senderId, receiverId, payloadLength);
    }

    @Override
    public String toString() {
        return String.format(
            "PacketHeader{ver=%d, type=0x%02X, flags=0x%04X, stream=%d, seq=%d, sender=%d, receiver=%d, payloadLen=%d}",
            version, messageType, flags, streamId, sequenceNumber, senderId, receiverId, payloadLength
        );
    }
}
package common;

public class PacketHeader{
    private final int version;
    private final int messageType;
    private final int flags;
    private final int streamID;
    private final int sequenceNumber;
    private final int payloadLength;
    private final int senderID;
    private final int receiverID;

    public PacketHeader(int version, int messageType, int flags, int streamID, int sequenceNumber, int payloadLength, int senderID, int receiverID){
        this.version = version;
        this.messageType = messageType;
        this.flags = flags;
        this.streamID = streamID;
        this.sequenceNumber = sequenceNumber;
        this.payloadLength = payloadLength;
        this.senderID = senderID;
        this.receiverID = receiverID;
    }

    public int getVersion() {
        return version;
    }

    public int getMessageType() {
        return messageType;
    }

    public int getFlags() {
        return flags;
    }

    public int getStreamID() {
        return streamID;
    }

    public int getSequenceNumber() {
        return sequenceNumber;
    }

    public int getPayloadLength() {
        return payloadLength;
    }

    public int getSenderID() {
        return senderID;
    }

    public int getReceiverID() {
        return receiverID;
    }
};
