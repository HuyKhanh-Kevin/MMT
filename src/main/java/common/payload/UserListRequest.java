package common.payload;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
public class UserListRequest {
    public final String sessionID;

    @JsonCreator
    public UserListRequest(@JsonProperty("session_id") String sessionID) {
        this.sessionID = sessionID;
    }

    public String getSessionID() {
        return sessionID;
    }
}
