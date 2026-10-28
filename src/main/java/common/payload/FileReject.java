package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
public class FileReject {
    private final int fileID;
    private final String reason;

    @JsonCreator
    public FileReject(
        @JsonProperty("fileID") int fileID, 
        @JsonProperty("reason") String reason
    ){
        this.fileID = fileID;
        this.reason = reason;
    }

    public int getFileID() {
        return fileID;
    }

    public String getReason() {
        return reason;
    }
}
