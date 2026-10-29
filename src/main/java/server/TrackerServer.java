package server;

import common.*;
import common.payload.*;

import java.io.IOException;
import java.net.*;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import java.util.logging.Logger;

/** Raw TCP account control and UDP heartbeat/discovery server. */
public final class TrackerServer implements AutoCloseable {
    private static final Logger LOG = Logger.getLogger(TrackerServer.class.getName());
    private final AccountStore accounts;
    private final SessionRegistry sessions;
    private final OnlineDirectory directory = new OnlineDirectory();
    private final ServerSocket tcp;
    private final DatagramSocket udp;
    private final Map<UUID, Socket> connections = new ConcurrentHashMap<>();
    private final ExecutorService loops = Executors.newFixedThreadPool(2);
    private final ThreadPoolExecutor workers = new ThreadPoolExecutor(0, 64, 30, TimeUnit.SECONDS,
            new SynchronousQueue<>());
    private final ScheduledExecutorService monitor = Executors.newSingleThreadScheduledExecutor();
    private final AtomicInteger presenceSequence = new AtomicInteger();
    private volatile boolean running;

    public TrackerServer(String bindIP, int tcpPort, int udpPort, Path accountFile) throws IOException {
        this(bindIP, tcpPort, udpPort, accountFile, SessionRegistry.DEFAULT_TIMEOUT);
    }

    public TrackerServer(String bindIP, int tcpPort, int udpPort, Path accountFile, Duration timeout)
            throws IOException {
        accounts = new AccountStore(accountFile);
        sessions = new SessionRegistry(timeout, System::nanoTime);
        tcp = new ServerSocket();
        DatagramSocket datagram = null;
        try {
            tcp.bind(new InetSocketAddress(bindIP, tcpPort));
            datagram = new DatagramSocket(new InetSocketAddress(bindIP, udpPort));
        } catch (IOException | RuntimeException e) {
            tcp.close();
            if (datagram != null) datagram.close();
            throw e;
        }
        udp = datagram;
    }

    public synchronized void start() {
        if (running) return;
        if (tcp.isClosed()) throw new IllegalStateException("Server is closed");
        running = true;
        loops.execute(this::acceptLoop);
        loops.execute(this::udpLoop);
        monitor.scheduleAtFixedRate(this::maintenance, 100, 100, TimeUnit.MILLISECONDS);
    }

    public int tcpPort() { return tcp.getLocalPort(); }
    public int udpPort() { return udp.getLocalPort(); }
    public SessionRegistry sessions() { return sessions; }

    private void acceptLoop() {
        while (running) {
            Socket socket = null;
            UUID connection = UUID.randomUUID();
            try {
                socket = tcp.accept();
                socket.setTcpNoDelay(true);
                socket.setSoTimeout(15_000);
                connections.put(connection, socket);
                Socket accepted = socket;
                workers.execute(() -> controlLoop(connection, accepted));
            } catch (RejectedExecutionException e) {
                connections.remove(connection);
                closeQuietly(socket);
            } catch (IOException e) {
                connections.remove(connection);
                closeQuietly(socket);
                if (running) LOG.log(Level.WARNING, "TCP accept failed", e);
            }
        }
    }

    private void controlLoop(UUID connection, Socket socket) {
        try (socket) {
            Packet request;
            while (running && (request = PacketIO.readPacket(socket.getInputStream())) != null) {
                Packet response;
                try {
                    validateHeader(request);
                    response = handleControl(connection, socket, request);
                } catch (AccountException e) {
                    response = error(request, e.code(), e.getMessage());
                } catch (IOException | IllegalArgumentException e) {
                    response = error(request, ErrorCode.INVALID_PAYLOAD, "INVALID_PAYLOAD");
                }
                PacketIO.writePacket(socket.getOutputStream(), response);
                publishChanges();
            }
        } catch (IOException e) {
            // Includes EOF midway through a frame, reset connections, and idle pre-login timeout.
            LOG.fine("Control connection ended: " + e.getClass().getSimpleName());
        } finally {
            connections.remove(connection);
            sessions.disconnect(connection);
            publishChanges();
        }
    }

    private Packet handleControl(UUID connection, Socket socket, Packet request)
            throws IOException, AccountException {
        int type = request.getHeader().getMessageType();
        int sender = request.getHeader().getSenderID();
        if (type == Integer.decode(MessageType.SIGNUP_REQUEST)) {
            if (sender != 0 || sessions.hasSession(connection)) throw invalid("ALREADY_AUTHENTICATED");
            SignupRequest signup = JsonPayloadCodec.decode(request.getPayload(), SignupRequest.class);
            SignupResponse response;
            try {
                accounts.signup(signup.username(), signup.password());
                response = new SignupResponse("success");
            } catch (AccountException e) {
                response = new SignupResponse("failed", e.getMessage());
            } catch (IOException e) {
                LOG.log(Level.WARNING, "Account persistence failed", e);
                response = new SignupResponse("failed", "ACCOUNT_STORE_UNAVAILABLE");
            }
            return reply(request, MessageType.SIGNUP_RESPONSE, 0, response);
        }
        if (type == Integer.decode(MessageType.LOGIN_REQUEST)) {
            if (sender != 0 || sessions.hasSession(connection)) throw invalid("ALREADY_AUTHENTICATED");
            LoginRequest login = JsonPayloadCodec.decode(request.getPayload(), LoginRequest.class);
            LoginResponse response;
            try {
                if (login.getTcpPort() < 1 || login.getTcpPort() > 65535
                        || login.getFileUdpPort() < 1 || login.getFileUdpPort() > 65535) throw invalid("INVALID_PORT");
                AccountStore.Account account = accounts.authenticate(login.getUsername(), login.getPassword());
                SessionRegistry.CreatedSession session = sessions.login(account, socket.getInetAddress(),
                        login.getTcpPort(), login.getFileUdpPort(), connection);
                socket.setSoTimeout(0);
                response = new LoginResponse(true, session.sessionID(), account.userID(), null);
            } catch (AccountException e) {
                response = new LoginResponse(false, null, 0, e.getMessage());
            }
            return reply(request, MessageType.LOGIN_RESPONSE, response.isStatus() ? response.getUserID() : 0, response);
        }
        if (type == Integer.decode(MessageType.LOGOUT_REQUEST)) {
            LogoutRequest logout = JsonPayloadCodec.decode(request.getPayload(), LogoutRequest.class);
            sessions.logout(logout.getSessionID(), sender, connection);
            socket.setSoTimeout(15_000);
            return reply(request, MessageType.LOGOUT_RESPONSE, sender, new LogoutResponse("success"));
        }
        throw invalid("UNSUPPORTED_TCP_MESSAGE");
    }

    private void udpLoop() {
        while (running) {
            UdpPacketIO.ReceivedPacket received;
            try {
                received = UdpPacketIO.receivePacket(udp);
            } catch (IOException e) {
                if (!running) return;
                // An undecodable datagram has no trustworthy request reference; drop it.
                continue;
            }
            Packet request = received.packet();
            try {
                validateHeader(request);
                int type = request.getHeader().getMessageType();
                int sender = request.getHeader().getSenderID();
                if (type == Integer.decode(MessageType.HEARTBEAT)) {
                    Heartbeat heartbeat = JsonPayloadCodec.decode(request.getPayload(), Heartbeat.class);
                    sessions.heartbeat(heartbeat.getSessionID(), sender, heartbeat.getHeartbeatSeq(), received.source());
                } else if (type == Integer.decode(MessageType.USER_LIST_REQUEST)) {
                    UserListRequest list = JsonPayloadCodec.decode(request.getPayload(), UserListRequest.class);
                    sessions.authenticateUdp(list.getSessionID(), sender, received.source());
                    UserListResponse page = directory.page(list.getSessionID(), list.getCursor(),
                            sessions.onlinePeers().stream().map(SessionRegistry.Peer::userInfo).toList());
                    UdpPacketIO.sendPacket(udp, received.source(), reply(request, MessageType.USER_LIST_RESPONSE, sender, page));
                } else {
                    throw invalid("UNSUPPORTED_UDP_MESSAGE");
                }
            } catch (AccountException e) {
                sendUdpError(received, e.code(), e.getMessage());
            } catch (IOException | IllegalArgumentException e) {
                sendUdpError(received, ErrorCode.INVALID_PAYLOAD, "INVALID_PAYLOAD");
            }
            publishChanges();
        }
    }

    private void maintenance() {
        try {
            sessions.expire();
            for (UUID connection : sessions.drainDisconnectedConnections()) {
                closeQuietly(connections.get(connection));
            }
            directory.cleanup();
            publishChanges();
        } catch (RuntimeException e) {
            LOG.log(Level.WARNING, "Presence maintenance failed", e);
        }
    }

    private synchronized void publishChanges() {
        for (PresenceUpdate update : sessions.drainChanges()) {
            int sequence = presenceSequence.updateAndGet(n -> n == -1 ? 1 : n + 1);
            for (SessionRegistry.Peer peer : sessions.onlinePeers()) {
                if (peer.presenceEndpoint() == null || peer.username().equals(update.username())) continue;
                try {
                    UdpPacketIO.sendPacket(udp, peer.presenceEndpoint(), ControlPackets.create(
                            MessageType.PRESENCE_UPDATE, sequence, 0, peer.userID(), update));
                } catch (IOException e) {
                    LOG.fine("Presence delivery failed for user " + peer.userID());
                }
            }
        }
    }

    private static void validateHeader(Packet request) throws AccountException {
        PacketHeader header = request.getHeader();
        if (header.getFlags() != 0 || header.getStreamID() != 0
                || header.getSequenceNumber() == 0 || header.getReceiverID() != 0) {
            throw invalid("INVALID_CONTROL_HEADER");
        }
    }

    private static Packet reply(Packet request, String type, int receiver, Object value) throws IOException {
        return ControlPackets.create(type, request.getHeader().getSequenceNumber(), 0, receiver, value);
    }

    private static Packet error(Packet request, int code, String reason) throws IOException {
        return reply(request, MessageType.ERROR, request.getHeader().getSenderID(),
                new ErrorPayload(code, reason, Integer.toUnsignedLong(request.getHeader().getStreamID()),
                        Integer.toUnsignedLong(request.getHeader().getSequenceNumber())));
    }

    private void sendUdpError(UdpPacketIO.ReceivedPacket request, int code, String reason) {
        try { UdpPacketIO.sendPacket(udp, request.source(), error(request.packet(), code, reason)); }
        catch (IOException e) { LOG.fine("UDP error response could not be sent"); }
    }

    private static AccountException invalid(String reason) {
        return new AccountException(ErrorCode.INVALID_PAYLOAD, reason);
    }

    private static void closeQuietly(Socket socket) {
        if (socket != null) try { socket.close(); } catch (IOException ignored) { }
    }

    @Override
    public synchronized void close() {
        running = false;
        try { tcp.close(); } catch (IOException ignored) { }
        udp.close();
        connections.values().forEach(TrackerServer::closeQuietly);
        monitor.shutdownNow();
        loops.shutdownNow();
        workers.shutdownNow();
    }

    public static void main(String[] args) throws Exception {
        String bindIP = args.length > 0 ? args[0] : "0.0.0.0";
        int tcpPort = args.length > 1 ? Integer.parseInt(args[1]) : 5000;
        int udpPort = args.length > 2 ? Integer.parseInt(args[2]) : 5000;
        Path file = Path.of(args.length > 3 ? args[3] : "data/accounts.json");
        TrackerServer server = new TrackerServer(bindIP, tcpPort, udpPort, file);
        Runtime.getRuntime().addShutdownHook(new Thread(server::close));
        server.start();
        System.out.printf("Tracker listening: TCP %d, UDP %d, heartbeat timeout 15s%n", server.tcpPort(), server.udpPort());
        new CountDownLatch(1).await();
    }
}
