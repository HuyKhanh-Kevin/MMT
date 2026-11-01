package src.main.java.common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class LoginResponse {
    private final boolean status;
    private final String sessionID;
    private final Long userID;
    private final String reason;


    @JsonCreator 
    public LoginResponse(
        @JsonProperty("status") boolean status, 
        @JsonProperty("session_id") String sessionID, 
        @JsonProperty("user_id") Long userID, 
        @JsonProperty("reason") String reason
    ){
        if (status) {
            if (sessionID == null || sessionID.isBlank()) {
                throw new IllegalArgumentException("Session ID is required");
            }

            if (userID == null || userID < 1 || userID > 0xFFFF_FFFFL) {
                throw new IllegalArgumentException("Invalid user ID");
            }
        } else {
            if (reason == null || reason.isBlank()) {
                throw new IllegalArgumentException("Failure reason is required");
            }
        }
        if(status == false){
            this.status = status;
            this.sessionID = null;
            this.userID = null;
            this.reason = reason;
        }
        else{
            this.status = status;
            this.sessionID = sessionID;
            this.userID = userID;
            this.reason = null;
        }
    }

    public boolean isStatus() {
        return status;
    }

    public String getSessionID() {
        return sessionID;
    }

    public Long getUserID() {
        return userID;
    }

    public String getReason() {
        return reason;
    }
}
