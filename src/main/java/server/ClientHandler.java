package server;

import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;

import common.MessageType;
import common.Packet;
import common.PacketIO;

public class ClientHandler implements Runnable {
    private final ClientSession session;
    private final SessionManager sessionManager;

    public ClientHandler(ClientSession session, SessionManager sessionManager) {
        this.session = session;
        this.sessionManager = sessionManager;
    }

    @Override
    public void run() {
        try (InputStream in = session.getSocket().getInputStream()) {
            while (!session.getSocket().isClosed()) {
                // Đọc packet hoàn chỉnh qua PacketIO của Khánh
                Packet packet = PacketIO.readPacket(in);
                if (packet == null) {
                    break; // Kết nối đã đóng
                }

                int msgType = packet.getHeader().getMessageType();

                // PHỐI HỢP VỚI CA: Chuyển tiếp tin nhắn Chat (0x03)
                if (msgType == MessageType.CHAT_MESSAGE || msgType == 0x03) {
                    relayChatMessage(packet);
                } 
                // GHẾP HANDLER CỦA ĐÔNG: Các gói tin Login, Logout...
                else {
                    dispatchToDongHandlers(packet);
                }
            }
        } catch (EOFException | java.net.SocketException e) {
            System.out.println("[SERVER] Client " + session.getIpAddress() + " ngắt kết nối an toàn.");
        } catch (Exception e) {
            System.err.println("[SERVER] Lỗi xử lý Client: " + e.getMessage());
        } finally {
            // XỬ LÝ NGẮT KẾT NỐI: Dọn dẹp tài nguyên để không làm Server dừng
            sessionManager.removeSession(session);
            try { session.getSocket().close(); } catch (IOException ignored) {}
        }
    }

    private void relayChatMessage(Packet packet) {
        int receiverId = packet.getHeader().getReceiverID();

        try {
            if (receiverId == 0) {
                // Broadcast: Gửi tới tất cả client ngoại trừ người gửi
                for (ClientSession target : sessionManager.getAllSessions()) {
                    if (target.getUserId() != session.getUserId()) {
                        target.sendPacket(packet);
                    }
                }
            } else {
                // Unicast: Gửi trực tiếp tới 1 client
                ClientSession target = sessionManager.getSession(receiverId);
                if (target != null) {
                    target.sendPacket(packet);
                } else {
                    System.out.println("[SERVER] User " + receiverId + " đang offline.");
                }
            }
        } catch (IOException e) {
            System.err.println("[SERVER] Lỗi chuyển tiếp chat: " + e.getMessage());
        }
    }

    private void dispatchToDongHandlers(Packet packet) {
        // Nơi gọi các handler nghiệp vụ của Đông khi Đông commit code
    }
}