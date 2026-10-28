package common.payload;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class ReqResend {
    private final int fileID;
    private final boolean resendAll;
    private final List<Integer> missingChunks;

    @JsonCreator 
    public ReqResend(
        @JsonProperty("fileID") int fileID, 
        @JsonProperty("resendAll") boolean resendAll,
        @JsonProperty("missingChunks") List<Integer> missingChunks
    ){
        this.fileID = fileID;
        this.resendAll = resendAll;
        this.missingChunks = missingChunks;
    }

    public int getFileID() {
        return fileID;
    }

    public boolean isResendAll() {
        return resendAll;
    }

    public List<Integer> getMissingChunks() {
        return missingChunks;
    }
}
