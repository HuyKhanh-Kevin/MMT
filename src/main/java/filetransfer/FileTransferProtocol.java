package src.main.java.filetransfer;

public final class FileTransferProtocol {
    private FileTransferProtocol() {}

    // Message types
    public static final int TYPE_FILE_REQ    = 0x07;
    public static final int TYPE_FILE_CHUNK  = 0x08;
    public static final int TYPE_FILE_DONE   = 0x0B;
    public static final int TYPE_FILE_ACCEPT = 0x0E;
    public static final int TYPE_FILE_REJECT = 0x0F;
    public static final int TYPE_REQ_RESEND  = 0x10;
    public static final int TYPE_ERROR_FILE  = 0x11;

    // Flags
    public static final int FLAG_ACK_NOT_REQUIRED = 0x0000;
    public static final int FLAG_ACK_REQUIRED = 0x0001;
}
