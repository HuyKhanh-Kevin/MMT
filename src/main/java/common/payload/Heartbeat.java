package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
public class Heartbeat {
    private final String sessionID;
    private final long heartbeatSeq;

    @JsonCreator
    public Heartbeat(
        @JsonProperty("session_id") String sessionID,
        @JsonProperty("heartbeat_seq") long heartbeatSeq
    ) {
        this.sessionID = sessionID;
        this.heartbeatSeq = heartbeatSeq;
    }

    @JsonProperty("session_id")
    public String getSessionID() {
        return sessionID;
    }

    public long getHeartbeatSeq() {
        return heartbeatSeq;
    }

}
