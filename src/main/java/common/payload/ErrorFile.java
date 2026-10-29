package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
public class ErrorFile {
    private final int fileID;
    private final int errorCode;
    private final String errorMessage;
    
    @JsonCreator
    public ErrorFile(
        @JsonProperty("fileID") int fileID,
        @JsonProperty("errorCode") int errorCode,
        @JsonProperty("errorMessage") String errorMessage
    ){
        this.fileID = fileID;
        this.errorCode = errorCode;
        this.errorMessage = errorMessage;
    }

    public int getFileID() {
        return fileID;
    }

    public int getErrorCode() {
        return errorCode;
    }

    public String getErrorMessage() {
        return errorMessage;
    }
}
