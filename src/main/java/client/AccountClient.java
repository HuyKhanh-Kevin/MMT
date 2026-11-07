package client;

import common.*;
import common.payload.*;

import java.io.IOException;
import java.net.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;

/** Small reference client for integrating the account module into the team's UI. */
public final class AccountClient implements AutoCloseable {
    private record Login(String token, int userID, AtomicLong heartbeatSequence) {}
    private final Object stateLock = new Object();
    private final Socket tcp;
    private final DatagramSocket udp;
    private final InetSocketAddress serverUDP;
    private final int peerTCPPort;
    private final int fileUDPPort;
    private final AtomicInteger sequence = new AtomicInteger();
    private final Map<Integer, CompletableFuture<Packet>> pending = new ConcurrentHashMap<>();
    private final Map<Integer, CompletableFuture<Packet>> pendingTCP = new ConcurrentHashMap<>();
    private final ScheduledExecutorService heartbeat = Executors.newSingleThreadScheduledExecutor();
    private final ExecutorService receiver = Executors.newFixedThreadPool(2);
    private final ExecutorService callbacks = Executors.newSingleThreadExecutor();
    private volatile Consumer<PresenceUpdate> presenceListener = update -> {};
    private volatile Login login;
    private volatile boolean closed;
    private volatile boolean heartbeatsEnabled = true;

    public AccountClient(String host, int serverTCPPort, int serverUDPPort, int peerTCPPort, int fileUDPPort)
            throws IOException {
        if (peerTCPPort < 1 || peerTCPPort > 65535 || fileUDPPort < 1 || fileUDPPort > 65535) {
            throw new IllegalArgumentException("Invalid local peer ports");
        }
        this.peerTCPPort = peerTCPPort;
        this.fileUDPPort = fileUDPPort;
        tcp = new Socket();
        DatagramSocket datagram = null;
        try {
            tcp.connect(new InetSocketAddress(host, serverTCPPort), 3000);
            // The reader also watches for EOF while the UI is idle. Request deadlines use futures.
            tcp.setSoTimeout(0);
            datagram = new DatagramSocket();
            serverUDP = new InetSocketAddress(tcp.getInetAddress(), serverUDPPort);
            datagram.connect(serverUDP);
        } catch (IOException | RuntimeException e) {
            tcp.close();
            if (datagram != null) datagram.close();
            throw e;
        }
        udp = datagram;
        receiver.execute(this::receiveLoop);
        receiver.execute(this::receiveControlLoop);
        heartbeat.scheduleAtFixedRate(this::sendHeartbeat, 0, 5, TimeUnit.SECONDS);
    }

    public void onPresence(Consumer<PresenceUpdate> listener) {
        presenceListener = Objects.requireNonNull(listener);
    }

    public boolean isAuthenticated() { return login != null; }
    public boolean isConnected() { return !closed; }
    public int userID() { Login current = login; return current == null ? 0 : current.userID(); }
    public String sessionID() { Login current = login; return current == null ? null : current.token(); }

    public synchronized SignupResponse signup(String username, String password) throws IOException {
        requireLoggedOut();
        return JsonPayloadCodec.decode(control(MessageType.SIGNUP_REQUEST, MessageType.SIGNUP_RESPONSE,
                0, new SignupRequest(username, password)).getPayload(), SignupResponse.class);
    }

    public synchronized LoginResponse login(String username, String password) throws IOException {
        requireLoggedOut();
        LoginResponse response = JsonPayloadCodec.decode(control(MessageType.LOGIN_REQUEST, MessageType.LOGIN_RESPONSE,
                0, new LoginRequest(username, password, peerTCPPort, fileUDPPort)).getPayload(), LoginResponse.class);
        if (response.isStatus()) {
            if (response.getSessionID() == null || response.getUserID() == null) throw new IOException("Incomplete login response");
            synchronized (stateLock) {
                if (closed) throw new IOException("Server closed the connection; reconnect");
                login = new Login(response.getSessionID(), response.getUserID(), new AtomicLong());
            }
            sendHeartbeat(); // Register this socket's actual UDP source port immediately.
        }
        return response;
    }

    public synchronized void logout() throws IOException {
        Login current = requireLogin();
        try {
            control(MessageType.LOGOUT_REQUEST, MessageType.LOGOUT_RESPONSE,
                    current.userID(), new LogoutRequest(current.token()));
        } finally {
            login = null;
        }
    }

    /** Walk all pages, retry each lost UDP request at most three times with the same reference. */
    public synchronized List<UserInfo> onlineUsers() throws IOException {
        Login current = requireLogin();
        List<UserInfo> users = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        String cursor = null;
        do {
            Packet request = ControlPackets.create(MessageType.USER_LIST_REQUEST, nextSequence(), current.userID(), 0,
                    new UserListRequest(current.token(), cursor));
            Packet response = requestUDP(request);
            if (response.getHeader().getMessageType() != Integer.decode(MessageType.USER_LIST_RESPONSE)) {
                throw new IOException("Unexpected discovery response");
            }
            UserListResponse page = JsonPayloadCodec.decode(response.getPayload(), UserListResponse.class);
            users.addAll(page.getUsers());
            cursor = page.getNextCursor();
            if (cursor != null && !seen.add(cursor)) throw new IOException("Repeated discovery cursor");
        } while (cursor != null);
        return List.copyOf(users);
    }

    /** Refresh discovery before selecting the TCP control and UDP data endpoints for a transfer. */
    public PeerEndpoint peerEndpoint(long userID) throws IOException {
        if (userID < 1 || userID > 0xFFFF_FFFFL) throw new IllegalArgumentException("Invalid user ID");
        UserInfo user = onlineUsers().stream().filter(peer -> peer.userID() == userID).findFirst()
                .orElseThrow(() -> new IOException(ErrorCode.RECIPIENT_OFFLINE + ": RECIPIENT_OFFLINE"));
        InetAddress address = InetAddress.getByName(user.ip());
        return new PeerEndpoint(user.userID(), user.username(),
                new InetSocketAddress(address, user.tcpPort()),
                new InetSocketAddress(address, user.fileUdpPort()));
    }

    /** Demo/test switch: keep TCP open but stop heartbeat to simulate a silent network failure. */
    public void setHeartbeatsEnabled(boolean enabled) { heartbeatsEnabled = enabled; }

    private Packet control(String type, String expected, int sender, Object body) throws IOException {
        Packet request = ControlPackets.create(type, nextSequence(), sender, 0, body);
        CompletableFuture<Packet> future = new CompletableFuture<>();
        int reference = request.getHeader().getSequenceNumber();
        pendingTCP.put(reference, future);
        Packet response;
        try {
            if (closed) throw new IOException("Connection is closed; reconnect");
            PacketIO.writePacket(tcp.getOutputStream(), request);
            response = future.get(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            close();
            throw new IOException("Control request interrupted", e);
        } catch (ExecutionException | TimeoutException | IOException e) {
            close();
            throw new IOException("Control connection failed; reconnect", e);
        } finally {
            pendingTCP.remove(reference);
        }
        if (response.getHeader().getSenderID() != 0 || response.getHeader().getStreamID() != 0
                || response.getHeader().getSequenceNumber() != request.getHeader().getSequenceNumber()) {
            throw new IOException("Unmatched control response");
        }
        checkError(response);
        if (response.getHeader().getMessageType() != Integer.decode(expected)) throw new IOException("Unexpected response");
        return response;
    }

    private void receiveControlLoop() {
        try {
            Packet response;
            while (!closed && (response = PacketIO.readPacket(tcp.getInputStream())) != null) {
                PacketHeader header = response.getHeader();
                if (header.getSenderID() != 0 || header.getStreamID() != 0 || header.getFlags() != 0) {
                    throw new IOException("Invalid control response header");
                }
                CompletableFuture<Packet> future = pendingTCP.get(header.getSequenceNumber());
                if (future == null) throw new IOException("Unexpected control response");
                future.complete(response);
            }
        } catch (IOException e) {
            // EOF/reset/timeout closes the local session even if the UI sends no more requests.
        } finally {
            close();
        }
    }

    private Packet requestUDP(Packet request) throws IOException {
        int reference = request.getHeader().getSequenceNumber();
        CompletableFuture<Packet> future = new CompletableFuture<>();
        pending.put(reference, future);
        try {
            if (closed) throw new IOException("Connection is closed; reconnect");
            for (int attempt = 0; attempt < 3; attempt++) {
                UdpPacketIO.sendPacket(udp, serverUDP, request);
                try {
                    Packet response = future.get(1, TimeUnit.SECONDS);
                    checkError(response);
                    return response;
                } catch (TimeoutException e) {
                    // Retrying the same cursor returns the same snapshot page.
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IOException("Discovery interrupted", e);
                } catch (ExecutionException e) {
                    throw new IOException("Discovery failed", e.getCause());
                }
            }
            throw new SocketTimeoutException("Discovery timed out after 3 attempts");
        } finally {
            pending.remove(reference);
        }
    }

    private void sendHeartbeat() {
        Login current = login;
        if (closed || current == null || !heartbeatsEnabled) return;
        try {
            long counter = current.heartbeatSequence().incrementAndGet();
            if (counter > 0xFFFF_FFFFL) return; // Session renewal is required at counter exhaustion.
            UdpPacketIO.sendPacket(udp, serverUDP, ControlPackets.create(MessageType.HEARTBEAT,
                    nextSequence(), current.userID(), 0, new Heartbeat(current.token(), counter)));
        } catch (IOException e) {
            // UDP failure does not stop the scheduler; the server applies the heartbeat deadline.
        }
    }

    private void receiveLoop() {
        while (!closed) {
            try {
                Packet packet = UdpPacketIO.receivePacket(udp).packet();
                Login current = login;
                if (current == null || packet.getHeader().getSenderID() != 0
                        || packet.getHeader().getReceiverID() != current.userID()
                        || packet.getHeader().getStreamID() != 0 || packet.getHeader().getFlags() != 0) continue;
                if (packet.getHeader().getMessageType() == Integer.decode(MessageType.PRESENCE_UPDATE)) {
                    PresenceUpdate update = JsonPayloadCodec.decode(packet.getPayload(), PresenceUpdate.class);
                    try {
                        callbacks.execute(() -> {
                            if (closed || login != current) return;
                            try { presenceListener.accept(update); }
                            catch (RuntimeException ignored) { /* Isolate UI callback failures. */ }
                        });
                    } catch (RejectedExecutionException ignored) { /* Client is closing. */ }
                } else {
                    CompletableFuture<Packet> future = pending.get(packet.getHeader().getSequenceNumber());
                    if (future != null) future.complete(packet);
                }
            } catch (IOException e) {
                if (closed) return;
            }
        }
    }

    private void checkError(Packet response) throws IOException {
        if (response.getHeader().getMessageType() == Integer.decode(MessageType.ERROR)) {
            ErrorPayload error = JsonPayloadCodec.decode(response.getPayload(), ErrorPayload.class);
            if (error.getErrorCode() == ErrorCode.UNAUTHENTICATED) login = null;
            throw new IOException(error.getErrorCode() + ": " + error.getErrorMessage());
        }
    }

    private int nextSequence() {
        int value = sequence.incrementAndGet();
        if (value == 0) throw new IllegalStateException("Packet reference space exhausted; reconnect");
        return value;
    }

    private Login requireLogin() throws IOException {
        Login current = login;
        if (current == null) throw new IOException("Login required");
        return current;
    }

    private void requireLoggedOut() throws IOException {
        if (closed) throw new IOException("Client is closed");
        if (login != null) throw new IOException("Already logged in");
    }

    @Override
    public void close() {
        synchronized (stateLock) {
            if (closed) return;
            closed = true;
            login = null;
        }
        heartbeat.shutdownNow();
        udp.close();
        try { tcp.close(); } catch (IOException ignored) { }
        pending.values().forEach(f -> f.completeExceptionally(new IOException("Client is closed")));
        pendingTCP.values().forEach(f -> f.completeExceptionally(new IOException("Client is closed")));
        receiver.shutdownNow();
        callbacks.shutdownNow();
    }
}
