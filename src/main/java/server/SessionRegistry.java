package server;

import common.ErrorCode;
import common.payload.PresenceUpdate;
import common.payload.UserInfo;

import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.function.LongSupplier;

/** All multi-map changes happen under one lock, including concurrent login/logout/expiry. */
public final class SessionRegistry {
    public static final Duration DEFAULT_TIMEOUT = Duration.ofSeconds(15);
    private final long timeoutNanos;
    private final LongSupplier nanoTime;
    private final SecureRandom random = new SecureRandom();
    private final Map<String, Session> sessions = new HashMap<>();
    private final Map<Integer, Session> byUser = new HashMap<>();
    private final Map<UUID, Session> byConnection = new HashMap<>();
    private final Queue<PresenceUpdate> changes = new ArrayDeque<>();
    private final Queue<UUID> disconnected = new ArrayDeque<>();

    public record Peer(int userID, String username, String ip, int tcpPort, int fileUdpPort,
                       Instant lastSeen, InetSocketAddress presenceEndpoint) {
        public UserInfo userInfo() {
            return new UserInfo(username, "online", Integer.toUnsignedLong(userID), ip, tcpPort, fileUdpPort);
        }
    }
    public record CreatedSession(String sessionID, Peer peer) {}

    private static final class Session {
        final String token;
        final AccountStore.Account account;
        final InetAddress address;
        final int tcpPort;
        final int fileUdpPort;
        final UUID connection;
        long lastHeartbeat;
        long heartbeatSeq;
        Instant lastSeen = Instant.now();
        InetSocketAddress presenceEndpoint;

        Session(String token, AccountStore.Account account, InetAddress address,
                int tcpPort, int fileUdpPort, UUID connection, long now) {
            this.token = token;
            this.account = account;
            this.address = address;
            this.tcpPort = tcpPort;
            this.fileUdpPort = fileUdpPort;
            this.connection = connection;
            this.lastHeartbeat = now;
        }

        Peer peer() {
            return new Peer(account.userID(), account.username(), address.getHostAddress(),
                    tcpPort, fileUdpPort, lastSeen, presenceEndpoint);
        }
    }

    public SessionRegistry() { this(DEFAULT_TIMEOUT, System::nanoTime); }

    public SessionRegistry(Duration timeout, LongSupplier nanoTime) {
        if (timeout.isNegative() || timeout.isZero()) throw new IllegalArgumentException("Invalid timeout");
        this.timeoutNanos = timeout.toNanos();
        this.nanoTime = Objects.requireNonNull(nanoTime);
    }

    public synchronized CreatedSession login(AccountStore.Account account, InetAddress address,
                                              int tcpPort, int fileUdpPort, UUID connection)
            throws AccountException {
        checkPort(tcpPort);
        checkPort(fileUdpPort);
        Session previous = byConnection.get(connection);
        boolean expiredConnection = previous != null && expired(previous);
        expire();
        if (expiredConnection) throw invalid("SESSION_EXPIRED_RECONNECT");
        if (byConnection.containsKey(connection)) throw invalid("ALREADY_AUTHENTICATED");
        if (byUser.containsKey(account.userID())) {
            throw new AccountException(ErrorCode.USERNAME_TAKEN, "ALREADY_ONLINE");
        }
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        Session session = new Session(token, account, address, tcpPort, fileUdpPort, connection, nanoTime.getAsLong());
        sessions.put(token, session);
        byUser.put(account.userID(), session);
        byConnection.put(connection, session);
        changes.add(new PresenceUpdate(account.username(), "online"));
        return new CreatedSession(token, session.peer());
    }

    public synchronized boolean hasSession(UUID connection) {
        Session session = byConnection.get(connection);
        return session != null && !expired(session);
    }

    public synchronized Peer authenticateUdp(String token, int senderID, InetSocketAddress source)
            throws AccountException {
        return udpSession(token, senderID, source).peer();
    }

    public synchronized void heartbeat(String token, int senderID, long sequence, InetSocketAddress source)
            throws AccountException {
        Session session = udpSession(token, senderID, source);
        if (sequence < 1 || sequence > 0xFFFF_FFFFL) throw invalid("INVALID_HEARTBEAT_SEQUENCE");
        // Lost/reordered/replayed heartbeat packets must not extend session lifetime.
        if (sequence <= session.heartbeatSeq) return;
        session.presenceEndpoint = source;
        session.heartbeatSeq = sequence;
        session.lastHeartbeat = nanoTime.getAsLong();
        session.lastSeen = Instant.now();
    }

    public synchronized void logout(String token, int senderID, UUID connection) throws AccountException {
        Session session = require(token, senderID);
        if (!session.connection.equals(connection)) throw unauthenticated();
        remove(session, false);
    }

    public synchronized void disconnect(UUID connection) {
        Session session = byConnection.get(connection);
        if (session != null) remove(session, false);
    }

    public synchronized void expire() {
        for (Session session : List.copyOf(sessions.values())) {
            if (expired(session)) remove(session, true);
        }
    }

    public synchronized List<Peer> onlinePeers() {
        return sessions.values().stream().filter(s -> !expired(s)).map(Session::peer)
                .sorted(Comparator.comparingInt(Peer::userID)).toList();
    }

    /** Routing/file-transfer owners can resolve the registered peer endpoint here. */
    public synchronized Optional<Peer> findOnlineUser(int userID) {
        Session session = byUser.get(userID);
        return session == null || expired(session) ? Optional.empty() : Optional.of(session.peer());
    }

    public synchronized List<PresenceUpdate> drainChanges() {
        List<PresenceUpdate> result = new ArrayList<>(changes);
        changes.clear();
        return result;
    }

    public synchronized List<UUID> drainDisconnectedConnections() {
        List<UUID> result = new ArrayList<>(disconnected);
        disconnected.clear();
        return result;
    }

    private Session udpSession(String token, int senderID, InetSocketAddress source) throws AccountException {
        Session session = require(token, senderID);
        if (!session.address.equals(source.getAddress())
                || (session.presenceEndpoint != null && !session.presenceEndpoint.equals(source))) {
            throw unauthenticated();
        }
        return session;
    }

    private Session require(String token, int senderID) throws AccountException {
        Session session = sessions.get(token);
        if (session == null || session.account.userID() != senderID || expired(session)) throw unauthenticated();
        return session;
    }

    private boolean expired(Session session) {
        return nanoTime.getAsLong() - session.lastHeartbeat >= timeoutNanos;
    }

    private void remove(Session session, boolean closeControl) {
        sessions.remove(session.token);
        byUser.remove(session.account.userID(), session);
        byConnection.remove(session.connection, session);
        changes.add(new PresenceUpdate(session.account.username(), "offline"));
        if (closeControl) disconnected.add(session.connection);
    }

    private static void checkPort(int port) throws AccountException {
        if (port < 1 || port > 65535) throw invalid("INVALID_PORT");
    }
    private static AccountException invalid(String reason) {
        return new AccountException(ErrorCode.INVALID_PAYLOAD, reason);
    }
    private static AccountException unauthenticated() {
        return new AccountException(ErrorCode.UNAUTHENTICATED, "UNAUTHENTICATED");
    }
}
