package server;

public final class AccountException extends Exception {
    private final int code;

    public AccountException(int code, String reason) {
        super(reason);
        this.code = code;
    }

    public int code() { return code; }
}
