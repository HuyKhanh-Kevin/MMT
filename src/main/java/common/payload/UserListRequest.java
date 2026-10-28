package common.payload;

public class UserListRequest {
    public final String sessionID;

    public UserListRequest(String sessionID) {
        this.sessionID = sessionID;
    }

    public String getSessionID() {
        return sessionID;
    }
}
