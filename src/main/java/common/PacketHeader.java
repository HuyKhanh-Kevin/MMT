package src.main.java.common;
// package common;

public class PacketHeader{
    private final int version;
    private final int messageType;
    private final int flags;
    private final int streamID;
    private final int sequenceNumber;
    private final int payloadLength;
    private final int senderID;
    private final int receiverID;
    public static final int SIZE = 24;
    
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

    // public PacketHeader (byte[] data) {
    //     if (data.length < 24) {
    //         throw new IllegalArgumentException("Data too short: " + data.length + " bytes");
    //     }
    //     ByteBuffer buf = ByteBuffer.wrap(data);
    //     int version        = buf.get() & 0xFF;
    //     int messageType    = buf.get() & 0xFF;
    //     int flags          = buf.getShort() & 0xFFFF;
    //     int streamId      = buf.getInt() & 0xFFFFFFFF;
    //     int seqNum        = buf.getInt() & 0xFFFFFFFF;
    //     int senderId      = buf.getInt() & 0xFFFFFFFF;
    //     int receiverId    = buf.getInt() & 0xFFFFFFFF;
    //     int payloadLength = buf.getInt() & 0xFFFFFFFF;
    //     this(version, messageType, flags, streamId, seqNum, senderId, receiverId, payloadLength);
    // }
    // public byte[] toBytes() {
    //     ByteBuffer buf = ByteBuffer.allocate(SIZE);
    //     buf.put((byte) version);
    //     buf.put((byte) messageType);
    //     buf.putShort((short) flags);
    //     buf.putInt((int) streamID);
    //     buf.putInt((int) sequenceNumber);
    //     buf.putInt((int) senderID);
    //     buf.putInt((int) receiverID);
    //     buf.putInt((int) payloadLength);
    //     return buf.array();
    // }

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

    @Override
    public String toString() {
        return String.format(
            "PacketHeader{ver=%d, type=0x%02X, flags=0x%04X, stream=%d, seq=%d, sender=%d, receiver=%d, payloadLen=%d}",
            version, messageType, flags, streamID, sequenceNumber, senderID, receiverID, payloadLength
        );
    }
};
