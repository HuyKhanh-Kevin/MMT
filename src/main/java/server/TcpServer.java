package server;

import java.io.IOException;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class TcpServer {
    private final int port;
    private final SessionManager sessionManager = new SessionManager();
    private final ExecutorService threadPool = Executors.newCachedThreadPool();

    public TcpServer(int port) {
        this.port = port;
    }

    public void start() {
        try (ServerSocket serverSocket = new ServerSocket(port)) {
            System.out.println("==================================================");
            System.out.println("[SERVER] TCP Server đang lắng nghe tại port: " + port);
            System.out.println("==================================================");

            while (true) {
                Socket clientSocket = serverSocket.accept();
                System.out.println("[SERVER] Nhận kết nối mới từ: " + clientSocket.getInetAddress());

                ClientSession session = new ClientSession(clientSocket);
                threadPool.execute(new ClientHandler(session, sessionManager));
            }
        } catch (IOException e) {
            System.err.println("[SERVER] Lỗi khởi chạy Server: " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        int port = 8080;
        new TcpServer(port).start();
    }
}