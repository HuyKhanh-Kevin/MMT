package common;

import org.junit.jupiter.api.Test;
import java.nio.ByteBuffer;
import java.util.HexFormat;
import static org.junit.jupiter.api.Assertions.*;

class PacketCodecTest {
    static Packet packet(byte[] payload) {
        // Constructor: payloadLength comes BEFORE senderID / receiverID.
        return new Packet(new PacketHeader(2, MessageType.CHAT_MESSAGE, 0x1234,
                0x01020304, 0x05060708, payload.length, 0x11121314, 0x21222324), payload);
    }

    static void assertPacketEquals(Packet expected, Packet actual) {
        assertNotNull(actual);
        PacketHeader e = expected.getHeader(), a = actual.getHeader();
        assertAll(
            () -> assertEquals(e.getVersion(), a.getVersion()),
            () -> assertEquals(e.getMessageType(), a.getMessageType()),
            () -> assertEquals(e.getFlags(), a.getFlags()),
            () -> assertEquals(e.getStreamID(), a.getStreamID()),
            () -> assertEquals(e.getSequenceNumber(), a.getSequenceNumber()),
            () -> assertEquals(e.getPayloadLength(), a.getPayloadLength()),
            () -> assertEquals(e.getSenderID(), a.getSenderID()),
            () -> assertEquals(e.getReceiverID(), a.getReceiverID()),
            () -> assertArrayEquals(expected.getPayload(), actual.getPayload())
        );
    }

    @Test void roundTripPreservesEveryFieldAndBinaryPayload() {
        Packet p = packet(new byte[]{0, 1, 127, (byte) 128, (byte) 255});
        assertPacketEquals(p, PacketCodec.decode(PacketCodec.encode(p)));
    }

    @Test void wireMatchesIndependent24ByteBigEndianExample() {
        byte[] expected = HexFormat.of().parseHex(
                "020312340102030405060708111213142122232400000003616263");
        Packet p = packet(new byte[]{97, 98, 99});
        assertEquals(24, ProtocolConstants.HEADER_SIZE);
        assertArrayEquals(expected, PacketCodec.encode(p));
        assertPacketEquals(p, PacketCodec.decode(expected));
    }

    @Test void zeroLengthPayloadRoundTrip() {
        Packet p = packet(new byte[0]);
        assertEquals(24, PacketCodec.encode(p).length);
        assertPacketEquals(p, PacketCodec.decode(PacketCodec.encode(p)));
    }

    @Test void packetSizeBoundary() {
        // PacketCodec only checks the outer envelope; JSON has its own 1100-byte cap.
        byte[] atLimit = PacketCodec.encode(packet(new byte[1176]));
        assertEquals(1200, atLimit.length);
        assertEquals(1176, PacketCodec.decode(atLimit).getPayload().length);
        assertThrows(IllegalArgumentException.class,
                () -> PacketCodec.encode(packet(new byte[1177])));
        assertThrows(IllegalArgumentException.class,
                () -> PacketCodec.decode(new byte[1201]));
    }

    @Test void rejectNullAndIncompleteHeader() {
        assertThrows(IllegalArgumentException.class, () -> PacketCodec.encode(null));
        assertThrows(IllegalArgumentException.class, () -> PacketCodec.decode(null));
        assertThrows(IllegalArgumentException.class, () -> PacketCodec.decode(new byte[23]));
    }

    @Test void rejectMismatchOnEncode() {
        Packet p = new Packet(new PacketHeader(2, 3, 0, 1, 1, 99, 1, 2), new byte[3]);
        assertThrows(IllegalArgumentException.class, () -> PacketCodec.encode(p));
    }

    @Test void rejectNegativeOrMismatchedLengthOnDecode() {
        for (int length : new int[]{-1, 2, 4}) {
            byte[] wire = PacketCodec.encode(packet(new byte[3]));
            ByteBuffer.wrap(wire).putInt(20, length);
            assertThrows(IllegalArgumentException.class, () -> PacketCodec.decode(wire));
        }
    }

    @Test void rejectUnknownVersionAndMessageType() {
        byte[] wrongVersion = PacketCodec.encode(packet(new byte[0]));
        wrongVersion[0] = 99;
        assertThrows(IllegalArgumentException.class, () -> PacketCodec.decode(wrongVersion));
        byte[] wrongType = PacketCodec.encode(packet(new byte[0]));
        wrongType[1] = 9; // 0x09 was removed from this protocol.
        assertThrows(IllegalArgumentException.class, () -> PacketCodec.decode(wrongType));
        assertThrows(IllegalArgumentException.class, () -> PacketCodec.encode(
                new Packet(new PacketHeader(99, 3, 0, 0, 0, 0, 0, 0), new byte[0])));
        assertThrows(IllegalArgumentException.class, () -> PacketCodec.encode(
                new Packet(new PacketHeader(2, 9, 0, 0, 0, 0, 0, 0), new byte[0])));
    }

    @Test void unsignedFlagsBoundary() {
        for (int flags : new int[]{0, 65535}) {
            Packet p = new Packet(new PacketHeader(2, 3, flags, 0, 0, 0, 0, 0), new byte[0]);
            assertPacketEquals(p, PacketCodec.decode(PacketCodec.encode(p)));
        }
        for (int flags : new int[]{-1, 65536}) {
            Packet p = new Packet(new PacketHeader(2, 3, flags, 0, 0, 0, 0, 0), new byte[0]);
            assertThrows(IllegalArgumentException.class, () -> PacketCodec.encode(p));
        }
    }

    @Test void packetDefensivelyCopiesPayload() {
        byte[] original = {1, 2, 3};
        Packet p = packet(original);
        original[0] = 9;
        p.getPayload()[1] = 9;
        assertArrayEquals(new byte[]{1, 2, 3}, p.getPayload());
    }
}
