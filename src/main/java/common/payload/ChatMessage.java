package common.payload;

public class ChatMessage {
    private final String text;

    public ChatMessage(String text) {
        if (text == null || text.isEmpty()) {
            throw new IllegalArgumentException("Chat message text cannot be null or empty");
        }

        if (text.getBytes().length > 1000) {
            throw new IllegalArgumentException("Chat message text cannot exceed 1000 characters");
        }
        this.text = text;
    }

    public String getText() {
        return text;
    }
}
