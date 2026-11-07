package src.main.java.common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class SignupRequest {
    public final String username;
    public final String password;

    @JsonCreator
    public SignupRequest(
            @JsonProperty(value = "username", required = true)
            String username,
            @JsonProperty(value = "password", required = true)
            String password
    ) {
        if (username == null
                || username.isEmpty()
                || username.length() > 32
                || username.chars().anyMatch(c -> c > 127)) {
            throw new IllegalArgumentException(
                    "Username must contain 1–32 ASCII characters"
            );
        }

        if (password == null || password.isEmpty()) {
            throw new IllegalArgumentException(
                    "Password must not be null or empty"
            );
        }

        this.username = username;
        this.password = password;
    }
}