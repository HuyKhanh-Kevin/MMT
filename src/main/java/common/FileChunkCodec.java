package common;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;

import common.payload.FileChunk;

public class FileChunkCodec {
    private FileChunkCodec() {}

    public static byte[] encode(FileChunk chunk) {
        if (chunk == null) {
            throw new IllegalArgumentException("FileChunk must not be null");
        }

        int fileId = chunk.getFileID();
        int chunkIndex = chunk.getChunkOrder();
        byte[] data = chunk.getPayloadData();

        if (data == null) {
            throw new IllegalArgumentException("Data must not be null");
        }

        ByteBuffer buffer = ByteBuffer.allocate(8 + data.length);
        buffer.order(ByteOrder.BIG_ENDIAN);

        buffer.putInt(fileId);
        buffer.putInt(chunkIndex);
        buffer.put(data);

        return buffer.array();
    }

    public static FileChunk decode(byte[] bytes) {
        if (bytes == null || bytes.length < 8) {
            throw new IllegalArgumentException(
                    "Byte array must not be null and must have at least 8 bytes");
        }

        ByteBuffer buffer = ByteBuffer.wrap(bytes);
        buffer.order(ByteOrder.BIG_ENDIAN);

        int fileId = buffer.getInt();
        int chunkIndex = buffer.getInt();
        byte[] data = new byte[buffer.remaining()];
        buffer.get(data);

        return new FileChunk(fileId, chunkIndex, data);
    }
}
