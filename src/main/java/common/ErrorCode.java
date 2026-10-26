package src.main.java.common;

public final class ErrorCode {
    private ErrorCode() {
        // Không cần tạo đối tượng từ class chứa hằng số.
    }

    public static final int SUCCESS = 0;

    public static final int INVALID_CREDENTIALS = 1001;
    public static final int USERNAME_TAKEN = 1002;
    public static final int INVALID_PAYLOAD = 1003;
    public static final int UNAUTHENTICATED = 1004;

    public static final int RECIPIENT_OFFLINE = 2001;

    public static final int FILE_TOO_LARGE = 3001;
    public static final int FILE_HASH_MISMATCH = 3002;
    public static final int TRANSFER_TIMEOUT = 3003;
    public static final int FILE_WRITE_FAILED = 3004;

    public static final int DECRYPTION_FAILED = 4001;
    public static final int WINDOW_EXCEEDED = 4002;
    public static final int RATE_LIMIT_EXCEEDED = 4003;
}