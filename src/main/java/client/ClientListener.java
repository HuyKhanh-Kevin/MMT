package src.main.java.client;

import src.main.java.common.payload.*;
import java.util.*;

public interface ClientListener {
    public void displayUserList(List<UserInfo> users);
    public void displayMessage(int senderId, String message);
    public void displaySignupResponse();
    public void displayLoginResponse(boolean status, String reason);
    public void displayLogoutResponse();
}
