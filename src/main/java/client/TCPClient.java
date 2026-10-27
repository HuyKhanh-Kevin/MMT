package src.main.java.client;
import java.io.IOException;
import java.net.Socket;

public class TCPClient {
    private final Socket socket;
    private volatile Boolean running;
    private volatile Boolean authenticated;

    public TCPClient(String serverIp, int serverPort) throws IOException {
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
    private void sendPacket(byte[] packet) {}
    public void sendSignupRequest(String username, String password) {}
    public void sendLoginRequest(String username, String password) {}
    public void sendLogoutRequest() {}
    public void getOnlineUsersList() {}
    public void sendPrivateChatRequest(int receiverId, String message) {}
    public void sendGlobalChatRequest(String message) {}
}