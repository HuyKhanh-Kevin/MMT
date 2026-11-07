package server;

import common.ErrorCode;
import org.junit.jupiter.api.Test;

import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;

class SessionRegistryTest {
    private final AtomicLong now = new AtomicLong();
    private final SessionRegistry registry = new SessionRegistry(Duration.ofSeconds(15), now::get);
    private final AccountStore.Account alice = new AccountStore.Account(1, "alice");
    private final InetAddress ip = InetAddress.getLoopbackAddress();
    private final InetSocketAddress udp = new InetSocketAddress(ip, 7000);

    @Test void recordsEndpointsAndIssuesANewTokenAfterLogout() throws Exception {
        UUID connection = UUID.randomUUID();
        var first = registry.login(alice, ip, 5001, 6001, connection);
        assertEquals(5001, first.peer().tcpPort());
        assertEquals(6001, first.peer().fileUdpPort());
        assertEquals(ip.getHostAddress(), first.peer().ip());
        assertTrue(first.sessionID().length() <= 64);
        assertThrows(AccountException.class, () -> registry.login(alice, ip, 5002, 6002, UUID.randomUUID()));
        registry.logout(first.sessionID(), 1, connection);
        assertTrue(registry.onlinePeers().isEmpty());
        var second = registry.login(alice, ip, 5002, 6002, connection);
        assertNotEquals(first.sessionID(), second.sessionID());
        assertEquals(first.peer().userID(), second.peer().userID());
        assertThrows(AccountException.class, () -> registry.heartbeat(first.sessionID(), 1, 1, udp));
    }

    @Test void heartbeatExtendsDeadlineButReplaysAndListsDoNot() throws Exception {
        var session = registry.login(alice, ip, 5001, 6001, UUID.randomUUID());
        now.set(Duration.ofSeconds(10).toNanos());
        registry.heartbeat(session.sessionID(), 1, 1, udp);
        now.set(Duration.ofSeconds(20).toNanos());
        registry.authenticateUdp(session.sessionID(), 1, udp);
        registry.heartbeat(session.sessionID(), 1, 1, udp);
        registry.expire();
        assertEquals(1, registry.onlinePeers().size());
        now.set(Duration.ofSeconds(25).toNanos());
        assertEquals(ErrorCode.UNAUTHENTICATED, assertThrows(AccountException.class,
                () -> registry.heartbeat(session.sessionID(), 1, 2, udp)).code());
        registry.expire();
        assertTrue(registry.onlinePeers().isEmpty());
        assertEquals(1, registry.drainDisconnectedConnections().size());
        assertEquals("offline", registry.drainChanges().get(1).status());
    }

    @Test void rejectsForgedUserIpUdpPortAndControlConnection() throws Exception {
        UUID connection = UUID.randomUUID();
        var session = registry.login(alice, ip, 5001, 6001, connection);
        registry.heartbeat(session.sessionID(), 1, 1, udp);
        assertThrows(AccountException.class, () -> registry.heartbeat(session.sessionID(), 2, 2, udp));
        assertThrows(AccountException.class, () -> registry.heartbeat(session.sessionID(), 1, 2,
                new InetSocketAddress(InetAddress.getByName("192.0.2.1"), 7000)));
        assertThrows(AccountException.class, () -> registry.heartbeat(session.sessionID(), 1, 2,
                new InetSocketAddress(ip, 7001)));
        assertThrows(AccountException.class, () -> registry.logout(session.sessionID(), 1, UUID.randomUUID()));
        assertThrows(AccountException.class, () -> registry.heartbeat(session.sessionID(), 1, 0, udp));
        assertThrows(AccountException.class, () -> registry.heartbeat(session.sessionID(), 1, 0x1_0000_0000L, udp));
        assertEquals(1, registry.onlinePeers().size());
    }

    @Test void disconnectAndTimeoutEmitOnlyOneOfflineEvent() throws Exception {
        UUID connection = UUID.randomUUID();
        registry.login(alice, ip, 5001, 6001, connection);
        registry.drainChanges();
        registry.disconnect(connection);
        registry.disconnect(connection);
        now.set(Duration.ofSeconds(30).toNanos());
        registry.expire();
        assertEquals(1, registry.drainChanges().size());
    }

    @Test void simultaneousLoginHasOneWinner() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        Callable<Boolean> attempt = () -> {
            start.await();
            try { registry.login(alice, ip, 5001, 6001, UUID.randomUUID()); return true; }
            catch (AccountException e) { return false; }
        };
        try {
            Future<Boolean> a = pool.submit(attempt);
            Future<Boolean> b = pool.submit(attempt);
            start.countDown();
            assertNotEquals(a.get(3, TimeUnit.SECONDS), b.get(3, TimeUnit.SECONDS));
            assertEquals(1, registry.onlinePeers().size());
        } finally { pool.shutdownNow(); }
    }

    @Test void tcpSessionGuardRejectsWrongTokenUserConnectionAndExpiredSession() throws Exception {
        UUID connection = UUID.randomUUID();
        var session = registry.login(alice, ip, 5001, 6001, connection);
        assertEquals(1, registry.authenticateTcp(session.sessionID(), 1, connection).userID());
        assertThrows(AccountException.class, () -> registry.authenticateTcp("wrong", 1, connection));
        assertThrows(AccountException.class, () -> registry.authenticateTcp(session.sessionID(), 2, connection));
        assertThrows(AccountException.class, () -> registry.authenticateTcp(session.sessionID(), 1, UUID.randomUUID()));
        now.set(Duration.ofSeconds(15).toNanos());
        assertThrows(AccountException.class, () -> registry.authenticateTcp(session.sessionID(), 1, connection));
    }

    @Test void expiredConnectionCannotReloginWhileItsSocketIsWaitingToClose() throws Exception {
        UUID connection = UUID.randomUUID();
        registry.login(alice, ip, 5001, 6001, connection);
        now.set(Duration.ofSeconds(15).toNanos());
        registry.expire();
        registry.drainDisconnectedConnections();
        assertEquals("SESSION_EXPIRED_RECONNECT", assertThrows(AccountException.class,
                () -> registry.login(alice, ip, 5001, 6001, connection)).getMessage());
        var newLogin = registry.login(alice, ip, 5002, 6002, UUID.randomUUID());
        registry.disconnect(connection); // Old connection cleanup cannot delete the new session.
        assertEquals(newLogin.peer(), registry.findOnlineUser(1).orElseThrow());
    }

    @Test void reloginReplacesIpAndBothPortsAndResetsUdpBinding() throws Exception {
        UUID oldConnection = UUID.randomUUID();
        var first = registry.login(alice, ip, 5001, 6001, oldConnection);
        registry.heartbeat(first.sessionID(), 1, 100, udp);
        registry.logout(first.sessionID(), 1, oldConnection);
        InetAddress newIP = InetAddress.getByName("192.0.2.2");
        UUID newConnection = UUID.randomUUID();
        var second = registry.login(alice, newIP, 5010, 6010, newConnection);
        var newUDP = new InetSocketAddress(newIP, 7010);
        registry.heartbeat(second.sessionID(), 1, 1, newUDP);
        var peer = registry.findOnlineUser(1).orElseThrow();
        assertEquals("192.0.2.2", peer.ip());
        assertEquals(5010, peer.tcpPort());
        assertEquals(6010, peer.fileUdpPort());
        assertEquals(newUDP, peer.presenceEndpoint());
        assertThrows(AccountException.class, () -> registry.discover(first.sessionID(), 1, udp));
        assertThrows(AccountException.class, () -> registry.discover(second.sessionID(), 1, udp));
    }
}
