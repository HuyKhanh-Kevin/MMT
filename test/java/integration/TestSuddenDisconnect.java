package integration;

import common.Packet;
import common.PacketHeader;
import common.PacketIO;
import common.ProtocolConstants;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Ca kiểm thử 2: Client mất kết nối đột ngột (Sudden Disconnect & Connection Resilience)
 * Mục tiêu: Chứng minh Server không bị crash hoặc rò rỉ socket khi client ngắt kết nối bất ngờ.
 */
public class TestSuddenDisconnect {

    public static void main(String[] args) {
        System.out.println("=== CHẠY KIỂM THỬ: CLIENT MẤT KẾT NỐI ĐỘT NGỘT (SUDDEN DISCONNECT) ===");
        TestSuddenDisconnect tester = new TestSuddenDisconnect();
        try {
            tester.testImmediateClientDisconnect();
            System.out.println("[PASS] 1. Immediate Disconnect - Server nhận diện đóng kết nối (EOF) an toàn.");

            tester.testDisconnectMidTransmission();
            System.out.println("[PASS] 2. Disconnect Mid-Transmission - Server giải phóng tài nguyên, không bị block.");

            tester.testConcurrentClientSuddenDisconnects();
            System.out.println("[PASS] 3. Concurrent Sudden Disconnects - 5 client ngắt đồng thời, server vẫn nhận client mới bình thường.");

            System.out.println("===> TẤT CẢ CA KIỂM THỬ MẤT KẾT NỐI ĐỘT NGỘT ĐỀU THÀNH CÔNG!\n");
        } catch (Throwable t) {
            System.err.println("[FAIL] Lỗi kiểm thử: " + t.getMessage());
            t.printStackTrace();
        }
    }

    @Test
    @DisplayName("1. Client kết nối TCP rồi đóng ngay lập tức (không gửi dữ liệu)")
    public void testImmediateClientDisconnect() throws Exception {
        try (ServerSocket serverSocket = new ServerSocket(0)) {
            int port = serverSocket.getLocalPort();
            CountDownLatch serverDone = new CountDownLatch(1);

            Thread serverThread = new Thread(() -> {
                try (Socket clientSocket = serverSocket.accept();
                     InputStream in = clientSocket.getInputStream()) {
                    // Khi client đóng ngay, readPacket phải trả về null (EOF sạch sẽ)
                    Packet packet = PacketIO.readPacket(in);
                    assertNull(packet, "Server phải nhận null khi kết nối đóng trước khi gửi packet");
                } catch (IOException e) {
                    fail("Server không được quăng lỗi ngoài ý muốn khi client đóng sạch: " + e.getMessage());
                } finally {
                    serverDone.countDown();
                }
            });
            serverThread.start();

            // Client mở kết nối rồi close ngay
            Socket client = new Socket("127.0.0.1", port);
            client.close();

            assertTrue(serverDone.await(2, TimeUnit.SECONDS), "Server thread phải kết thúc gọn gàng");
        }
    }

    @Test
    @DisplayName("2. Client ngắt kết nối đột ngột giữa chừng bằng TCP RST (Linger = 0)")
    public void testDisconnectMidTransmission() throws Exception {
        try (ServerSocket serverSocket = new ServerSocket(0)) {
            int port = serverSocket.getLocalPort();
            CountDownLatch serverDone = new CountDownLatch(1);

            Thread serverThread = new Thread(() -> {
                try (Socket clientSocket = serverSocket.accept();
                     InputStream in = clientSocket.getInputStream()) {
                    // Đọc thử dữ liệu
                    PacketIO.readPacket(in);
                } catch (IOException e) {
                    // Server bắt được IOException/SocketException khi đường truyền bị đứt là đúng chuẩn mạng
                } finally {
                    serverDone.countDown();
                }
            });
            serverThread.start();

            // Client mở socket, gửi 5 bytes rồi ép ngắt bằng TCP RST (setSoLinger = true, 0)
            Socket client = new Socket("127.0.0.1", port);
            client.setSoLinger(true, 0); // Ép gửi cờ TCP RST khi close, mô phỏng crash phần mềm
            client.getOutputStream().write(new byte[]{1, 2, 3, 4, 5});
            client.close();

            assertTrue(serverDone.await(2, TimeUnit.SECONDS), "Server phải bắt SocketException và thoát luồng an toàn");
        }
    }

    @Test
    @DisplayName("3. Nhiều client (5 clients) kết nối và ngắt đồng thời, sau đó kiểm tra server vẫn sống")
    public void testConcurrentClientSuddenDisconnects() throws Exception {
        try (ServerSocket serverSocket = new ServerSocket(0)) {
            int port = serverSocket.getLocalPort();
            int clientCount = 5;
            AtomicInteger handledClients = new AtomicInteger(0);
            ExecutorService pool = Executors.newFixedThreadPool(clientCount + 1);

            // Vòng lặp nhận kết nối của server
            Thread serverListener = new Thread(() -> {
                for (int i = 0; i < clientCount; i++) {
                    try {
                        Socket socket = serverSocket.accept();
                        pool.submit(() -> {
                            try (socket; InputStream in = socket.getInputStream()) {
                                PacketIO.readPacket(in);
                            } catch (IOException ignored) {
                            } finally {
                                handledClients.incrementAndGet();
                            }
                        });
                    } catch (IOException e) {
                        break;
                    }
                }
            });
            serverListener.start();

            // Khởi chạy 5 client kết nối và ngắt đột ngột
            for (int i = 0; i < clientCount; i++) {
                new Thread(() -> {
                    try {
                        Socket c = new Socket("127.0.0.1", port);
                        c.setSoLinger(true, 0);
                        c.getOutputStream().write(new byte[]{0x02, 0x01});
                        c.close();
                    } catch (IOException ignored) {
                    }
                }).start();
            }

            // Chờ server xử lý hết 5 client ngắt
            long start = System.currentTimeMillis();
            while (handledClients.get() < clientCount && System.currentTimeMillis() - start < 3000) {
                Thread.sleep(100);
            }
            assertEquals(clientCount, handledClients.get(), "Server phải xử lý đủ 5 client bị ngắt");

            // Kiểm tra tính sống còn (Health Check): Kết nối 1 client hợp lệ tiếp theo
            CountDownLatch validClientDone = new CountDownLatch(1);
            Thread validWorker = new Thread(() -> {
                try (Socket healthyClient = serverSocket.accept();
                     InputStream in = healthyClient.getInputStream()) {
                    Packet p = PacketIO.readPacket(in);
                    assertNotNull(p, "Server vẫn phải nhận packet từ client mới bình thường");
                    validClientDone.countDown();
                } catch (IOException e) {
                    fail("Server không phản hồi sau hàng loạt kết nối lỗi: " + e.getMessage());
                }
            });
            validWorker.start();

            // Gửi 1 packet hợp lệ
            try (Socket healthySender = new Socket("127.0.0.1", port)) {
                PacketHeader header = new PacketHeader(
                        ProtocolConstants.VERSION, 0x05, 0, 1, 1, 4, 1, 0 // HEARTBEAT
                );
                Packet packet = new Packet(header, "PING".getBytes());
                PacketIO.writePacket(healthySender.getOutputStream(), packet);
            }

            assertTrue(validClientDone.await(2, TimeUnit.SECONDS), "Server vẫn hoạt động trơn tru sau bão kết nối lỗi!");
            pool.shutdownNow();
        }
    }
}
