package common;

import java.io.IOException;

/** Account/presence messages all use control stream 0. */
public final class ControlPackets {
    private ControlPackets() {}

    public static Packet create(String type, int sequence, int sender, int receiver, Object value)
            throws IOException {
        byte[] bytes = JsonPayloadCodec.encode(value);
        return new Packet(new PacketHeader(ProtocolConstants.VERSION, Integer.decode(type),
                0, 0, sequence, bytes.length, sender, receiver), bytes);
    }
}
