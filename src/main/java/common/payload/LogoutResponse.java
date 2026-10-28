package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
public class LogoutResponse {
    private final String status;

    @JsonCreator
    public LogoutResponse(
        @JsonProperty("status") String status
    ){
        this.status = status;
    }

    public String getStatus() {
        return status;
    }
}
