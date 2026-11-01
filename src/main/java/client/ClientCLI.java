package src.main.java.client;

import src.main.java.common.*;
import java.io.IOException;
import java.util.Scanner;

public class ClientCLI {
    private final TCPClient tcpClient;

    public ClientCLI(TCPClient client) {
        tcpClient = client;
    }

    public void displayMenu() {
        System.out.println("Choose one of the options");
        if (!tcpClient.getAuthenticated()) {
            System.out.println("1. Signup");
            System.out.println("2. Login");
            System.out.println("3. Exit");
        }
        else if (tcpClient.getAuthenticated()) {
            System.out.println("1. Online Users List");
            System.out.println("2. Private Chat");
            System.out.println("3. Global Chat");
            System.out.println("4. Logout");
        }
    }

    public void startSending() throws IOException {
        while (tcpClient.getRunning()) {
            Scanner scanner = new Scanner(System.in);
            String command = scanner.nextLine();
            if (tcpClient.getAuthenticated()) {
                switch (command) {
                    case "1": {
                        Packet packet = tcpClient.createOnlineUsersListPacket();
                        tcpClient.sendPacket(packet);
                        break;
                    }
                    case "2": {
                        int recipientId = scanner.nextInt();
                        String message = scanner.nextLine();
                        Packet packet = tcpClient.createPrivateChatPacket(recipientId, message);
                        tcpClient.sendPacket(packet);
                        break;
                    }
                    case "3": {
                        String message = scanner.nextLine();
                        Packet packet = tcpClient.createGlobalChatPacket(message);
                        tcpClient.sendPacket(packet);
                        break;
                    }
                    case "4": {
                        Packet packet = tcpClient.createLogoutPacket();
                        tcpClient.sendPacket(packet);
                        break;
                    }
                }
            }
            else {
                switch (command) {
                    case "1": {
                        String username = scanner.nextLine();
                        String password = scanner.nextLine();
                        Packet packet = tcpClient.createSignupPacket(username, password);
                        tcpClient.sendPacket(packet);
                        break;
                    }
                    case "2": {
                        String username = scanner.nextLine();
                        String password = scanner.nextLine();
                        Packet packet = tcpClient.createLoginPacket(username, password);
                        tcpClient.sendPacket(packet);
                        break;
                    }
                    case "3": {
                        break;
                    }
                }
            }
        }
    }
}
