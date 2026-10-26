package src.main.java.common;


public final class ProtocolConstants {
    private ProtocolConstants() {
        // Không cần tạo đối tượng từ class này.
    }

    public static final int VERSION = 2;

    public static final int HEADER_SIZE = 24;              // Bytes
    public static final int MAX_JSON_PAYLOAD_SIZE = 1100; // Bytes
    public static final int MAX_TEXT_SIZE = 1000;         // UTF-8 bytes

    public static final int MAX_CHUNK_DATA_SIZE = 1024;   // Bytes
    public static final int CHUNK_METADATA_SIZE = 12;     // Bytes

    public static final int MAX_PACKET_SIZE = 1200;       // Bytes
}