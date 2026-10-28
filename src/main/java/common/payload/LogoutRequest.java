package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
public class LogoutRequest {
    private final String sessionID;

    @JsonCreator 
    public LogoutRequest(@JsonProperty("sessionID") String sessionID) {
        this.sessionID = sessionID;
    }

    public String getSessionID() {
        return sessionID;
    }
}
