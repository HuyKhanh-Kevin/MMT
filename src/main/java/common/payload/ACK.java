package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
public class ACK {
    private final int ackStreamID;
    private final  int ackSeqNum;

    @JsonCreator
    public ACK(
        @JsonProperty("ackStreamID") int ackStreamID, 
        @JsonProperty("ackSeqNum") int ackSeqNum
    ){
        this.ackStreamID = ackStreamID;
        this.ackSeqNum = ackSeqNum;
    }

    public int getAckStreamID() {
        return ackStreamID;
    }

    public int getAckSeqNum() {
        return ackSeqNum;
    }
}
