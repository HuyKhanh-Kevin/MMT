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
    private final AccountRequestHandler accountHandler;
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
        AccountStore accounts = new AccountStore(accountFile);
        sessions = new SessionRegistry(timeout, System::nanoTime);
        accountHandler = new AccountRequestHandler(accounts, sessions, directory);
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
                Packet response = accountHandler.handleTcp(connection, socket.getInetAddress(), request);
                socket.setSoTimeout(sessions.hasSession(connection) ? 0 : 15_000);
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
                Packet response = accountHandler.handleUdp(request, received.source());
                if (response != null) UdpPacketIO.sendPacket(udp, received.source(), response);
            } catch (IOException e) {
                if (running) LOG.fine("UDP response could not be sent");
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
