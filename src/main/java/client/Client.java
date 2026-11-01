package src.main.java.client;

import src.main.java.common.*;
import src.main.java.common.payload.*;
import java.io.IOException;
import java.io.OutputStream;
import java.net.Socket;
import java.util.concurrent.atomic.AtomicInteger;

public class Client {
    private int id;
    private String sessionId;
    private final AtomicInteger sequenceCounter = new AtomicInteger(1);
    private volatile Boolean running;
    private volatile Boolean authenticated;
    private final Socket socket;

    public Client(String serverIp, int serverPort) throws IOException {
        running = true;
        authenticated = false;
        socket = new Socket(serverIp, serverPort);
    }

    public Boolean getRunning() {
        return running;
    }

    public Boolean getAuthenticated() {
        return authenticated;
    }

    public void startReceiving() {
        Thread thread = new Thread(this::receiveLoop);
        thread.start();
    }

    private void closeConnection() {
        running = false;
        authenticated = false;
        try {
            socket.close();
        }
        catch (IOException e) {
            System.out.println("Socket error: " + e.getMessage());
        }
    }

    private void receiveLoop() {}

    public void sendPacket(Packet packet) throws IOException {
        OutputStream outputStream = socket.getOutputStream();
        PacketIO.writePacket(outputStream, packet);
    }

    public Packet createSignupPacket(String username, String password) {}

    public Packet createLoginPacket(String username, String password) {}

    public Packet createLogoutPacket() throws IOException{
        if (!authenticated || sessionId == null) {
            throw new IllegalStateException("You must log in before logging out");
        }
        int sequenceNumber = sequenceCounter.getAndIncrement();
        LogoutRequest logoutRequest = new LogoutRequest(sessionId);
        byte[] payload = JsonPayloadCodec.encode(logoutRequest);
        PacketHeader header = new PacketHeader(ProtocolConstants.VERSION, MessageType.LOGOUT_REQUEST, 0, 0, sequenceNumber, payload.length, id, 0);
        return new Packet(header, payload);
    }

    public Packet createOnlineUsersListPacket() throws IOException{
        if (!authenticated || sessionId == null) {
            throw new IllegalStateException("You must log in before requesting online users");
        }
        int sequenceNumber = sequenceCounter.getAndIncrement();
        UserListRequest userListRequest = new UserListRequest(sessionId);
        byte[] payload = JsonPayloadCodec.encode(userListRequest);
        PacketHeader header = new PacketHeader(ProtocolConstants.VERSION, MessageType.USER_LIST_REQUEST, 0, 0, sequenceNumber, payload.length, id, 0);
        return new Packet(header, payload);
    }

    public Packet createPrivateChatPacket(int receiverId, String message) {}

    public Packet createGlobalChatPacket(String message) {}
}