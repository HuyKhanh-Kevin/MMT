package server;

import client.AccountClient;
import common.*;
import common.payload.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.BooleanSupplier;

import static org.junit.jupiter.api.Assertions.*;

@Timeout(40)
class TrackerServerTest {
    @TempDir Path temp;

    private TrackerServer start(Duration timeout) throws Exception {
        TrackerServer server = new TrackerServer("127.0.0.1", 0, 0, temp.resolve("accounts.json"), timeout);
        server.start();
        return server;
    }

    private AccountClient client(TrackerServer server) throws IOException {
        return new AccountClient("127.0.0.1", server.tcpPort(), server.udpPort(), 5101, 6101);
    }

    @Test void signupLoginDiscoveryPresenceAndLogoutOverRealSockets() throws Exception {
        try (TrackerServer server = start(Duration.ofSeconds(15));
             AccountClient alice = client(server); AccountClient bob = client(server);
             AccountClient duplicate = client(server)) {
            assertEquals("success", alice.signup("alice", "password123").getStatus());
            assertEquals("USERNAME_TAKEN", bob.signup("alice", "password123").getReason());
            assertEquals("INVALID_CREDENTIALS", alice.login("alice", "wrongpass").getReason());
            assertEquals("INVALID_CREDENTIALS", bob.login("missing", "password123").getReason());
            assertTrue(alice.login("alice", "password123").isStatus());
            String oldToken = alice.sessionID();
            BlockingQueue<PresenceUpdate> events = new LinkedBlockingQueue<>();
            alice.onPresence(events::add);
            // A list request follows the first heartbeat on the same UDP socket.
            assertEquals(1, alice.onlineUsers().size());
            assertEquals("ALREADY_ONLINE", duplicate.login("alice", "password123").getReason());
            bob.signup("bob", "password123");
            assertTrue(bob.login("bob", "password123").isStatus());
            assertEquals(new PresenceUpdate("bob", "online"), events.poll(3, TimeUnit.SECONDS));
            List<UserInfo> users = alice.onlineUsers();
            assertEquals(List.of("alice", "bob"), users.stream().map(UserInfo::username).toList());
            assertEquals("127.0.0.1", users.get(0).ip());
            assertEquals(5101, users.get(0).tcpPort());
            assertEquals(6101, users.get(0).fileUdpPort());
            bob.logout();
            assertEquals(new PresenceUpdate("bob", "offline"), events.poll(3, TimeUnit.SECONDS));
            assertEquals(1, alice.onlineUsers().size());
            int userID = alice.userID();
            alice.logout();
            assertTrue(alice.login("alice", "password123").isStatus());
            assertEquals(userID, alice.userID());
            assertNotEquals(oldToken, alice.sessionID());
        }
    }

    @Test void silentTimeoutAndAbruptDisconnectRemoveUserAndNotifyObservers() throws Exception {
        // Exercise the production 5s heartbeat / 15s expiry policy over real sockets.
        try (TrackerServer server = start(Duration.ofSeconds(15));
             AccountClient observer = client(server); AccountClient silent = client(server)) {
            observer.signup("observer", "password123");
            observer.login("observer", "password123");
            BlockingQueue<PresenceUpdate> events = new LinkedBlockingQueue<>();
            observer.onPresence(events::add);
            observer.onlineUsers();
            silent.signup("silent", "password123");
            silent.login("silent", "password123");
            int silentID = silent.userID();
            silent.setHeartbeatsEnabled(false);
            assertEquals(new PresenceUpdate("silent", "online"), events.poll(2, TimeUnit.SECONDS));
            assertEquals(new PresenceUpdate("silent", "offline"), events.poll(18, TimeUnit.SECONDS));
            assertTrue(server.sessions().findOnlineUser(silentID).isEmpty());
            await(() -> !silent.isAuthenticated() && !silent.isConnected());
            assertThrows(IOException.class, silent::onlineUsers);
        }
    }

    @Test void abruptTcpCloseIsDetectedWithoutWaitingForHeartbeatTimeout() throws Exception {
        try (TrackerServer server = start(Duration.ofSeconds(15)); AccountClient observer = client(server)) {
            observer.signup("observer", "password123");
            observer.login("observer", "password123");
            observer.onlineUsers();
            BlockingQueue<PresenceUpdate> events = new LinkedBlockingQueue<>();
            observer.onPresence(events::add);
            AccountClient dropped = client(server);
            try {
                dropped.signup("dropped", "password123");
                dropped.login("dropped", "password123");
                assertEquals(new PresenceUpdate("dropped", "online"), events.poll(3, TimeUnit.SECONDS));
            } finally { dropped.close(); }
            assertEquals(new PresenceUpdate("dropped", "offline"), events.poll(3, TimeUnit.SECONDS));
            assertEquals(1, observer.onlineUsers().size());
        }
    }

    @Test void malformedPayloadsAndDatagramsDoNotKillServer() throws Exception {
        try (TrackerServer server = start(Duration.ofSeconds(15));
             Socket tcp = new Socket("127.0.0.1", server.tcpPort());
             DatagramSocket udp = new DatagramSocket()) {
            tcp.setSoTimeout(3000);
            // Missing creator property, wrong scalar type, duplicate and unknown JSON fields.
            List<String> invalid = List.of(
                    "{\"username\":\"alice\"}",
                    "{\"username\":12,\"password\":\"password123\"}",
                    "{\"username\":\"a\",\"username\":\"b\",\"password\":\"password123\"}",
                    "{\"username\":\"a\",\"password\":\"password123\",\"extra\":true}");
            for (int i = 0; i < invalid.size(); i++) {
                byte[] payload = invalid.get(i).getBytes(StandardCharsets.UTF_8);
                PacketIO.writePacket(tcp.getOutputStream(), new Packet(new PacketHeader(2,
                        Integer.decode(MessageType.SIGNUP_REQUEST), 0, 0, i + 1, payload.length, 0, 0), payload));
                Packet response = PacketIO.readPacket(tcp.getInputStream());
                assertNotNull(response);
                assertEquals(Integer.decode(MessageType.ERROR), response.getHeader().getMessageType(), invalid.get(i));
                assertEquals(ErrorCode.INVALID_PAYLOAD, JsonPayloadCodec.decode(response.getPayload(), ErrorPayload.class).getErrorCode());
            }
            byte[] garbage = new byte[]{1, 2, 3};
            udp.send(new DatagramPacket(garbage, garbage.length, InetAddress.getLoopbackAddress(), server.udpPort()));
            byte[] oversized = new byte[1300];
            udp.send(new DatagramPacket(oversized, oversized.length, InetAddress.getLoopbackAddress(), server.udpPort()));
            udp.setSoTimeout(3000);
            UdpPacketIO.sendPacket(udp, new InetSocketAddress("127.0.0.1", server.udpPort()),
                    ControlPackets.create(MessageType.USER_LIST_REQUEST, 20, 1, 0, new UserListRequest("fake", null)));
            Packet response = UdpPacketIO.receivePacket(udp).packet();
            assertEquals(ErrorCode.UNAUTHENTICATED, JsonPayloadCodec.decode(response.getPayload(), ErrorPayload.class).getErrorCode());
            assertEquals(20, response.getHeader().getSequenceNumber());
            PacketIO.writePacket(tcp.getOutputStream(), ControlPackets.create(MessageType.SIGNUP_REQUEST,
                    30, 0, 0, new SignupRequest("alice", "password123")));
            assertEquals("success", JsonPayloadCodec.decode(PacketIO.readPacket(tcp.getInputStream()).getPayload(), SignupResponse.class).getStatus());
        }
    }

    @Test void forgedLogoutAndUdpSourceCannotInvalidateOrHijackSession() throws Exception {
        try (TrackerServer server = start(Duration.ofSeconds(15)); AccountClient alice = client(server);
             Socket attacker = new Socket("127.0.0.1", server.tcpPort()); DatagramSocket udp = new DatagramSocket()) {
            alice.signup("alice", "password123");
            alice.login("alice", "password123");
            alice.onlineUsers();
            attacker.setSoTimeout(3000);
            PacketIO.writePacket(attacker.getOutputStream(), ControlPackets.create(MessageType.LOGOUT_REQUEST,
                    10, alice.userID(), 0, new LogoutRequest(alice.sessionID())));
            var denied = PacketIO.readPacket(attacker.getInputStream());
            assertEquals(ErrorCode.UNAUTHENTICATED, JsonPayloadCodec.decode(denied.getPayload(), ErrorPayload.class).getErrorCode());
            udp.setSoTimeout(3000);
            UdpPacketIO.sendPacket(udp, new InetSocketAddress("127.0.0.1", server.udpPort()),
                    ControlPackets.create(MessageType.HEARTBEAT, 11, alice.userID(), 0, new Heartbeat(alice.sessionID(), 500)));
            assertEquals(ErrorCode.UNAUTHENTICATED, JsonPayloadCodec.decode(
                    UdpPacketIO.receivePacket(udp).packet().getPayload(), ErrorPayload.class).getErrorCode());
            assertEquals(1, alice.onlineUsers().size());
        }
    }

    @Test void servesTwentyConcurrentClientsWithCompletePaginatedDiscovery() throws Exception {
        try (TrackerServer server = start(Duration.ofSeconds(15))) {
            List<AccountClient> clients = new ArrayList<>();
            ExecutorService pool = Executors.newFixedThreadPool(20);
            try {
                for (int i = 0; i < 20; i++) clients.add(client(server));
                List<Future<?>> tasks = new ArrayList<>();
                for (int i = 0; i < clients.size(); i++) {
                    AccountClient client = clients.get(i);
                    String username = "user_" + i;
                    tasks.add(pool.submit(() -> {
                        try {
                            assertEquals("success", client.signup(username, "password123").getStatus());
                            assertTrue(client.login(username, "password123").isStatus());
                        } catch (IOException e) { throw new RuntimeException(e); }
                    }));
                }
                for (Future<?> task : tasks) task.get(30, TimeUnit.SECONDS);
                assertEquals(20, server.sessions().onlinePeers().size());
                for (AccountClient client : clients) {
                    var users = client.onlineUsers();
                    assertEquals(20, users.size());
                    assertEquals(20, users.stream().map(UserInfo::userID).distinct().count());
                }
            } finally {
                clients.forEach(AccountClient::close);
                pool.shutdownNow();
            }
            await(() -> server.sessions().onlinePeers().isEmpty());
        }
    }

    private static void await(BooleanSupplier condition) throws Exception {
        long deadline = System.nanoTime() + Duration.ofSeconds(3).toNanos();
        while (!condition.getAsBoolean() && System.nanoTime() < deadline) Thread.sleep(20);
        assertTrue(condition.getAsBoolean());
    }
}
