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
        Scanner scanner = new Scanner(System.in);
        while (client.getRunning()) {
            String command = scanner.nextLine();
            if (!client.getRunning()) break;
            if (client.getAuthenticated()) {
                switch (command) {
                    case "1": {
                        Packet packet = client.createOnlineUsersListPacket();
                        client.sendUDPPacket(packet);
                        break;
                    }
                    case "2": {
                        int recipientId = Integer.parseInt(scanner.nextLine());
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
                        client.exitProgram();
                        break;
                    }
                }
            }
        }
    }

    @Override
    public void displayUserList(List<UserInfo> users) {
        System.out.println("Users list:");
        for (UserInfo user : users) {
            System.out.println("ID: " + user.userID() + " | Username: " + user.username() + " | Status: " + user.status());
        }
    }

    @Override
    public void displayMessage(int senderId, String message) {
        System.out.println("ID: " + senderId + " | Message: " + message);
    }

    @Override
    public void displaySignupResponse(String status, String reason) {
        if (status.equals("success")) {
            System.out.println("Signup successful");
            System.out.println("Please login to your account");
        }
        else {
            System.out.println("Signup failed");
            System.out.println("Reason: " + reason);
        }
    }

    @Override
    public void displayLoginResponse(String status, String reason) {
        if (status.equals("success")) {
            System.out.println("Login successful");
        }
        else {
            System.out.println("Login failed");
            System.out.println("Reason: " + reason);
        }
    }

    @Override
    public void displayLogoutResponse() {
        System.out.println("Logout successful");
        System.out.println("Connection closed. Press Enter to exit.");
    }

    @Override
    public void displayError(int code, String message) {
        System.out.println("Error: " + code + " | Message: " + message);
    }
}
