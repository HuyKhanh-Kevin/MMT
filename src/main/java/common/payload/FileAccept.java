package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
public class FileAccept {
    private final int fileID;

    @JsonCreator
    public FileAccept(
        @JsonProperty("fileID") int fileID
    ){
        this.fileID = fileID;
    }

    public int getFileID() {
        return fileID;
    }
}
