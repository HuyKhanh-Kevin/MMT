package common;

import common.payload.*;
import org.junit.jupiter.api.Test;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class JsonPayloadCodecTest {
    private static byte[] utf8(String s) { return s.getBytes(StandardCharsets.UTF_8); }
    private static LoginResponse login(String json) throws IOException {
        return JsonPayloadCodec.decode(utf8(json), LoginResponse.class);
    }

    @Test void loginSuccessRoundTripWithNullReason() throws IOException {
        LoginResponse r = JsonPayloadCodec.decode(JsonPayloadCodec.encode(
                new LoginResponse(true, "session-test", 4294967295L, null)), LoginResponse.class);
        assertAll(() -> assertTrue(r.isStatus()),
                () -> assertEquals("session-test", r.getSessionID()),
                () -> assertEquals(Long.valueOf(4294967295L), r.getUserID()),
                () -> assertNull(r.getReason()));
    }

    @Test void loginFailureRoundTripWithNullSessionAndUserId() throws IOException {
        LoginResponse r = JsonPayloadCodec.decode(JsonPayloadCodec.encode(
                new LoginResponse(false, null, null, "Invalid credentials")), LoginResponse.class);
        assertAll(() -> assertFalse(r.isStatus()), () -> assertNull(r.getSessionID()),
                () -> assertNull(r.getUserID()),
                () -> assertEquals("Invalid credentials", r.getReason()));
    }

    @Test void rejectSuccessWithoutSession() {
        assertThrows(IOException.class, () -> login(
                "{\"status\":true,\"session_id\":null,\"user_id\":1,\"reason\":null}"));
    }

    @Test void rejectSuccessWithoutValidUserId() {
        for (String id : new String[]{"null", "0", "-1", "4294967296"}) {
            assertThrows(IOException.class, () -> login(
                    "{\"status\":true,\"session_id\":\"s\",\"user_id\":" + id + ",\"reason\":null}"));
        }
    }

    @Test void rejectFailureWithoutReason() {
        for (String reason : new String[]{"null", "\"\"", "\"   \""}) {
            assertThrows(IOException.class, () -> login(
                    "{\"status\":false,\"session_id\":null,\"user_id\":null,\"reason\":" + reason + "}"));
        }
    }

    @Test void rejectMissingOrNullStatus() {
        assertThrows(IOException.class, () -> login(
                "{\"session_id\":null,\"user_id\":null,\"reason\":\"bad\"}"));
        assertThrows(IOException.class, () -> login(
                "{\"status\":null,\"session_id\":null,\"user_id\":null,\"reason\":\"bad\"}"));
    }

    @Test void allFourLoginResponseFieldsMustBePresent() {
        // Current contract: optional values are explicit null, not omitted fields.
        assertThrows(IOException.class, () -> login(
                "{\"status\":true,\"session_id\":\"s\",\"user_id\":1}"));
    }

    @Test void otherPayloadStillRejectsNullSession() {
        assertThrows(IOException.class, () -> JsonPayloadCodec.decode(
                utf8("{\"session_id\":null}"), UserListRequest.class));
    }

    @Test void heartbeatStillRejectsNullSession() {
        // Use the JSON name currently defined by Heartbeat's annotation.
        assertThrows(IOException.class, () -> JsonPayloadCodec.decode(
                utf8("{\"sessionID\":null,\"heartbeatSeq\":1}"), Heartbeat.class));
    }

    @Test void loginRequestRoundTrip() throws IOException {
        LoginRequest r = JsonPayloadCodec.decode(JsonPayloadCodec.encode(
                new LoginRequest("alice", "test-only-password", 5001, 5002)), LoginRequest.class);
        assertAll(() -> assertEquals("alice", r.getUsername()),
                () -> assertEquals("test-only-password", r.getPassword()),
                () -> assertEquals(5001, r.getTcpPort()),
                () -> assertEquals(5002, r.getFileUdpPort()));
    }

    @Test void rejectInvalidUsernamePasswordAndPorts() {
        for (String name : new String[]{null, "", "a".repeat(33), "\u00e1"}) {
            assertThrows(IllegalArgumentException.class,
                    () -> new LoginRequest(name, "pw", 5001, 5002));
        }
        for (String pw : new String[]{null, ""}) {
            assertThrows(IllegalArgumentException.class,
                    () -> new LoginRequest("alice", pw, 5001, 5002));
        }
        for (int port : new int[]{-1, 0, 65536}) {
            assertThrows(IllegalArgumentException.class,
                    () -> new LoginRequest("alice", "pw", port, 5002));
            assertThrows(IllegalArgumentException.class,
                    () -> new LoginRequest("alice", "pw", 5001, port));
        }
        assertDoesNotThrow(() -> new LoginRequest("alice", "pw", 1, 65535));
    }

    @Test void chatMeasuresUtf8Bytes() throws IOException {
        String text = "\u00e1".repeat(500); // 1000 UTF-8 bytes; 500 characters.
        ChatMessage r = JsonPayloadCodec.decode(
                JsonPayloadCodec.encode(new ChatMessage(text)), ChatMessage.class);
        assertEquals(text, r.getText());
        assertThrows(IllegalArgumentException.class, () -> new ChatMessage(text + "\u00e1"));
    }

    @Test void serializedJsonLimitIncludesEscapingAndFieldNames() throws IOException {
        // {"x":"..."} adds 8 bytes, so 1092 ASCII bytes gives exactly 1100.
        byte[] limit = JsonPayloadCodec.encode(Map.of("x", "a".repeat(1092)));
        assertEquals(1100, limit.length);
        assertEquals("a".repeat(1092), JsonPayloadCodec.decode(limit, Map.class).get("x"));
        assertThrows(IOException.class,
                () -> JsonPayloadCodec.encode(Map.of("x", "a".repeat(1093))));
        assertThrows(IOException.class, () -> JsonPayloadCodec.decode(
                utf8("{\"x\":\"" + "a".repeat(1093) + "\"}"), Map.class));
        // Text is only 600 bytes but 600 quotes expand to 1200 escaped bytes.
        ChatMessage quotes = new ChatMessage("\"".repeat(600));
        assertThrows(IOException.class, () -> JsonPayloadCodec.encode(quotes));
    }

    @Test void rejectMalformedDuplicateUnknownAndTrailingJson() {
        for (String json : new String[]{"", "[]", "null", "{", "{\"text\":\"a\",\"text\":\"b\"}",
                "{\"text\":\"hi\",\"extra\":1}", "{\"text\":\"hi\"} {}"}) {
            assertThrows(IOException.class,
                    () -> JsonPayloadCodec.decode(utf8(json), ChatMessage.class), json);
        }
    }

    @Test void rejectMalformedUtf8AndCoercedNumbers() {
        assertThrows(IOException.class,
                () -> JsonPayloadCodec.decode(new byte[]{(byte) 0xc3, 0x28}, ChatMessage.class));
        for (String port : new String[]{"\"5001\"", "5001.5", "null"}) {
            assertThrows(IOException.class, () -> JsonPayloadCodec.decode(utf8(
                    "{\"username\":\"alice\",\"password\":\"pw\",\"tcp_port\":"
                            + port + ",\"file_udp_port\":5002}"), LoginRequest.class));
        }
    }
}
