package src.main.java.common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class SignupResponse {
    public final String status;
    public final String reason;

    @JsonCreator
    public SignupResponse(
            @JsonProperty(value = "status", required = true)
            String status,
            @JsonProperty(value = "reason", required = true)
            String reason
    ) {
        if (status == null) {
            throw new IllegalArgumentException(
                    "Status must not be null"
            );
        }

        if (status.equals("success") && reason != null) {
            throw new IllegalArgumentException(
                    "Reason must be null when signup succeeds"
            );
        }

        if (status.equals("failed") && (reason == null || reason.isBlank())) {
            throw new IllegalArgumentException(
                    "Reason must not be blank when signup fails"
            );
        }

        this.status = status;
        this.reason = reason;
    }

    public String getStatus() { return status; }
    public String getReason() { return reason; }
}
