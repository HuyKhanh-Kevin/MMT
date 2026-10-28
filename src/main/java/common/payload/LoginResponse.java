package common.payload;

public class LoginResponse {
    private final boolean status;
    private final String sessionID;
    private final int userID;
    private final String reason;

    public LoginResponse(boolean status, String sessionID, int userID, String reason) {
        this.status = status;
        this.sessionID = sessionID;
        this.userID = userID;
        this.reason = reason;
    }

    public boolean isStatus() {
        return status;
    }

    public String getSessionID() {
        return sessionID;
    }

    public int getUserID() {
        return userID;
    }

    public String getReason() {
        return reason;
    }
}
