package src.main.java.common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonInclude;


@JsonInclude(JsonInclude.Include.NON_NULL)
public final class LoginResponse {
    private final String status;
    @JsonProperty("session_id") private String sessionID;
    @JsonProperty("user_id") private Integer userID;
    @JsonProperty("reason") private String reason;

    // These fields are conditional; only status is a required creator property.
    @JsonCreator
    public LoginResponse(@JsonProperty("status") String status) { this.status = status; }

    public LoginResponse(boolean success, String sessionID, int userID, String reason) {
        this(success ? "success" : "failed");
        this.sessionID = success ? sessionID : null;
        this.userID = success ? userID : null;
        this.reason = success ? null : reason;
    }

    @JsonProperty("status") public String getStatus() { return status; }
    @JsonIgnore public boolean isStatus() { return "success".equals(status); }
    @JsonProperty("session_id") public String getSessionID() { return sessionID; }
    @JsonProperty("user_id") public Integer getUserID() { return userID; }
    public String getReason() { return reason; }
}
