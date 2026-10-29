package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class ErrorPayload {
    private final int errorCode;
    private final String errorMessage;
    private final long relatedStreamID;
    private final long relatedSequenceNumber;

    public ErrorPayload(int errorCode, String errorMessage) {
        this(errorCode, errorMessage, 0, 0);
    }

    @JsonCreator
    public ErrorPayload(@JsonProperty("error_code") int errorCode,
                        @JsonProperty("error_message") String errorMessage,
                        @JsonProperty("related_stream_id") long relatedStreamID,
                        @JsonProperty("related_sequence_number") long relatedSequenceNumber) {
        this.errorCode = errorCode;
        this.errorMessage = errorMessage;
        this.relatedStreamID = relatedStreamID;
        this.relatedSequenceNumber = relatedSequenceNumber;
    }

    public int getErrorCode() {
        return errorCode;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    @JsonProperty("related_stream_id") public long getRelatedStreamID() { return relatedStreamID; }
    public long getRelatedSequenceNumber() { return relatedSequenceNumber; }

}
