package client;

import common.payload.LoginResponse;
import common.payload.SignupResponse;

import java.io.Console;
import java.io.IOException;
import java.net.DatagramSocket;
import java.net.ServerSocket;
import java.util.Arrays;
import java.util.Scanner;

/** Account demo only; the peer listeners reserve real ports for endpoint registration. */
public final class AccountDemo {
    private AccountDemo() {}

    public static void main(String[] args) throws Exception {
        String host = args.length > 0 ? args[0] : "127.0.0.1";
        int tcpPort = args.length > 1 ? Integer.parseInt(args[1]) : 5000;
        int udpPort = args.length > 2 ? Integer.parseInt(args[2]) : 5000;
        try (ServerSocket peer = new ServerSocket(0);
             DatagramSocket file = new DatagramSocket(0);
             AccountClient client = new AccountClient(host, tcpPort, udpPort, peer.getLocalPort(), file.getLocalPort());
             Scanner input = new Scanner(System.in)) {
            client.onPresence(update -> System.out.printf("%n[presence] %s: %s%n", update.username(), update.status()));
            System.out.println("Commands: signup, login, users, logout, pause, resume, quit");
            while (true) {
                System.out.print("> ");
                if (!input.hasNextLine()) break;
                String command = input.nextLine().trim();
                try {
                    switch (command) {
                        case "signup", "login" -> {
                            System.out.print("Username: ");
                            String username = input.nextLine();
                            String password = readPassword(input);
                            if (command.equals("signup")) {
                                SignupResponse response = client.signup(username, password);
                                System.out.println(response.getStatus() + (response.getReason() == null ? "" : ": " + response.getReason()));
                            } else {
                                LoginResponse response = client.login(username, password);
                                System.out.println(response.isStatus() ? "Online. user_id=" + response.getUserID()
                                        : "Login failed: " + response.getReason());
                            }
                        }
                        case "users" -> client.onlineUsers().forEach(user -> System.out.printf(
                                "%d %-32s %s TCP=%d file UDP=%d%n", user.userID(), user.username(),
                                user.ip(), user.tcpPort(), user.fileUdpPort()));
                        case "logout" -> { client.logout(); System.out.println("Logged out."); }
                        case "pause" -> { client.setHeartbeatsEnabled(false); System.out.println("Heartbeat paused. Session expires after 15s of silence."); }
                        case "resume" -> { client.setHeartbeatsEnabled(true); System.out.println("Heartbeat resumed (if session has not expired)."); }
                        case "quit" -> {
                            if (client.isAuthenticated()) try { client.logout(); } catch (IOException ignored) { }
                            return;
                        }
                        default -> System.out.println("Commands: signup, login, users, logout, pause, resume, quit");
                    }
                } catch (IOException | IllegalArgumentException e) {
                    System.out.println("Request failed: " + e.getMessage());
                }
            }
        }
    }

    private static String readPassword(Scanner fallback) {
        Console console = System.console();
        if (console == null) {
            System.out.print("Password (visible in this terminal): ");
            return fallback.nextLine();
        }
        char[] password = console.readPassword("Password: ");
        if (password == null) return "";
        try { return new String(password); }
        finally { Arrays.fill(password, '\0'); }
    }
}
