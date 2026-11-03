package src.main.java.filetransfer;

import src.main.java.common.PacketHeader;
import src.main.java.common.ProtocolConstants;

import java.io.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public class FileSender {
    private static final int RESEND_LIMIT = 3;
    private static final int MESSAGE_ERROR_LIMIT = 5;

    private static final int TYPE_FILE_REQ    = 0x07;
    private static final int TYPE_FILE_CHUNK  = 0x08;
    
    // For demo only
    private static final long SENDER_ID   = 1;
    private static final long RECEIVER_ID = 2;
    private static final long STREAM_ID   = 20;
    private static final long FILE_ID     = 42;

    public static void main(String[] args) throws Exception {
        if (args.length < 3) {
            System.out.println("FileSender <tcp_host> <port> <file_path>");
            System.exit(1);
        }

        String receiverHost = args[0];
        int receiverTcpPort = Integer.parseInt(args[1]);
        Path filePath = Path.of(args[2]);
        if (!Files.exists(filePath) || !Files.isRegularFile(filePath)) {
            System.err.println("File not found: " + filePath.toString());
            System.exit(1);
        }

        // === Meta data ===
        byte[] fileData   = Files.readAllBytes(filePath);
        long   fileSize   = fileData.length;
        int    totalChunks = (int) Math.ceil((double) fileSize / ProtocolConstants.MAX_CHUNK_DATA_SIZE);
        if (fileSize == 0) totalChunks = 0;
        String checksum = sha256Hex(fileData);
        String fileName = filePath.getFileName().toString();

        System.out.println("=== FileSender started ===");
        System.out.println("ID (fixed for demo): " + FILE_ID);
        System.out.println("Name: " + fileName);
        System.out.println("Size: " + fileSize);
        System.out.println("Chunks: " + totalChunks);
        System.out.println("Checksum: " + checksum);

        // === Main part ===
        System.out.printf("Connecting to %s:%d...%n", receiverHost, receiverTcpPort);
        try (Socket tcpSocket = new Socket(receiverHost, receiverTcpPort)) {
            System.out.println("connected.");
            
            DataOutputStream tcpOut = new DataOutputStream(tcpSocket.getOutputStream());
            DataInputStream  tcpIn  = new DataInputStream(tcpSocket.getInputStream());

            // === FILE_REQ ===
            sendFileReq(tcpOut, FILE_ID, fileName, fileSize, totalChunks, checksum);
            System.out.println("FILE_REQ.");

            // === FILE_ACCEPT / FILE_REJECT ===
            int responseType = receiveControlMessage(tcpIn);
            if (responseType == FileTransferProtocol.TYPE_FILE_REJECT) {
                System.err.println("FILE_REJECT");
                return;
            }
            if (responseType != FileTransferProtocol.TYPE_FILE_ACCEPT) {
                System.err.printf("Strange message: 0x%02X%n", responseType);
                return;
            }
            System.out.println("FILE_ACCEPT");

            // === Send chunks ===
            int resendCount = 0;
            int msgErrCount = 0;
            int receiverUdpPort = receiverTcpPort + 1; // UDP port = TCP port + 1 (used for demo)
            boolean done = false;
            while (!done) {
                sendAllChunks(receiverHost, receiverUdpPort, FILE_ID, fileData, totalChunks);

                // === FILE_DONE / REQ_RESEND / ERROR_FILE ===
                int msgType = receiveControlMessage(tcpIn);
                switch (msgType) {
                    case FileTransferProtocol.TYPE_FILE_DONE:
                        System.out.println("FILE_DONE");
                        done = true;
                        break;

                    case FileTransferProtocol.TYPE_REQ_RESEND:
                        resendCount++;
                        if (resendCount > RESEND_LIMIT) {
                            System.err.println("RESEND limit exceeded");
                            done = true;
                            break;
                        }
                        System.out.printf("REQ_RESEND (attempt %d/%d)",
                                resendCount, RESEND_LIMIT);
                        break;

                    case FileTransferProtocol.TYPE_ERROR_FILE:
                        System.err.println("ERROR_FILE");
                        done = true;
                        break;

                    default:
                        System.out.printf("Strange message: 0x%02X%n", msgType);
                        if(msgErrCount > MESSAGE_ERROR_LIMIT){
                            System.out.println("Ignored too much messages!");
                            done = true;
                        }
                }
            }
        }

        System.out.println("=== FileSender finished ===");
    }


    // FILE_REQ function
    private static void sendFileReq(DataOutputStream out, long ID, String fileName, long fileSize, int totalChunks, String checksum) throws Exception{
        // Payload
        String json = String.format(
            "{\"File_ID\":%d,\"File_Name\":\"%s\",\"File_Size\":%d,\"Total_Chunks\":%d,\"Checksum\":\"%s\"}",
            ID, fileName, fileSize, totalChunks, checksum
        );
        byte[] payload = json.getBytes("UTF-8");
        
        // Header
        PacketHeader header = new PacketHeader(
            ProtocolConstants.VERSION, TYPE_FILE_REQ, FileTransferProtocol.FLAG_ACK_NOT_REQUIRED, STREAM_ID, 1, SENDER_ID, RECEIVER_ID, payload.length
        );

        // Send
        out.write(header.toBytes());
        out.write(payload);
        out.flush();
        return;
    }

    // Send Chunks function
    private static void sendAllChunks(String receiverAddr, int receiverUdpPort, long fileId, byte[] fileData, int totalChunks) throws IOException{
        try (DatagramSocket udpSocket = new DatagramSocket()) {
            for (int chunkOrder = 0; chunkOrder < totalChunks; chunkOrder++) {
                // Payload
                int offset = chunkOrder * ProtocolConstants.MAX_CHUNK_DATA_SIZE;
                int length = Math.min(ProtocolConstants.MAX_CHUNK_DATA_SIZE, fileData.length - offset);
                byte[] chunkData = new byte[length];
                System.arraycopy(fileData, offset, chunkData, 0, length);
    
                int chunkPayloadSize = ProtocolConstants.CHUNK_METADATA_SIZE + length;
                ByteBuffer chunkPayload = ByteBuffer.allocate(chunkPayloadSize);
                chunkPayload.putInt((int) fileId);
                chunkPayload.putInt(chunkOrder);
                chunkPayload.putInt(length);
                chunkPayload.put(chunkData);
    
                // Header
                PacketHeader header = new PacketHeader(
                    ProtocolConstants.VERSION, TYPE_FILE_CHUNK, FileTransferProtocol.FLAG_ACK_REQUIRED, STREAM_ID, chunkOrder + 2, SENDER_ID, RECEIVER_ID, chunkPayloadSize
                );
    
                // Send
                byte[] headerBytes  = header.toBytes();
                byte[] payloadBytes = chunkPayload.array();
                byte[] datagram     = new byte[headerBytes.length + payloadBytes.length];
                System.arraycopy(headerBytes, 0, datagram, 0, headerBytes.length);
                System.arraycopy(payloadBytes, 0, datagram, headerBytes.length, payloadBytes.length);
    
                InetAddress rAddr = InetAddress.getByName(receiverAddr);
                DatagramPacket packet = new DatagramPacket(datagram, datagram.length, rAddr, receiverUdpPort);
                udpSocket.send(packet);
    
                System.out.printf("[UDP] Sent chunk %d/%d (%d bytes)%n", chunkOrder + 1, totalChunks, length);
            }
        }
    }

    // Receive Control Message fucntion
    private static int receiveControlMessage(DataInputStream in) throws IOException {
        byte[] headerBuf = new byte[PacketHeader.SIZE];
        in.readFully(headerBuf);
        PacketHeader header = PacketHeader.fromBytes(headerBuf);
        
        byte[] payloadBuf = new byte[(int) header.payloadLength];
        in.readFully(payloadBuf); 
        String payload = new String(payloadBuf, "UTF-8"); // Haven't been used in demo

        System.out.printf("Received header: %s, with payload: %s%n", header, payload);

        return header.messageType;
    }


    private static String sha256Hex(byte[] data) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(data);
        return HexFormat.of().formatHex(hash);
    }
}