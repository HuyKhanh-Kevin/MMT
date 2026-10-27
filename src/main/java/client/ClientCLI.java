package src.main.java.client;

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
        }
    }

    public void startSending() {}
}
