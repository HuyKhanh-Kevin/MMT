package common.payload;

import com.fasterxml.jackson.annotation.JsonProperty;

public record UserInfo(
        @JsonProperty("username") String username,
        @JsonProperty("status") String status,
        @JsonProperty("user_id") long userID
) {
    public UserInfo {
        if (username == null
                || !username.matches("[\\x00-\\x7F]{1,32}")) {
            throw new IllegalArgumentException(
                    "Username must contain 1-32 ASCII characters");
        }

        if (!"online".equals(status)) {
            throw new IllegalArgumentException(
                    "Status must be online");
        }

        if (userID < 1 || userID > 0xFFFF_FFFFL) {
            throw new IllegalArgumentException(
                    "User ID must be between 1 and 4294967295");
        }
    }
}