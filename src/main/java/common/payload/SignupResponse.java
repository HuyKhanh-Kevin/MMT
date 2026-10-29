package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonInclude(JsonInclude.Include.NON_NULL)
public final class SignupResponse {
    private final String status;
    @JsonProperty("reason")
    private String reason;

    @JsonCreator
    public SignupResponse(@JsonProperty("status") String status) { this.status = status; }

    public SignupResponse(String status, String reason) {
        this(status);
        this.reason = reason;
    }

    public String getStatus() { return status; }
    public String getReason() { return reason; }
}
