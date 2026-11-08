package src.main.java.common.payload;

import common.ProtocolConstants;

public final class FileChunk {
    private final int fileID;
    private final int chunkOrder;
    private final byte[] payloadData;

    public FileChunk(int fileID, int chunkOrder, byte[] payloadData) {
        if (payloadData == null) {
            throw new IllegalArgumentException(
                    "Chunk data must not be null");
        }

        if (payloadData.length >
                ProtocolConstants.MAX_CHUNK_DATA_SIZE) {
            throw new IllegalArgumentException(
                    "Chunk data exceeds the maximum size");
        }

        if (chunkOrder < 0) {
            throw new IllegalArgumentException(
                    "Chunk order must be non-negative");
        }

        this.fileID = fileID;
        this.chunkOrder = chunkOrder;
        this.payloadData = payloadData.clone();
    }

    public int getFileID() {
        return fileID;
    }

    public int getChunkOrder() {
        return chunkOrder;
    }

    public int getPayloadLength() {
        return payloadData.length;
    }

    public byte[] getPayloadData() {
        return payloadData.clone();
    }
}