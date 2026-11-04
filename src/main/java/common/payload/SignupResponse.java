package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class SignupResponse {
    public final boolean status;
    public final String reason;

    @JsonCreator
    public SignupResponse(
            @JsonProperty(value = "status", required = true)
            Boolean status,
            @JsonProperty(value = "reason", required = true)
            String reason
    ) {
        if (status == null) {
            throw new IllegalArgumentException(
                    "Status must not be null"
            );
        }

        if (status && reason != null) {
            throw new IllegalArgumentException(
                    "Reason must be null when signup succeeds"
            );
        }

        if (!status && (reason == null || reason.isBlank())) {
            throw new IllegalArgumentException(
                    "Reason must not be blank when signup fails"
            );
        }

        this.status = status;
        this.reason = reason;
    }
}