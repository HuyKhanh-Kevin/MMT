package common;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;

import common.payload.FileChunk;

public class FileChunkCodec {
    private FileChunkCodec() {
        
    }

    public static byte[] encode(FileChunk chunk) {
        if (chunk == null) {
            throw new IllegalArgumentException("FileChunk must not be null");
        }

        int fileId = chunk.getFileID();
        int chunkIndex = chunk.getChunkOrder();
        byte[] data = chunk.getPayloadData();
        if (fileId < 0) {
            throw new IllegalArgumentException("File ID cannot be negative");
        }

        if (chunkIndex < 0) {
            throw new IllegalArgumentException("Chunk index cannot be negative");
        }

        if (data == null) {
            throw new IllegalArgumentException("Data must not be null");
        }

        ByteBuffer buffer = ByteBuffer.allocate(ProtocolConstants.CHUNK_METADATA_SIZE + data.length);
        buffer.order(ByteOrder.BIG_ENDIAN);

        buffer.putInt(fileId);
        buffer.putInt(chunkIndex);
        buffer.putInt(data.length);
        buffer.put(data);

        return buffer.array();
    }

    public static FileChunk decode(byte[] bytes) {
        if (bytes == null) {
            throw new IllegalArgumentException("Chunk bytes must not be null");
        }

        if (bytes.length < ProtocolConstants.CHUNK_METADATA_SIZE) {
            throw new IllegalArgumentException("Incomplete chunk metadata");
        }

        if (bytes.length > ProtocolConstants.CHUNK_METADATA_SIZE
                + ProtocolConstants.MAX_CHUNK_DATA_SIZE) {
            throw new IllegalArgumentException("Chunk is too large");
        }

        ByteBuffer buffer = ByteBuffer.wrap(bytes);
        buffer.order(ByteOrder.BIG_ENDIAN);

        int fileId = buffer.getInt();
        int chunkIndex = buffer.getInt();  
        int payloadLength = buffer.getInt();

        if (payloadLength < 0
                || payloadLength > ProtocolConstants.MAX_CHUNK_DATA_SIZE
                || payloadLength != buffer.remaining()) {
            throw new IllegalArgumentException("Invalid chunk payload length");
        }

        byte[] data = new byte[payloadLength];
        buffer.get(data);

        return new FileChunk(fileId, chunkIndex, data);
    }
}
