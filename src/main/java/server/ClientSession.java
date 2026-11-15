package server;

import java.io.IOException;
import java.net.Socket;

import common.Packet;
import common.PacketIO;

public class ClientSession {
    private final Socket socket;
    private final String ipAddress;
    private int userId = 0;
    private String username;

    public ClientSession(Socket socket) {
        this.socket = socket;
        this.ipAddress = socket.getInetAddress().getHostAddress();
    }

    public synchronized void sendPacket(Packet packet) throws IOException {
        if (socket != null && !socket.isClosed()) {
            PacketIO.writePacket(socket.getOutputStream(), packet);
        }
    }

    public Socket getSocket() { return socket; }
    public String getIpAddress() { return ipAddress; }
    public int getUserId() { return userId; }
    public void setUserId(int userId) { this.userId = userId; }
    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
}