package common.payload;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
public class ChatMessage {
    private final String text;

    @JsonCreator 
    public ChatMessage(@JsonProperty("text") String text) {
        if (text == null || text.isEmpty()) {
            throw new IllegalArgumentException("Chat message text cannot be null or empty");
        }

        if (text.getBytes(StandardCharsets.UTF_8).length > 1000) {
            throw new IllegalArgumentException("Chat message text cannot exceed 1000 characters");
        }
        this.text = text;
    }

    public String getText() {
        return text;
    }
}
