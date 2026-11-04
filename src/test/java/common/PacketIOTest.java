package common;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import java.io.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

@Timeout(10)
class PacketIOTest {
    // Guarantees short reads. TCP write() boundaries alone cannot guarantee this.
    static final class ShortReadStream extends InputStream {
        private final ByteArrayInputStream source;
        private final int maxRead;
        int bulkReads;
        ShortReadStream(byte[] bytes, int maxRead) {
            source = new ByteArrayInputStream(bytes);
            this.maxRead = maxRead;
        }
        @Override public int read() { return source.read(); }
        @Override public int read(byte[] b, int off, int len) {
            bulkReads++;
            return source.read(b, off, Math.min(len, maxRead));
        }
    }

    @Test void packetSplitIntoManySmallReads() throws IOException {
        Packet p = PacketCodecTest.packet(new byte[]{1, 2, 3, 4, 5, 6, 7});
        byte[] wire = PacketCodec.encode(p);
        for (int size : new int[]{1, 2, 5, 7}) {
            ShortReadStream in = new ShortReadStream(wire, size);
            PacketCodecTest.assertPacketEquals(p, PacketIO.readPacket(in));
            assertTrue(in.bulkReads > 2, "Must actually require multiple reads");
            assertNull(PacketIO.readPacket(in));
        }
    }

    @Test void severalPacketsInOneStreamRemainSeparate() throws IOException {
        Packet[] packets = {PacketCodecTest.packet(new byte[]{1, 2}),
                PacketCodecTest.packet(new byte[0]), PacketCodecTest.packet(new byte[]{9, 8, 7})};
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        for (Packet p : packets) PacketIO.writePacket(out, p);
        try (InputStream in = new ByteArrayInputStream(out.toByteArray())) {
            for (Packet p : packets) PacketCodecTest.assertPacketEquals(p, PacketIO.readPacket(in));
            assertNull(PacketIO.readPacket(in));
        }
        try (InputStream in = new ShortReadStream(out.toByteArray(), 3)) {
            for (Packet p : packets) PacketCodecTest.assertPacketEquals(p, PacketIO.readPacket(in));
            assertNull(PacketIO.readPacket(in));
        }
    }

    @Test void cleanEofReturnsNull() throws IOException {
        assertNull(PacketIO.readPacket(new ByteArrayInputStream(new byte[0])));
    }

    @Test void eofDuringHeaderThrows() {
        assertThrows(EOFException.class,
                () -> PacketIO.readPacket(new ByteArrayInputStream(new byte[23])));
    }

    @Test void eofDuringPayloadThrows() {
        byte[] wire = PacketCodec.encode(PacketCodecTest.packet(new byte[3]));
        assertThrows(EOFException.class, () -> PacketIO.readPacket(
                new ByteArrayInputStream(Arrays.copyOf(wire, wire.length - 1))));
    }

    @Test void badLengthRejectedBeforeReadingPayload() {
        for (int length : new int[]{-1, 1177, Integer.MAX_VALUE}) {
            byte[] header = PacketCodec.encode(PacketCodecTest.packet(new byte[0]));
            ByteBuffer.wrap(header).putInt(20, length);
            assertThrows(IOException.class,
                    () -> PacketIO.readPacket(new ByteArrayInputStream(header)));
        }
    }

    @Test void malformedHeaderBecomesIOException() {
        byte[] wire = PacketCodec.encode(PacketCodecTest.packet(new byte[0]));
        wire[1] = 9;
        assertThrows(IOException.class,
                () -> PacketIO.readPacket(new ByteArrayInputStream(wire)));
    }

    @Test void writesCompletePacket() throws IOException {
        Packet p = PacketCodecTest.packet(new byte[]{1, 2, 3});
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        PacketIO.writePacket(out, p);
        assertArrayEquals(PacketCodec.encode(p), out.toByteArray());
    }

    @Test void realTcpLoopbackEcho() throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket(0, 1, InetAddress.getLoopbackAddress())) {
            listener.setSoTimeout(3000);
            Future<Void> server = worker.submit(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(3000);
                    Packet received = PacketIO.readPacket(peer.getInputStream());
                    assertNotNull(received);
                    PacketIO.writePacket(peer.getOutputStream(), received);
                }
                return null;
            });
            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(InetAddress.getLoopbackAddress(),
                        listener.getLocalPort()), 3000);
                client.setSoTimeout(3000);
                Packet p = PacketCodecTest.packet(new byte[]{0, 1, (byte) 255});
                PacketIO.writePacket(client.getOutputStream(), p);
                PacketCodecTest.assertPacketEquals(p, PacketIO.readPacket(client.getInputStream()));
                assertNull(PacketIO.readPacket(client.getInputStream()));
            }
            server.get(5, TimeUnit.SECONDS);
        } finally {
            worker.shutdownNow();
        }
    }
}
