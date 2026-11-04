package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
public class ErrorPayload {
    private final int errorCode;
    private final String errorMessage;


    @JsonCreator 
    public ErrorPayload(@JsonProperty("errorCode") int errorCode, @JsonProperty("errorMessage") String errorMessage) {
        this.errorCode = errorCode;
        this.errorMessage = errorMessage;
    }

    public int getErrorCode() {
        return errorCode;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

}