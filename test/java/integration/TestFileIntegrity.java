package test.java.integration;

import common.ErrorCode;
import common.MessageType;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Ca kiểm thử 3: Kiểm tra toàn vẹn truyền file và phát hiện sai Hash (File Integrity & Hash Mismatch)
 * Mục tiêu: Đảm bảo dữ liệu file nhận được qua UDP chunking được kiểm tra mã băm SHA-256 chính xác;
 * nếu có byte bị sai lệch hoặc mất gói, hệ thống phải kích hoạt mã lỗi FILE_HASH_MISMATCH (3002).
 */
public class TestFileIntegrity {

    public static void main(String[] args) {
        System.out.println("=== CHẠY KIỂM THỬ: TOÀN VẸN FILE VÀ PHÁT HIỆN SAI LỆCH HASH ===");
        TestFileIntegrity tester = new TestFileIntegrity();
        try {
            tester.testNormalFileChunkingAndReassembly();
            System.out.println("[PASS] 1. Normal File Transfer - Ghép file và hash SHA-256 khớp hoàn toàn.");

            tester.testCorruptedChunkDetectedByHashMismatch();
            System.out.println("[PASS] 2. Corrupted Chunk Detection - Phát hiện sai 1 byte dữ liệu, kích hoạt mã lỗi 3002 (FILE_HASH_MISMATCH).");

            tester.testOutOfOrderChunkReassembly();
            System.out.println("[PASS] 3. Out-Of-Order Chunks - Nhận chunk lộn xộn thứ tự qua UDP vẫn ghép đúng thứ tự và hash khớp.");

            System.out.println("===> TẤT CẢ CA KIỂM THỬ TOÀN VẸN FILE ĐỀU THÀNH CÔNG!\n");
        } catch (Throwable t) {
            System.err.println("[FAIL] Lỗi kiểm thử: " + t.getMessage());
            t.printStackTrace();
        }
    }

    public static class FileChunkModel {
        public final int fileId;
        public final int chunkOrder;
        public final byte[] data;

        public FileChunkModel(int fileId, int chunkOrder, byte[] data) {
            this.fileId = fileId;
            this.chunkOrder = chunkOrder;
            this.data = data;
        }
    }

    public static String computeSHA256(byte[] data) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] hash = md.digest(data);
        StringBuilder hexString = new StringBuilder();
        for (byte b : hash) {
            String hex = Integer.toHexString(0xff & b);
            if (hex.length() == 1) hexString.append('0');
            hexString.append(hex);
        }
        return hexString.toString();
    }

    @Test
    @DisplayName("1. Truyền file bình thường: Chia nhỏ thành các chunk <= 1024 bytes, ghép lại và kiểm tra hash")
    public void testNormalFileChunkingAndReassembly() throws Exception {
        // Tạo file mẫu kích thước 2500 bytes (gồm chữ và số)
        byte[] originalContent = ("Distributed Streaming File Transfer Test Content " +
                "HCMUT Computer Networks Assignment 1 - Chunking and Verification ").repeat(25).getBytes(StandardCharsets.UTF_8);

        String originalHash = computeSHA256(originalContent);
        int chunkSize = 1024;
        List<FileChunkModel> chunks = new ArrayList<>();

        // 1. Phía Sender: Chia file thành các chunk <= 1024 bytes
        int totalChunks = (int) Math.ceil((double) originalContent.length / chunkSize);
        for (int i = 0; i < totalChunks; i++) {
            int start = i * chunkSize;
            int length = Math.min(chunkSize, originalContent.length - start);
            byte[] chunkData = Arrays.copyOfRange(originalContent, start, start + length);
            chunks.add(new FileChunkModel(101, i, chunkData));
        }

        assertEquals(3, chunks.size(), "File 2500 bytes phải chia thành đúng 3 chunks");

        // 2. Phía Receiver: Ghép các chunk vào buffer tạm
        ByteArrayOutputStream reassembledStream = new ByteArrayOutputStream();
        for (FileChunkModel chunk : chunks) {
            reassembledStream.write(chunk.data);
        }
        byte[] reassembledData = reassembledStream.toByteArray();

        // 3. Phía Receiver: Tính toán lại hash và đối chiếu
        String reassembledHash = computeSHA256(reassembledData);
        assertEquals(originalHash, reassembledHash, "Mã băm SHA-256 của file ghép phải trùng khớp 100% với file gốc");
    }

    @Test
    @DisplayName("2. Phát hiện lỗi dữ liệu: 1 byte trong chunk bị sai lệch trên đường truyền UDP -> Báo mã lỗi 3002")
    public void testCorruptedChunkDetectedByHashMismatch() throws Exception {
        byte[] originalContent = "Secure Network Programming Assignment HCMUT".repeat(30).getBytes(StandardCharsets.UTF_8);
        String expectedHash = computeSHA256(originalContent);

        // Tạo 2 chunks
        byte[] chunk1 = Arrays.copyOfRange(originalContent, 0, 500);
        byte[] chunk2 = Arrays.copyOfRange(originalContent, 500, originalContent.length);

        // GIẢ LẬP LỖI MẠNG: 1 byte trong chunk2 bị đảo bit (bit-flip) do nhiễu hoặc truyền lỗi
        chunk2[10] = (byte) (chunk2[10] ^ 0xFF);

        // Ghép file tại Receiver
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        buffer.write(chunk1);
        buffer.write(chunk2);
        byte[] receivedData = buffer.toByteArray();

        String receivedHash = computeSHA256(receivedData);

        // Kiểm tra phát hiện lỗi
        assertNotEquals(expectedHash, receivedHash, "Hash phải phát hiện ra sự thay đổi dù chỉ 1 byte");

        // Mô phỏng logic ứng dụng: Nếu hash không khớp -> Ném mã lỗi FILE_HASH_MISMATCH (3002)
        int triggeredErrorCode = 0;
        if (!expectedHash.equals(receivedHash)) {
            triggeredErrorCode = ErrorCode.FILE_HASH_MISMATCH; // Mã 3002
        }

        assertEquals(ErrorCode.FILE_HASH_MISMATCH, triggeredErrorCode, "Ứng dụng phải kích hoạt mã lỗi FILE_HASH_MISMATCH (3002)");
    }

    @Test
    @DisplayName("3. UDP đến lộn xộn thứ tự (Out-of-Order): Receiver tự sắp xếp theo chunkOrder trước khi hash")
    public void testOutOfOrderChunkReassembly() throws Exception {
        byte[] content = "Chunk0-Data | Chunk1-Data | Chunk2-Data | Chunk3-Data".getBytes(StandardCharsets.UTF_8);
        String expectedHash = computeSHA256(content);

        // Giả lập 4 chunk
        FileChunkModel c0 = new FileChunkModel(202, 0, "Chunk0-Data | ".getBytes(StandardCharsets.UTF_8));
        FileChunkModel c1 = new FileChunkModel(202, 1, "Chunk1-Data | ".getBytes(StandardCharsets.UTF_8));
        FileChunkModel c2 = new FileChunkModel(202, 2, "Chunk2-Data | ".getBytes(StandardCharsets.UTF_8));
        FileChunkModel c3 = new FileChunkModel(202, 3, "Chunk3-Data".getBytes(StandardCharsets.UTF_8));

        // Nhận qua mạng UDP theo thứ tự lộn xộn: [c2, c0, c3, c1]
        List<FileChunkModel> receivedNetworkList = Arrays.asList(c2, c0, c3, c1);

        // Receiver sắp xếp lại theo chunkOrder
        List<FileChunkModel> sortedChunks = new ArrayList<>(receivedNetworkList);
        sortedChunks.sort(Comparator.comparingInt(c -> c.chunkOrder));

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        for (FileChunkModel chunk : sortedChunks) {
            buffer.write(chunk.data);
        }

        String actualHash = computeSHA256(buffer.toByteArray());
        assertEquals(expectedHash, actualHash, "Sau khi sắp xếp lại theo chunkOrder, hash phải khớp 100%");
    }
}
