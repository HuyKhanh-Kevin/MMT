package src/main/java/common/payload;

public class LoginRequest {
    private final String username;
    private final String password;
    private final int tcpPort;
    private final int fileUdpPort;

    public LoginRequest(String username, String password,
                        int tcpPort, int fileUdpPort) {
        this.username = username;
        this.password = password;
        this.tcpPort = tcpPort;
        this.fileUdpPort = fileUdpPort;
    }

    public String getUsername() {
        return username;
    }

    public String getPassword() {
        return password;
    }

    public int getTcpPort() {
        return tcpPort;
    }

    public int getFileUdpPort() {
        return fileUdpPort;
    }
}