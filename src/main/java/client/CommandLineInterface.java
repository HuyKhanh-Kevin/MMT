package src.main.java.client;

import src.main.java.common.*;
import java.io.IOException;
import java.util.List;
import java.util.Scanner;
import src.main.java.common.payload.*;

public class CommandLineInterface implements ClientListener{
    private final Client client;

    public CommandLineInterface(Client client) {
        this.client = client;
    }

    public void displayMenu() {
        System.out.println("Choose one of the options");
        if (!client.getAuthenticated()) {
            System.out.println("1. Signup");
            System.out.println("2. Login");
            System.out.println("3. Exit");
        }
        else if (client.getAuthenticated()) {
            System.out.println("1. Online Users List");
            System.out.println("2. Private Chat");
            System.out.println("3. Global Chat");
            System.out.println("4. Logout");
        }
    }

    public void startSending() throws IOException {
        while (client.getRunning()) {
            Scanner scanner = new Scanner(System.in);
            String command = scanner.nextLine();
            if (client.getAuthenticated()) {
                switch (command) {
                    case "1": {
                        Packet packet = client.createOnlineUsersListPacket();
                        client.sendUDPPacket(packet);
                        break;
                    }
                    case "2": {
                        int recipientId = scanner.nextInt();
                        String message = scanner.nextLine();
                        Packet packet = client.createPrivateChatPacket(recipientId, message);
                        client.sendTCPPacket(packet);
                        break;
                    }
                    case "3": {
                        String message = scanner.nextLine();
                        Packet packet = client.createGlobalChatPacket(message);
                        client.sendTCPPacket(packet);
                        break;
                    }
                    case "4": {
                        Packet packet = client.createLogoutPacket();
                        client.sendTCPPacket(packet);
                        break;
                    }
                }
            }
            else {
                switch (command) {
                    case "1": {
                        String username = scanner.nextLine();
                        String password = scanner.nextLine();
                        Packet packet = client.createSignupPacket(username, password);
                        client.sendTCPPacket(packet);
                        break;
                    }
                    case "2": {
                        String username = scanner.nextLine();
                        String password = scanner.nextLine();
                        Packet packet = client.createLoginPacket(username, password);
                        client.sendTCPPacket(packet);
                        break;
                    }
                    case "3": {
                        break;
                    }
                }
            }
        }
    }

    @Override
    public void displayUserList(List<UserInfo> users) {
        for (UserInfo user : users) {
            System.out.println("id: " + user.userID() + " | username: " + user.username() + " | status: " + user.status());
        }
    }

    @Override
    public void displayMessage(int senderId, String message) {
        System.out.println("id: " + senderId + " | message: " + message);
    }

    @Override
    public void displaySignupResponse() {
        System.out.println("signup successful");
    }

    @Override
    public void displayLoginResponse(boolean status, String reason) {
        if (status) {
            System.out.println("login successful");
        }
        else {
            System.out.println("login failed");
            System.out.println("reason: " + reason);
        }
    }

    @Override
    public void displayLogoutResponse() {
        System.out.println("logout successful");
    }
}
