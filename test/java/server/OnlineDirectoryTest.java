package test.java.server;

import common.JsonPayloadCodec;
import common.ProtocolConstants;
import common.payload.*;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.IntStream;

import static org.junit.jupiter.api.Assertions.*;

class OnlineDirectoryTest {
    private final AtomicLong now = new AtomicLong();
    private final OnlineDirectory directory = new OnlineDirectory(now::get);
    private final List<UserInfo> users = IntStream.rangeClosed(1, 20)
            .mapToObj(i -> new UserInfo("user_" + i + "_".repeat(24), "online", i,
                    "192.168.100.100", 65535, 65534)).toList();

    @Test void pagesAllTwentyUsersWithinPayloadCapAndKeepsSnapshotStable() throws Exception {
        var first = directory.page("session", null, users);
        assertNotNull(first.getNextCursor());
        List<UserInfo> result = new ArrayList<>(first.getUsers());
        String cursor = first.getNextCursor();
        int count = 1;
        while (cursor != null) {
            // Even if all users go offline midway, later pages retain the original snapshot.
            var page = directory.page("session", cursor, List.of());
            assertArrayEquals(JsonPayloadCodec.encode(page), JsonPayloadCodec.encode(directory.page("session", cursor, users)));
            assertTrue(JsonPayloadCodec.encode(page).length <= ProtocolConstants.MAX_JSON_PAYLOAD_SIZE);
            result.addAll(page.getUsers());
            cursor = page.getNextCursor();
            count++;
        }
        assertTrue(count > 1);
        assertEquals(users, result);
    }

    @Test void cursorCannotCrossSessionsAndExpiresAfterThirtySeconds() throws Exception {
        String cursor = directory.page("alice", null, users).getNextCursor();
        assertThrows(AccountException.class, () -> directory.page("bob", cursor, users));
        assertThrows(AccountException.class, () -> directory.page("alice", "invalid", users));
        now.set(Duration.ofSeconds(30).toNanos());
        assertThrows(AccountException.class, () -> directory.page("alice", cursor, users));
    }

    @Test void optionalNullCursorAndConditionalResponsesRoundTripThroughStrictCodec() throws Exception {
        UserListResponse empty = directory.page("alice", null, List.of());
        assertEquals("{\"users\":[],\"next_cursor\":null}", new String(JsonPayloadCodec.encode(empty), StandardCharsets.UTF_8));
        assertNull(JsonPayloadCodec.decode(JsonPayloadCodec.encode(empty), UserListResponse.class).getNextCursor());
        var request = new UserListRequest("session", null);
        assertEquals("session", JsonPayloadCodec.decode(JsonPayloadCodec.encode(request), UserListRequest.class).getSessionID());
        var success = new LoginResponse(true, "token", 1, null);
        byte[] encoded = JsonPayloadCodec.encode(success);
        assertEquals("success", JsonPayloadCodec.decode(encoded, LoginResponse.class).getStatus());
        String json = new String(encoded, StandardCharsets.UTF_8);
        assertTrue(json.contains("\"session_id\":\"token\""));
        assertTrue(json.contains("\"user_id\":1"));
        assertFalse(json.contains("reason"));
        assertEquals("failed", JsonPayloadCodec.decode(JsonPayloadCodec.encode(
                new LoginResponse(false, null, 0, "INVALID_CREDENTIALS")), LoginResponse.class).getStatus());
        assertEquals("success", JsonPayloadCodec.decode(JsonPayloadCodec.encode(new SignupResponse("success")), SignupResponse.class).getStatus());
    }
}
