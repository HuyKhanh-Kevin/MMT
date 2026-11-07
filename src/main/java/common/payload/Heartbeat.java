package src.main.java.common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
public class Heartbeat {
    private final String sessionID;
    private final int heartbeatSeq;

    @JsonCreator
    public Heartbeat(
        @JsonProperty("sessionID") String sessionID, 
        @JsonProperty("heartbeatSeq") int heartbeatSeq
    ) {
        this.sessionID = sessionID;
        this.heartbeatSeq = heartbeatSeq;
    }

    public String getSessionID() {
        return sessionID;
    }

    public int getHeartbeatSeq() {
        return heartbeatSeq;
    }

}
