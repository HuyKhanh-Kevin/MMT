package common;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.json.JsonMapper;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class JsonPayloadCodec {
    private JsonPayloadCodec() {}

    private static final JsonMapper MAPPER = JsonMapper.builder()
            // tcpPort -> tcp_port; fileUdpPort -> file_udp_port.
            .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)

            // Không chấp nhận field trùng tên.
            .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)

            // Không chấp nhận dữ liệu nằm sau JSON đầu tiên.
            .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)

            // Kiểm tra các field khi tạo đối tượng.
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
            .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
            .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)

            // Không tự đổi 5001.5 hoặc "5001" thành số nguyên.
            .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
            .disable(MapperFeature.ALLOW_COERCION_OF_SCALARS)
            .build();

    public static byte[] encode(Object value) throws IOException {
        if (value == null) {
            throw new IllegalArgumentException("Payload must not be null");
        }

        JsonNode json = MAPPER.valueToTree(value);

        if (!json.isObject()) {
            throw new IOException("JSON payload must be an object");
        }

        // Jackson xuất JSON thành UTF-8 bytes.
        byte[] payload = MAPPER.writeValueAsBytes(json);

        checkSize(payload);
        return payload;
    }

    public static <T> T decode(byte[] payload, Class<T> type)
            throws IOException {

        if (payload == null || type == null) {
            throw new IllegalArgumentException(
                    "Payload and target type must not be null");
        }

        checkSize(payload);

        // Từ chối UTF-8 không hợp lệ thay vì tự thay ký tự lỗi.
        String text = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(payload))
                .toString();

        JsonNode json = MAPPER.readTree(text);

        if (json == null || !json.isObject()) {
            throw new IOException("JSON payload must be an object");
        }

        if (type == common.payload.LoginResponse.class) {
            return MAPPER.readerFor(type)
                    .without(
                        DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
                    .readValue(json.traverse(MAPPER));
        }

        return MAPPER.treeToValue(json, type);
    }

    private static void checkSize(byte[] payload) throws IOException {
        if (payload.length == 0
                || payload.length >
                ProtocolConstants.MAX_JSON_PAYLOAD_SIZE) {
            throw new IOException("Invalid JSON payload size");
        }
    }
}