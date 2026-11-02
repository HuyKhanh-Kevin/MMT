package src.main.java.client;

import src.main.java.common.*;
import src.main.java.common.payload.*;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.DatagramSocket;
import java.net.InetSocketAddress;
import java.net.SocketException;
import java.net.Socket;
import java.util.concurrent.atomic.AtomicInteger;

public class Client {
    private int id;
    private String sessionId;
    private final AtomicInteger sequenceCounter = new AtomicInteger(1);
    private volatile Boolean running;
    private volatile Boolean authenticated;
    private final int peerTCPPort;
    private final int fileUDPPort;
    private final Socket TCPSocket;
    private final DatagramSocket UDPSocket;
    private final InetSocketAddress serverUdpAddress;

    public Client(String serverIp, int serverPort, int udpPort, int peerTCPPort, int fileUDPPort) throws IOException {
        running = true;
        authenticated = false;
        TCPSocket = new Socket(serverIp, serverPort);
        UDPSocket = new DatagramSocket(0);
        serverUdpAddress = new InetSocketAddress(serverIp, udpPort);
        this.peerTCPPort = peerTCPPort;
        this.fileUDPPort = fileUDPPort;
    }

    public Boolean getRunning() {
        return running;
    }

    public Boolean getAuthenticated() {
        return authenticated;
    }

    public void startReceiving() {
        new Thread(this::receiveTCPLoop, "tcp-receiver").start();
        new Thread(this::receiveUDPLoop, "udp-receiver").start();
    }

    private void closeConnection() {
        running = false;
        authenticated = false;
        UDPSocket.close();
        try {
            TCPSocket.close();
        }
        catch (IOException e) {
            System.out.println("Socket error: " + e.getMessage());
        }
    }

    private void receiveTCPLoop() {
        try {
            InputStream inputStream = TCPSocket.getInputStream();
            while (running) {
                Packet packet = PacketIO.readPacket(inputStream);
                if (packet == null) break;
            }
        }
        catch (IOException e) {
            if (running) {
                System.out.println("TCP receive error: " + e.getMessage());
            }
        }
        finally {
            closeConnection();
        }
    }

    private void receiveUDPLoop() {
        while (running) {
            try {
                UdpPacketIO.ReceivedPacket packet = UdpPacketIO.receivePacket(UDPSocket);
            }
            catch (SocketException e) {
                if (running) {
                    System.out.println("UDP socket error: " + e.getMessage());
                }
                break;
            }
            catch (IOException e) {
                if (running) {
                    System.out.println("UDP receive error: " + e.getMessage());
                }
            }
        }
    }

    public void sendTCPPacket(Packet packet) throws IOException {
        OutputStream outputStream = TCPSocket.getOutputStream();
        PacketIO.writePacket(outputStream, packet);
    }

    public void sendUDPPacket(Packet packet) throws IOException {
        UdpPacketIO.sendPacket(UDPSocket, serverUdpAddress, packet);
    }

    public Packet createSignupPacket(String username, String password) {}

    public Packet createLoginPacket(String username, String password) throws IOException {
        if (authenticated) {
            throw new IllegalStateException("You are already logged in");
        }
        int sequenceNumber = sequenceCounter.getAndIncrement();
        LoginRequest loginRequest = new LoginRequest(username, password, peerTCPPort, fileUDPPort);
        byte[] payload = JsonPayloadCodec.encode(loginRequest);
        PacketHeader header = new PacketHeader(ProtocolConstants.VERSION, MessageType.LOGIN_REQUEST, 0, 0, sequenceNumber, payload.length, 0, 0);
        return new Packet(header, payload);
    }

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

    public Packet createPrivateChatPacket(int receiverId, String message) throws IOException {
        if (!authenticated || sessionId == null) {
            throw new IllegalStateException("You must log in before sending private messages");
        }
        int sequenceNumber = sequenceCounter.getAndIncrement();
        ChatMessage chatMessage = new ChatMessage(message);
        byte[] payload = JsonPayloadCodec.encode(chatMessage);
        PacketHeader header = new PacketHeader(ProtocolConstants.VERSION, MessageType.CHAT_MESSAGE, 0, 0, sequenceNumber, payload.length, id, receiverId);
        return new Packet(header, payload);
    }

    public Packet createGlobalChatPacket(String message) throws IOException {
        if (!authenticated || sessionId == null) {
            throw new IllegalStateException("You must log in before sending global messages");
        }
        int sequenceNumber = sequenceCounter.getAndIncrement();
        ChatMessage chatMessage = new ChatMessage(message);
        byte[] payload = JsonPayloadCodec.encode(chatMessage);
        PacketHeader header = new PacketHeader(ProtocolConstants.VERSION, MessageType.CHAT_MESSAGE, 0, 0, sequenceNumber, payload.length, id, 0);
        return new Packet(header, payload);
    }
}