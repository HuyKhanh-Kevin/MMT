package common.payload;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

public final class UserListResponse {
    private final List<UserInfo> users;

    @JsonCreator
    public UserListResponse(
            @JsonProperty("users") List<UserInfo> users) {

        if (users == null) {
            throw new IllegalArgumentException(
                    "Users must not be null");
        }

        this.users = List.copyOf(users);
    }

    public List<UserInfo> getUsers() {
        return users;
    }
}