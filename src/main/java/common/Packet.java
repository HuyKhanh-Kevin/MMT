package src.main.java.common;

// package common;

public class Packet{
    private final PacketHeader header;
    private final byte[] payload;

    public Packet(PacketHeader header, byte[] payload){
        this.header = header;
        this.payload = payload.clone();
    }

    public PacketHeader getHeader() {
        return header;
    } 

    public byte[] getPayload() {
        return payload.clone();
    }
};

