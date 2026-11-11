package server;

import client.AccountClient;
import common.*;
import common.payload.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.net.*;
import java.nio.file.Path;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;

import static org.junit.jupiter.api.Assertions.*;

@Timeout(40)
class AccountIntegrationTest {
    @TempDir Path temp;

    private TrackerServer start() throws IOException {
        var server = new TrackerServer("127.0.0.1", 0, 0, temp.resolve("accounts.json"));
        server.start();
        return server;
    }

    @Test void wrongSessionsAndWrongSendersAreRejectedOnBothTransports() throws Exception {
        try (var server = start(); var client = new WireClient(server)) {
            var login = client.register("alice");
            client.heartbeat(login, 1);
            assertError(client.udp(MessageType.USER_LIST_REQUEST, login.getUserID(), new UserListRequest("bad", null)), 1004);
            assertError(client.udp(MessageType.HEARTBEAT, login.getUserID(), new Heartbeat("bad", 2)), 1004);
            assertError(client.udp(MessageType.USER_LIST_REQUEST, login.getUserID() + 1,
                    new UserListRequest(login.getSessionID(), null)), 1004);
            assertError(client.tcp(MessageType.LOGOUT_REQUEST, login.getUserID(), new LogoutRequest("bad")), 1004);
            assertError(client.tcp(MessageType.LOGOUT_REQUEST, login.getUserID() + 1,
                    new LogoutRequest(login.getSessionID())), 1004);
            assertEquals(1, server.sessions().onlinePeers().size());
            client.tcp(MessageType.LOGOUT_REQUEST, login.getUserID(), new LogoutRequest(login.getSessionID()));
            assertError(client.udp(MessageType.USER_LIST_REQUEST, login.getUserID(),
                    new UserListRequest(login.getSessionID(), null)), 1004);
            assertError(client.udp(MessageType.HEARTBEAT, login.getUserID(), new Heartbeat(login.getSessionID(), 2)), 1004);
        }
    }

    @Test void invalidPortsDoNotCreateSessionAndValidRetrySucceeds() throws Exception {
        try (var server = start(); var client = new WireClient(server)) {
            client.tcp(MessageType.SIGNUP_REQUEST, 0, new SignupRequest("alice", "password123"));
            for (int[] ports : List.of(new int[]{0, 6000}, new int[]{5000, 65536}, new int[]{-1, 6000})) {
                Packet response = client.tcp(MessageType.LOGIN_REQUEST, 0,
                        new LoginRequest("alice", "password123", ports[0], ports[1]));
                assertEquals("INVALID_PORT", JsonPayloadCodec.decode(response.getPayload(), LoginResponse.class).getReason());
                assertTrue(server.sessions().onlinePeers().isEmpty());
            }
            Packet success = client.tcp(MessageType.LOGIN_REQUEST, 0, new LoginRequest("alice", "password123", 5000, 6000));
            assertTrue(JsonPayloadCodec.decode(success.getPayload(), LoginResponse.class).isStatus());
        }
    }

    @Test void discoversChangedEndpointsAndDeliversAFileChunkToTheAdvertisedUdpPort() throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (var server = start();
             var tcpOld = new ServerSocket(0, 10, loopback); var udpOld = new DatagramSocket(0, loopback);
             var tcpNew = new ServerSocket(0, 10, loopback); var udpNew = new DatagramSocket(0, loopback);
             var alice = new AccountClient("127.0.0.1", server.tcpPort(), server.udpPort(), 5001, 6001);
             var bobOld = new AccountClient("127.0.0.1", server.tcpPort(), server.udpPort(), tcpOld.getLocalPort(), udpOld.getLocalPort());
             var bobNew = new AccountClient("127.0.0.1", server.tcpPort(), server.udpPort(), tcpNew.getLocalPort(), udpNew.getLocalPort())) {
            alice.signup("alice", "password123");
            alice.login("alice", "password123");
            bobOld.signup("bob", "password123");
            int bobID = bobOld.login("bob", "password123").getUserID();
            var oldEndpoint = alice.peerEndpoint(bobID);
            assertEquals(tcpOld.getLocalPort(), oldEndpoint.tcp().getPort());
            assertEquals(udpOld.getLocalPort(), oldEndpoint.fileUDP().getPort());
            bobOld.logout();
            assertFalse(bobOld.isAuthenticated());
            assertTrue(bobOld.isConnected());
            assertThrows(IOException.class, () -> alice.peerEndpoint(bobID));
            assertEquals(bobID, bobNew.login("bob", "password123").getUserID());
            var endpoint = alice.peerEndpoint(bobID);
            assertEquals(loopback, endpoint.tcp().getAddress());
            assertEquals(tcpNew.getLocalPort(), endpoint.tcp().getPort());
            assertEquals(udpNew.getLocalPort(), endpoint.fileUDP().getPort());
            tcpNew.setSoTimeout(3000);
            try (Socket sender = new Socket()) {
                sender.connect(endpoint.tcp(), 3000);
                try (Socket recipient = tcpNew.accept()) {
                    recipient.setSoTimeout(3000);
                    sender.getOutputStream().write(42);
                    assertEquals(42, recipient.getInputStream().read());
                }
            }
            byte[] bytes = new byte[1024];
            new Random(42).nextBytes(bytes);
            byte[] payload = FileChunkCodec.encode(new FileChunk(7, 0, bytes));
            Packet chunk = new Packet(new PacketHeader(2, Integer.decode(MessageType.FILE_CHUNK), 0,
                    7, 1, payload.length, alice.userID(), bobID), payload);
            udpNew.setSoTimeout(3000);
            try (var sender = new DatagramSocket()) {
                UdpPacketIO.sendPacket(sender, endpoint.fileUDP(), chunk);
                Packet received = UdpPacketIO.receivePacket(udpNew).packet();
                assertEquals(bobID, received.getHeader().getReceiverID());
                assertArrayEquals(bytes, FileChunkCodec.decode(received.getPayload()).getPayloadData());
            }
        }
    }

    @Test void presenceCallbackCanRefreshDirectoryWithoutBlockingUdpReception() throws Exception {
        try (var server = start();
             var alice = new AccountClient("127.0.0.1", server.tcpPort(), server.udpPort(), 5001, 6001);
             var bob = new AccountClient("127.0.0.1", server.tcpPort(), server.udpPort(), 5002, 6002)) {
            alice.signup("alice", "password123");
            alice.login("alice", "password123");
            alice.onlineUsers();
            CompletableFuture<List<UserInfo>> refreshed = new CompletableFuture<>();
            alice.onPresence(update -> {
                if (update.username().equals("bob") && update.status().equals("online")) {
                    try { refreshed.complete(alice.onlineUsers()); }
                    catch (IOException e) { refreshed.completeExceptionally(e); }
                }
            });
            bob.signup("bob", "password123");
            bob.login("bob", "password123");
            assertEquals(2, refreshed.get(4, TimeUnit.SECONDS).size());
        }
    }

    @Test void allWirePagesFitPayloadLimitAndOldCursorCannotBypassLogout() throws Exception {
        try (var server = start()) {
            List<WireClient> clients = new ArrayList<>();
            try {
                LoginResponse first = null;
                for (int i = 0; i < 20; i++) {
                    var client = new WireClient(server);
                    clients.add(client);
                    var login = client.register(String.format("user%028d", i));
                    client.heartbeat(login, 1);
                    if (i == 0) first = login;
                }
                var reader = clients.get(0);
                Packet packet = reader.udp(MessageType.USER_LIST_REQUEST, first.getUserID(), new UserListRequest(first.getSessionID(), null));
                UserListResponse page = JsonPayloadCodec.decode(packet.getPayload(), UserListResponse.class);
                String firstCursor = page.getNextCursor();
                assertNotNull(firstCursor);
                Set<Long> ids = new HashSet<>();
                int pages = 0;
                while (true) {
                    assertTrue(packet.getPayload().length <= ProtocolConstants.MAX_JSON_PAYLOAD_SIZE);
                    assertTrue(PacketCodec.encode(packet).length <= ProtocolConstants.MAX_PACKET_SIZE);
                    for (UserInfo user : page.getUsers()) assertTrue(ids.add(user.userID()));
                    pages++;
                    if (page.getNextCursor() == null) break;
                    packet = reader.udp(MessageType.USER_LIST_REQUEST, first.getUserID(), new UserListRequest(first.getSessionID(), page.getNextCursor()));
                    page = JsonPayloadCodec.decode(packet.getPayload(), UserListResponse.class);
                }
                assertTrue(pages > 1);
                assertEquals(20, ids.size());
                reader.tcp(MessageType.LOGOUT_REQUEST, first.getUserID(), new LogoutRequest(first.getSessionID()));
                assertError(reader.udp(MessageType.USER_LIST_REQUEST, first.getUserID(), new UserListRequest(first.getSessionID(), firstCursor)), 1004);
                assertTrue(server.sessions().findOnlineUser(first.getUserID()).isEmpty());
            } finally { clients.forEach(WireClient::close); }
        }
    }

    private static void assertError(Packet packet, int code) throws IOException {
        assertEquals(Integer.decode(MessageType.ERROR), packet.getHeader().getMessageType());
        assertEquals(code, JsonPayloadCodec.decode(packet.getPayload(), ErrorPayload.class).getErrorCode());
    }

    private static final class WireClient implements AutoCloseable {
        final Socket tcp;
        final DatagramSocket udp;
        final InetSocketAddress serverUDP;
        int sequence;

        WireClient(TrackerServer server) throws IOException {
            tcp = new Socket("127.0.0.1", server.tcpPort());
            tcp.setSoTimeout(3000);
            udp = new DatagramSocket();
            udp.setSoTimeout(3000);
            serverUDP = new InetSocketAddress("127.0.0.1", server.udpPort());
        }

        LoginResponse register(String username) throws IOException {
            Packet signup = tcp(MessageType.SIGNUP_REQUEST, 0, new SignupRequest(username, "password123"));
            assertEquals("success", JsonPayloadCodec.decode(signup.getPayload(), SignupResponse.class).getStatus());
            Packet login = tcp(MessageType.LOGIN_REQUEST, 0, new LoginRequest(username, "password123", 5001, 6001));
            var result = JsonPayloadCodec.decode(login.getPayload(), LoginResponse.class);
            assertTrue(result.isStatus());
            return result;
        }

        Packet tcp(String type, int sender, Object payload) throws IOException {
            PacketIO.writePacket(tcp.getOutputStream(), ControlPackets.create(type, ++sequence, sender, 0, payload));
            Packet response = PacketIO.readPacket(tcp.getInputStream());
            assertNotNull(response);
            assertEquals(sequence, response.getHeader().getSequenceNumber());
            return response;
        }

        void heartbeat(LoginResponse login, long counter) throws IOException {
            UdpPacketIO.sendPacket(udp, serverUDP, ControlPackets.create(MessageType.HEARTBEAT, ++sequence,
                    login.getUserID(), 0, new Heartbeat(login.getSessionID(), counter)));
        }

        Packet udp(String type, int sender, Object payload) throws IOException {
            UdpPacketIO.sendPacket(udp, serverUDP, ControlPackets.create(type, ++sequence, sender, 0, payload));
            long deadline = System.nanoTime() + Duration.ofSeconds(3).toNanos();
            while (System.nanoTime() < deadline) {
                Packet packet = UdpPacketIO.receivePacket(udp).packet();
                if (packet.getHeader().getMessageType() == Integer.decode(MessageType.PRESENCE_UPDATE)) continue;
                assertEquals(sequence, packet.getHeader().getSequenceNumber());
                return packet;
            }
            throw new SocketTimeoutException("No matching UDP response");
        }

        public void close() {
            udp.close();
            try { tcp.close(); } catch (IOException ignored) { }
        }
    }
}
