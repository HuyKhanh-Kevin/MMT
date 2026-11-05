package common;

import common.payload.FileChunk;
import org.junit.jupiter.api.Test;
import java.nio.ByteBuffer;
import java.util.HexFormat;
import java.util.Random;
import static org.junit.jupiter.api.Assertions.*;

class FileChunkCodecTest {
    @Test void wireMatches12ByteMetadataExample() {
        byte[] expected = HexFormat.of().parseHex("0000002a0000000700000003616263");
        assertArrayEquals(expected, FileChunkCodec.encode(new FileChunk(42, 7, new byte[]{97, 98, 99})));
        FileChunk r = FileChunkCodec.decode(expected);
        assertEquals(42, r.getFileID());
        assertEquals(7, r.getChunkOrder());
        assertEquals(3, r.getPayloadLength());
        assertArrayEquals(new byte[]{97, 98, 99}, r.getPayloadData());
    }

    @Test void roundTripsBoundarySizes() {
        for (int size : new int[]{0, 1, 1024}) {
            byte[] data = new byte[size];
            new Random(42).nextBytes(data);
            byte[] wire = FileChunkCodec.encode(new FileChunk(42, 7, data));
            assertEquals(12 + size, wire.length);
            FileChunk r = FileChunkCodec.decode(wire);
            assertEquals(42, r.getFileID());
            assertEquals(7, r.getChunkOrder());
            assertEquals(size, r.getPayloadLength());
            assertArrayEquals(data, r.getPayloadData());
        }
    }

    @Test void rejectsBadLengthAndOversize() {
        assertThrows(IllegalArgumentException.class, () -> FileChunkCodec.decode(new byte[11]));
        assertThrows(IllegalArgumentException.class, () -> FileChunkCodec.decode(new byte[1037]));
        assertThrows(IllegalArgumentException.class, () -> new FileChunk(42, 0, new byte[1025]));
        for (int length : new int[]{-1, 3, 1025}) {
            byte[] wire = ByteBuffer.allocate(12).putInt(42).putInt(0).putInt(length).array();
            assertThrows(IllegalArgumentException.class, () -> FileChunkCodec.decode(wire));
        }
    }

    @Test void rejectsNegativeChunkOrderOnBothPaths() {
        assertThrows(IllegalArgumentException.class, () -> new FileChunk(42, -1, new byte[0]));
        byte[] wire = ByteBuffer.allocate(12).putInt(42).putInt(-1).putInt(0).array();
        assertThrows(IllegalArgumentException.class, () -> FileChunkCodec.decode(wire));
    }
}
