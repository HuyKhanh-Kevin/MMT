package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public final class UserListRequest {
    private final String sessionID;
    @JsonProperty("cursor") private String cursor;

    @JsonCreator
    public UserListRequest(@JsonProperty("session_id") String sessionID) { this.sessionID = sessionID; }

    public UserListRequest(String sessionID, String cursor) {
        this(sessionID);
        this.cursor = cursor;
    }

    @JsonProperty("session_id") public String getSessionID() { return sessionID; }
    public String getCursor() { return cursor; }
}
