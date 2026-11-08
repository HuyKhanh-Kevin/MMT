package common.payload;

import com.fasterxml.jackson.annotation.JsonProperty;

public record PresenceUpdate(@JsonProperty("username") String username,
                             @JsonProperty("status") String status) {}
