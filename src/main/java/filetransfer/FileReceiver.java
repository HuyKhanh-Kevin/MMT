package src.main.java.filetransfer;

import src.main.java.common.PacketHeader;
import src.main.java.common.ProtocolConstants;

import java.io.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.file.*;
import java.util.Arrays;

public class FileReceiver {
    private static final long MAX_FILE_SIZE = 104_857_600L;

    private static final int UDP_RECEIVE_TIMEOUT_MS = 15_000;

    private static final int RESEND_LIMIT = 3;

    // For demo only
    private static final long SENDER_ID   = 2L; 
    private static final long RECEIVER_ID = 1L;
    private static final long STREAM_ID   = 20L;

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.out.println("FileReceiver <tcp_port> <save_directory>");
            System.exit(1);
        }

        int    tcpPort   = Integer.parseInt(args[0]);
        Path   saveDir   = Paths.get(args[1]);

        System.out.println("=== FileReceiver started ===");

        // === Main part ===
        System.out.printf("Listening on TCP port %d%n", tcpPort);
        try (ServerSocket serverSocket = new ServerSocket(tcpPort)) {
            System.out.println("Waiting for sender connection...");
            try (Socket tcpSocket = serverSocket.accept()) {
                System.out.println("Sender connected: " + tcpSocket.getInetAddress());

                DataInputStream  tcpIn  = new DataInputStream(tcpSocket.getInputStream());
                DataOutputStream tcpOut = new DataOutputStream(tcpSocket.getOutputStream());

                // === FILE_REQ ===
                FileMetadata metadata = receiveFileReq(tcpIn);
                System.out.printf(
                    "FILE_REQ:%nfile='%s',%nsize=%d,%nchunks=%d,%nchecksum: %s%n", 
                    metadata.fileName, metadata.fileSize, metadata.totalChunks, metadata.checksum
                );

                // === FILE_REJECT ===
                if (metadata.fileSize > MAX_FILE_SIZE) {
                    System.err.println("FILE_REJECT");
                    sendFileReject(tcpOut, metadata.fileId, "File size exceeded 100 MiB");
                    return;
                }

                // === FILE_ACCEPT ===
                sendFileAccept(tcpOut, metadata.fileId);
                System.out.println("FILE_ACCEPT");

                // === Receive chunks ===
                byte[] fileBuffer = new byte[(int) metadata.fileSize];
                boolean[] chunkReceived = new boolean[metadata.totalChunks];

                int udpPort = tcpPort + 1; // UDP = TCP + 1 (used for demo)
                boolean done = false;
                while (!done) {
                    receiveChunks(udpPort, fileBuffer, chunkReceived, metadata);
                    
                    // === FILE_DONE / REQ_RESEND / ERROR_FILE ===
                    Files.createDirectories(saveDir);
                    Path outPath = saveDir.resolve(metadata.fileName);
                    Files.write(outPath, fileBuffer);
                    sendFileDone(tcpOut, metadata.fileId);
                    System.out.println("FILE_DONE.");
                    done = true;
                    
                }
            }
        }

        System.out.println("=== FileReceiver finished ===");
    }

    // Receive Chunks function
    private static void receiveChunks(int udpPort, byte[] fileBuffer, boolean[] chunkReceived, FileMetadata meta) throws Exception{
        try (DatagramSocket udpSocket = new DatagramSocket(udpPort)) {
            byte[] buf = new byte[ProtocolConstants.MAX_PACKET_SIZE];

            System.out.printf("[UDP] Listening on port %d%n",
                    udpPort, UDP_RECEIVE_TIMEOUT_MS);

            int received = 0;
            while (received < meta.totalChunks) {
                DatagramPacket datagram = new DatagramPacket(buf, buf.length);
                udpSocket.receive(datagram);

                byte[] data = Arrays.copyOf(datagram.getData(), datagram.getLength());
                ByteBuffer payload = ByteBuffer.wrap(data, PacketHeader.SIZE, data.length - PacketHeader.SIZE);

                long fileId     = payload.getInt() & 0xFFFFFFFFL;
                int  chunkOrder = payload.getInt();
                int  payloadLen = payload.getInt();

                byte[] chunkData = new byte[payloadLen];
                payload.get(chunkData);

                int bufOffset = chunkOrder * ProtocolConstants.MAX_CHUNK_DATA_SIZE;
                System.arraycopy(chunkData, 0, fileBuffer, bufOffset, payloadLen);

                if (!chunkReceived[chunkOrder]) {
                    chunkReceived[chunkOrder] = true;
                    received++;
                }
            }
            System.out.printf("[UDP] Finished receiving: %d/%d chunks.%n", received, meta.totalChunks);
        }
    }


    // FILE_REQ fucntion
    private static FileMetadata receiveFileReq(DataInputStream in) throws IOException {
        byte[] headerBuf = new byte[PacketHeader.SIZE];
        in.readFully(headerBuf);
        PacketHeader header = PacketHeader.fromBytes(headerBuf);

        if (header.messageType != FileTransferProtocol.TYPE_FILE_REQ) {
            throw new IOException("Expected FILE_REQ (0x07) but received: 0x" +
                    Integer.toHexString(header.messageType));
        }


        byte[] payloadBuf = new byte[(int) header.payloadLength];
        in.readFully(payloadBuf);
        String json = new String(payloadBuf, "UTF-8");
        System.out.println("FILE_REQ payload: " + json);


        long   fileId      = extractJsonLong(json, "File_ID");
        String fileName    = extractJsonString(json, "File_Name");
        long   fileSize    = extractJsonLong(json, "File_Size");
        int    totalChunks = (int) extractJsonLong(json, "Total_Chunks");
        String checksum    = extractJsonString(json, "Checksum");

        return new FileMetadata(fileId, fileName, fileSize, totalChunks, checksum);
    }

    // FILE_ACCEPT fucntion
    private static void sendFileAccept(DataOutputStream out, long fileId) throws IOException {
        String json = "{\"File_ID\":" + fileId + "}";
        sendTcpControlMessage(out, FileTransferProtocol.TYPE_FILE_ACCEPT, json);
    }

    // FILE_REJECT fucntion
    private static void sendFileReject(DataOutputStream out, long fileId, String reason) throws IOException {
        String json = "{\"File_ID\":" + fileId + ",\"reason\":\"" + reason + "\"}";
        sendTcpControlMessage(out, FileTransferProtocol.TYPE_FILE_REJECT, json);
    }

    // FILE_DONE fucntion
    private static void sendFileDone(DataOutputStream out, long fileId) throws IOException {
        String json = "{\"File_ID\":" + fileId + "}";
        sendTcpControlMessage(out, FileTransferProtocol.TYPE_FILE_DONE, json);
    }

    // REQ_RESEND fucntion
    private static void sendReqResend(DataOutputStream out, long fileId) throws IOException {}
    
    // ERROR_FILE fucntion
    private static void sendErrorFile(DataOutputStream out, long fileId) throws IOException {}

    // Send Control Message fucntion
    private static void sendTcpControlMessage(DataOutputStream out, int msgType, String json) throws IOException {
        byte[] payload = json.getBytes("UTF-8");
        PacketHeader header = new PacketHeader( ProtocolConstants.VERSION, msgType, FileTransferProtocol.FLAG_ACK_NOT_REQUIRED, 
                                                STREAM_ID, 0, SENDER_ID, RECEIVER_ID, payload.length );
        out.write(header.toBytes());
        out.write(payload);
        out.flush();
        System.out.printf("Sent 0x%02X: %s%n", msgType, json);
    }

    
    private static long extractJsonLong(String json, String key) {
        String search = "\"" + key + "\":";
        int idx = json.indexOf(search);
        if (idx < 0) throw new IllegalArgumentException("Key not found: " + key);
        int start = idx + search.length();
        int end = start;
        while (end < json.length() && (Character.isDigit(json.charAt(end)) || json.charAt(end) == '-')) end++;
        return Long.parseLong(json.substring(start, end));
    }

    private static String extractJsonString(String json, String key) {
        String search = "\"" + key + "\":\"";
        int idx = json.indexOf(search);
        if (idx < 0) throw new IllegalArgumentException("Key not found: " + key);
        int start = idx + search.length();
        int end = json.indexOf('"', start);
        return json.substring(start, end);
    }


    private static class FileMetadata {
        final long   fileId;
        final String fileName;
        final long   fileSize;
        final int    totalChunks;
        final String checksum;

        FileMetadata(long fileId, String fileName, long fileSize, int totalChunks, String checksum) {
            this.fileId      = fileId;
            this.fileName    = fileName;
            this.fileSize    = fileSize;
            this.totalChunks = totalChunks;
            this.checksum    = checksum;
        }
    }
}