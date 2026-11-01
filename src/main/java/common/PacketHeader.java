package src.main.java.common;

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
