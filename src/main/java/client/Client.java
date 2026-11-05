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
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class Client {
    private int id;
    private String sessionId;
    private final AtomicInteger TCPSequenceCounter = new AtomicInteger(1);
    private final AtomicInteger UDPSequenceCounter = new AtomicInteger(1);
    private final AtomicInteger heartbeatCounter = new AtomicInteger(1);
    private volatile Boolean running;
    private volatile Boolean authenticated;
    private final int peerTCPPort;
    private final int fileUDPPort;
    private final Socket TCPSocket;
    private final DatagramSocket UDPSocket;
    private final InetSocketAddress serverUdpAddress;
    private ClientListener listener;
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();
    private ScheduledFuture<?> heartbeatTask;

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

    public void setListener(ClientListener listener) {
        this.listener = listener;
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
        if (heartbeatTask != null) {
            heartbeatTask.cancel(false);
        }
        scheduler.shutdownNow();
    }

    private void receiveTCPLoop() {
        try {
            InputStream inputStream = TCPSocket.getInputStream();
            while (running) {
                Packet packet = PacketIO.readPacket(inputStream);
                if (packet == null) break;
                switch (packet.getHeader().getMessageType()) {
                    case MessageType.SIGNUP_RESPONSE -> {
                        SignupResponse signupResponse = JsonPayloadCodec.decode(packet.getPayload(), SignupResponse.class);
                        listener.displaySignupResponse(signupResponse.status, signupResponse.reason);
                    }
                    case MessageType.LOGIN_RESPONSE -> {
                        LoginResponse loginResponse = JsonPayloadCodec.decode(packet.getPayload(), LoginResponse.class);
                        if (loginResponse.getStatus().equals("success")) {
                            id = loginResponse.getUserID().intValue();
                            sessionId = loginResponse.getSessionID();
                            authenticated = true;
                            startHeartbeat();
                        }
                        listener.displayLoginResponse(loginResponse.getStatus(), loginResponse.getReason());
                    }
                    case MessageType.LOGOUT_RESPONSE -> {
                        LogoutResponse logoutResponse = JsonPayloadCodec.decode(packet.getPayload(), LogoutResponse.class);
                        if (logoutResponse.getStatus().equals("success")) {
                            listener.displayLogoutResponse();
                            closeConnection();
                        }
                    }
                    case MessageType.CHAT_MESSAGE -> {
                        ChatMessage chatMessage = JsonPayloadCodec.decode(packet.getPayload(), ChatMessage.class);
                        listener.displayMessage(packet.getHeader().getSenderID(), chatMessage.getText());
                    }
                }
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
                UdpPacketIO.ReceivedPacket receivedPacket = UdpPacketIO.receivePacket(UDPSocket);
                if (!serverUdpAddress.equals(receivedPacket.source())) continue;
                Packet packet = receivedPacket.packet();
                switch (packet.getHeader().getMessageType()) {
                    case MessageType.USER_LIST_RESPONSE -> {
                        UserListResponse userListResponse = JsonPayloadCodec.decode(packet.getPayload(), UserListResponse.class);
                        listener.displayUserList(userListResponse.getUsers());
                    }
                }
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

    private void startHeartbeat() {
        if (heartbeatTask != null && !heartbeatTask.isDone()) {
            return;
        }
        heartbeatTask = scheduler.scheduleAtFixedRate(() -> {
            if (!authenticated) return;
            try {
                Packet packet = createHeartbeatPacket();
                sendUDPPacket(packet);
            }
            catch (IOException e) {
                System.out.println("Heartbeat error: " + e.getMessage());
            }
        }, 5, 5, TimeUnit.SECONDS);
    }

    public Packet createSignupPacket(String username, String password) throws IOException {
        SignupRequest signupRequest = new SignupRequest(username, password);
        byte[] payload = JsonPayloadCodec.encode(signupRequest);
        int sequenceNumber = TCPSequenceCounter.getAndIncrement();
        PacketHeader header = new PacketHeader(ProtocolConstants.VERSION, MessageType.SIGNUP_REQUEST, 0, 0, sequenceNumber, payload.length, 0, 0);
        return new Packet(header, payload);
    }

    public Packet createLoginPacket(String username, String password) throws IOException {
        if (authenticated) {
            throw new IllegalStateException("You are already logged in");
        }
        LoginRequest loginRequest = new LoginRequest(username, password, peerTCPPort, fileUDPPort);
        byte[] payload = JsonPayloadCodec.encode(loginRequest);
        int sequenceNumber = TCPSequenceCounter.getAndIncrement();
        PacketHeader header = new PacketHeader(ProtocolConstants.VERSION, MessageType.LOGIN_REQUEST, 0, 0, sequenceNumber, payload.length, 0, 0);
        return new Packet(header, payload);
    }

    public Packet createLogoutPacket() throws IOException{
        if (!authenticated || sessionId == null) {
            throw new IllegalStateException("You must log in before logging out");
        }
        LogoutRequest logoutRequest = new LogoutRequest(sessionId);
        byte[] payload = JsonPayloadCodec.encode(logoutRequest);
        int sequenceNumber = TCPSequenceCounter.getAndIncrement();
        PacketHeader header = new PacketHeader(ProtocolConstants.VERSION, MessageType.LOGOUT_REQUEST, 0, 0, sequenceNumber, payload.length, id, 0);
        return new Packet(header, payload);
    }

    public Packet createOnlineUsersListPacket() throws IOException{
        if (!authenticated || sessionId == null) {
            throw new IllegalStateException("You must log in before requesting online users");
        }
        UserListRequest userListRequest = new UserListRequest(sessionId);
        byte[] payload = JsonPayloadCodec.encode(userListRequest);
        int sequenceNumber = UDPSequenceCounter.getAndIncrement();
        PacketHeader header = new PacketHeader(ProtocolConstants.VERSION, MessageType.USER_LIST_REQUEST, 0, 0, sequenceNumber, payload.length, id, 0);
        return new Packet(header, payload);
    }

    public Packet createPrivateChatPacket(int receiverId, String message) throws IOException {
        if (!authenticated || sessionId == null) {
            throw new IllegalStateException("You must log in before sending private messages");
        }
        ChatMessage chatMessage = new ChatMessage(message);
        byte[] payload = JsonPayloadCodec.encode(chatMessage);
        int sequenceNumber = TCPSequenceCounter.getAndIncrement();
        PacketHeader header = new PacketHeader(ProtocolConstants.VERSION, MessageType.CHAT_MESSAGE, 0, 0, sequenceNumber, payload.length, id, receiverId);
        return new Packet(header, payload);
    }

    public Packet createGlobalChatPacket(String message) throws IOException {
        if (!authenticated || sessionId == null) {
            throw new IllegalStateException("You must log in before sending global messages");
        }
        ChatMessage chatMessage = new ChatMessage(message);
        byte[] payload = JsonPayloadCodec.encode(chatMessage);
        int sequenceNumber = TCPSequenceCounter.getAndIncrement();
        PacketHeader header = new PacketHeader(ProtocolConstants.VERSION, MessageType.CHAT_MESSAGE, 0, 0, sequenceNumber, payload.length, id, 0);
        return new Packet(header, payload);
    }

    private Packet createHeartbeatPacket() throws IOException {
        int heartbeatSequence = heartbeatCounter.getAndIncrement();
        Heartbeat heartbeat = new Heartbeat(sessionId, heartbeatSequence);
        byte[] payload = JsonPayloadCodec.encode(heartbeat);
        int sequenceNumber = UDPSequenceCounter.getAndIncrement();
        PacketHeader header = new PacketHeader(ProtocolConstants.VERSION, MessageType.HEARTBEAT, 0, 0, sequenceNumber, payload.length, id, 0);
        return new Packet(header, payload);
    }
}