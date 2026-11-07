package src.main.java.common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
public class FileReq {
    private final int fileID;
    private final String fileName;
    private final int fileSize;
    private final int totalChunks;
    private final String checksum;

    @JsonCreator 
    public FileReq(
        @JsonProperty("fileID") int fileID, 
        @JsonProperty("fileName") String fileName, 
        @JsonProperty("fileSize") int fileSize, 
        @JsonProperty("totalChunks") int totalChunks, 
        @JsonProperty("checksum") String checksum
    ){
        this.fileID = fileID;
        this.fileName = fileName;
        this.fileSize = fileSize;
        this.totalChunks = totalChunks;
        this.checksum = checksum;
    }

    public int getFileID() {
        return fileID;
    }
    
    public String getFileName() {
        return fileName;
    }

    public int getFileSize() {
        return fileSize;
    }

    public int getTotalChunks() {
        return totalChunks;
    }

    public String getChecksum() {
        return checksum;
    }
}
