package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class LoginRequest {
    private final String username;
    private final String password;
    private final int tcpPort;
    private final int fileUdpPort;

    @JsonCreator
    public LoginRequest(
            @JsonProperty("username") String username,
            @JsonProperty("password") String password,
            @JsonProperty("tcp_port") int tcpPort,
            @JsonProperty("file_udp_port") int fileUdpPort) {
        
        if (username == null || !username.matches("[\\x00-\\x7F]{1,32}")) {
            throw new IllegalArgumentException(
                    "Username must contain 1-32 ASCII characters");
        }

        if (password == null || password.isEmpty()) {
            throw new IllegalArgumentException(
                    "Password cannot be null or empty");
        }

        if (tcpPort < 1 || tcpPort > 65535 || fileUdpPort < 1 || fileUdpPort > 65535) {
            throw new IllegalArgumentException(
                    "Port numbers must be between 1 and 65535");
        }
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