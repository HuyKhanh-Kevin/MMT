package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
public class FileDone {
    private final int fileID;

    @JsonCreator
    public FileDone(@JsonProperty("fileID") int fileID) {
        this.fileID = fileID;
    }

    public int getFileID() {
        return fileID;
    }
}
