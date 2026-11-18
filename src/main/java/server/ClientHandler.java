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
                Packet packet = PacketIO.readPacket(in);
                if (packet == null) {
                    break;
                }

                int msgType = packet.getHeader().getMessageType();

                if (msgType == MessageType.CHAT_MESSAGE || msgType == 0x03) {
                    relayChatMessage(packet);
                } 
                else {
                    dispatchToDongHandlers(packet);
                }
            }
        } catch (EOFException | java.net.SocketException e) {
            System.out.println("[SERVER] Client " + session.getIpAddress() + " ngắt kết nối an toàn.");
        } catch (Exception e) {
            System.err.println("[SERVER] Lỗi xử lý Client: " + e.getMessage());
        } finally {
            sessionManager.removeSession(session);
            try { session.getSocket().close(); } catch (IOException ignored) {}
        }
    }

    private void relayChatMessage(Packet packet) {
        int receiverId = packet.getHeader().getReceiverID();

        try {
            if (receiverId == 0) {
                for (ClientSession target : sessionManager.getAllSessions()) {
                    if (target.getUserId() != session.getUserId()) {
                        target.sendPacket(packet);
                    }
                }
            } else {
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
    }
}