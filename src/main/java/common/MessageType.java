package src.main.java.common;

public class MessageType {
    private MessageType() {
        // Không cần tạo đối tượng từ class chứa hằng số.
    }

    public static final int LOGIN_REQUEST = 0x01;
    public static final int LOGIN_RESPONSE = 0x02;
    public static final int CHAT_MESSAGE = 0x03;
    public static final int ACK = 0x04;
    public static final int HEARTBEAT = 0x05;
    public static final int USER_LIST_RESPONSE = 0x06;
    public static final int FILE_REQ = 0x07;
    public static final int FILE_CHUNK = 0x08;
    public static final int ERROR = 0x0A;
    public static final int FILE_DONE = 0x0B;
    public static final int SIGNUP_REQUEST = 0x0C;
    public static final int SIGNUP_RESPONSE = 0x0D;
    public static final int FILE_ACCEPT = 0x0E;
    public static final int FILE_REJECT = 0x0F;
    public static final int REQ_RESEND = 0x10;
    public static final int ERROR_FILE = 0x11;
    public static final int USER_LIST_REQUEST = 0x12;
    public static final int PRESENCE_UPDATE = 0x13;
    public static final int LOGOUT_REQUEST = 0x14;
    public static final int LOGOUT_RESPONSE = 0x15;

    public static boolean isValid(int type) {
        return switch (type) {
            case 0x01, // LOGIN_REQUEST
                0x02, // LOGIN_RESPONSE
                0x03, // CHAT_MESSAGE
                0x04, // ACK
                0x05, // HEARTBEAT
                0x06, // USER_LIST_RESPONSE
                0x07, // FILE_REQ
                0x08, // FILE_CHUNK
                0x0A, // ERROR
                0x0B, // FILE_DONE
                0x0C, // SIGNUP_REQUEST
                0x0D, // SIGNUP_RESPONSE
                0x0E, // FILE_ACCEPT
                0x0F, // FILE_REJECT
                0x10, // REQ_RESEND
                0x11, // ERROR_FILE
                0x12, // USER_LIST_REQUEST
                0x13, // PRESENCE_UPDATE
                0x14, // LOGOUT_REQUEST
                0x15  // LOGOUT_RESPONSE
                    -> true;

            default -> false;
        };
    }
}