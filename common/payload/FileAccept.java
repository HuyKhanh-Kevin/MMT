package src.main.java.common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
public class FileAccept {
    private final int fileID;

    @JsonCreator
    public FileAccept(
        @JsonProperty("file_id") int fileID
    ){
        this.fileID = fileID;
    }

    public int getFileID() {
        return fileID;
    }
}
