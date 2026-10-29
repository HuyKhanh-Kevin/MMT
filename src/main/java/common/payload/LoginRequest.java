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