package common.payload;

import com.fasterxml.jackson.annotation.JsonProperty;

public record SignupRequest(@JsonProperty("username") String username,
                            @JsonProperty("password") String password) {}
