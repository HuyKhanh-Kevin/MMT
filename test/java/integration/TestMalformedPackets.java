package test.java.integration;

import common.*;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.*;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Ca kiểm thử 1: Xử lý gói tin sai định dạng (Malformed Packet & Framing Resilience)
 * Mục tiêu: Chứng minh hệ thống không bị crash hoặc dead-loop khi gặp packet lỗi.
 */
public class TestMalformedPackets {

    public static void main(String[] args) {
        System.out.println("=== CHẠY KIỂM THỬ: GÓI TIN SAI ĐỊNH DẠNG (MALFORMED PACKETS) ===");
        TestMalformedPackets tester = new TestMalformedPackets();
        try {
            tester.testIncompleteHeader();
            System.out.println("[PASS] 1. Incomplete Header (< 24 bytes) - Bắt EOFException an toàn.");

            tester.testInvalidProtocolVersion();
            System.out.println("[PASS] 2. Invalid Protocol Version - Bắt IllegalArgumentException an toàn.");

            tester.testInvalidMessageType();
            System.out.println("[PASS] 3. Unknown Message Type (0x99) - Bắt IllegalArgumentException an toàn.");

            tester.testPayloadLengthMismatch();
            System.out.println("[PASS] 4. Payload Length Mismatch - Bắt EOFException khi stream ngắt giữa chừng.");

            tester.testOversizedPacket();
            System.out.println("[PASS] 5. Oversized Packet (> 65535 bytes) - Từ chối ngay trước khi cấp phát bộ nhớ.");

            System.out.println("===> TẤT CẢ CA KIỂM THỬ GÓI TIN SAI ĐỀU THÀNH CÔNG!\n");
        } catch (Throwable t) {
            System.err.println("[FAIL] Lỗi kiểm thử: " + t.getMessage());
            t.printStackTrace();
        }
    }

    @Test
    @DisplayName("1. Header gửi thiếu byte (< 24 bytes) qua socket TCP")
    public void testIncompleteHeader() throws Exception {
        // Tạo ServerSocket giả lập để đọc packet
        try (ServerSocket serverSocket = new ServerSocket(0)) {
            int port = serverSocket.getLocalPort();
            AtomicBoolean serverHandledCleanly = new AtomicBoolean(false);

            Thread serverThread = new Thread(() -> {
                try (Socket client = serverSocket.accept();
                     InputStream in = client.getInputStream()) {
                    // Thử đọc packet bằng PacketIO
                    PacketIO.readPacket(in);
                } catch (EOFException | SocketException e) {
                    // Đúng mong đợi: client ngắt khi chưa đủ 24 bytes header
                    serverHandledCleanly.set(true);
                } catch (IOException e) {
                    serverHandledCleanly.set(true);
                }
            });
            serverThread.start();

            // Client kết nối và chỉ gửi 10 bytes rác rồi đóng socket
            try (Socket client = new Socket("127.0.0.1", port);
                 OutputStream out = client.getOutputStream()) {
                out.write(new byte[]{1, 2, 3, 4, 5, 6, 7, 8, 9, 10});
                out.flush();
            }

            serverThread.join(2000);
            assertTrue(serverHandledCleanly.get(), "Server phải bắt EOFException khi nhận header không đủ 24 bytes");
        }
    }

    @Test
    @DisplayName("2. Phiên bản giao thức không hợp lệ (version != 2)")
    public void testInvalidProtocolVersion() {
        // PacketHeader(version, messageType, flags, streamID, sequenceNumber, payloadLength, senderID, receiverID)
        PacketHeader invalidHeader = new PacketHeader(99, 0x01, 0, 1, 1, 4, 10, 0);
        byte[] payload = "test".getBytes();
        Packet packet = new Packet(invalidHeader, payload);

        Exception exception = assertThrows(IllegalArgumentException.class, () -> {
            PacketCodec.encode(packet);
        });
        assertTrue(exception.getMessage().contains("Unsupported protocol version"));
    }

    @Test
    @DisplayName("3. Mã loại thông điệp (MessageType) không hợp lệ (ví dụ: 0x99)")
    public void testInvalidMessageType() {
        PacketHeader invalidHeader = new PacketHeader(ProtocolConstants.VERSION, 0x99, 0, 1, 1, 4, 10, 0);
        byte[] payload = "test".getBytes();
        Packet packet = new Packet(invalidHeader, payload);

        Exception exception = assertThrows(IllegalArgumentException.class, () -> {
            PacketCodec.encode(packet);
        });
        assertTrue(exception.getMessage().contains("Unknown message type"));
    }

    @Test
    @DisplayName("4. Header khai khống payload (báo 5000 bytes nhưng chỉ gửi 5 bytes rồi ngắt)")
    public void testPayloadLengthMismatch() throws Exception {
        try (ServerSocket serverSocket = new ServerSocket(0)) {
            int port = serverSocket.getLocalPort();
            AtomicBoolean serverHandledCleanly = new AtomicBoolean(false);

            Thread serverThread = new Thread(() -> {
                try (Socket client = serverSocket.accept();
                     InputStream in = client.getInputStream()) {
                    PacketIO.readPacket(in);
                } catch (EOFException | SocketException e) {
                    // Đúng mong đợi: Đang đọc payload thì client ngắt kết nối
                    serverHandledCleanly.set(true);
                } catch (IOException e) {
                    // Trên Windows, connection reset có thể là IOException
                    serverHandledCleanly.set(true);
                }
            });
            serverThread.start();

            // Client gửi 24 bytes header hợp lệ với payload_length = 5000, nhưng chỉ gửi 5 bytes
            try (Socket client = new Socket("127.0.0.1", port);
                 OutputStream out = client.getOutputStream()) {

                ByteBuffer headerBuf = ByteBuffer.allocate(ProtocolConstants.HEADER_SIZE);
                headerBuf.order(ByteOrder.BIG_ENDIAN);
                headerBuf.put((byte) ProtocolConstants.VERSION);
                headerBuf.put((byte) 0x03); // CHAT_MESSAGE
                headerBuf.putShort((short) 0);
                headerBuf.putInt(1);  // streamID
                headerBuf.putInt(1);  // seq
                headerBuf.putInt(10); // senderID
                headerBuf.putInt(0);  // receiverID
                headerBuf.putInt(5000); // Khai khống payloadLength = 5000

                out.write(headerBuf.array());
                out.write(new byte[]{1, 2, 3, 4, 5}); // Chỉ gửi 5 bytes rồi đóng socket
                out.flush();
            }

            serverThread.join(2000);
            assertTrue(serverHandledCleanly.get(), "Server phải phát hiện thiếu payload và bắt EOFException");
        }
    }

    @Test
    @DisplayName("5. Gói tin vượt quá giới hạn kích thước tối đa (> MAX_PACKET_SIZE)")
    public void testOversizedPacket() {
        int oversized = ProtocolConstants.MAX_PACKET_SIZE + 100;
        PacketHeader oversizedHeader = new PacketHeader(
                ProtocolConstants.VERSION, 0x03, 0, 1, 1, oversized, 10, 0
        );
        byte[] payload = new byte[oversized];
        Packet packet = new Packet(oversizedHeader, payload);

        Exception exception = assertThrows(IllegalArgumentException.class, () -> {
            PacketCodec.encode(packet);
        });
        assertTrue(exception.getMessage().contains("Packet is too large"));
    }
}
