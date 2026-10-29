# BTL Mạng Máy Tính - Distributed Streaming Collaboration Application
> **Đại học Bách Khoa TP.HCM (HCMUT)**  
> **Môn học:** Lập trình ứng dụng mạng (Network Application Development)  
> **Ngôn ngữ:** Java 17 | **Build Tool:** Apache Maven  

---

## 1. Yêu cầu hệ thống (Prerequisites)
* **Java:** JDK 17 trở lên (đã kiểm tra tương thích trên Eclipse Adoptium Temurin 17 / OpenJDK 17).
* **Maven:** Apache Maven 3.8+ (hoặc dùng Maven tích hợp sẵn trong IDE).

---

## 2. Hướng dẫn biên dịch & Chạy kiểm thử (How to Build & Test)

### Bước 1: Biên dịch toàn bộ dự án
Mở terminal tại thư mục gốc `MMT` và chạy:
```bash
mvn clean compile
```

### Bước 2: Chạy toàn bộ 15 ca kiểm thử tích hợp & xử lý lỗi (Integration Tests)
```bash
mvn test
```
*Kết quả mong đợi:* Toàn bộ 16/16 bài kiểm thử chạy thành công với `BUILD SUCCESS`.

### Bước 3: Chạy trực tiếp qua Java / IDE (Dành cho Vấn đáp Demo)
Bạn có thể mở bất kỳ IDE nào (VS Code, IntelliJ IDEA, Eclipse) và **Run** file:
`src/test/java/integration/MasterIntegrationTest.java`

Hoặc chạy từ dòng lệnh:
```bash
java -cp "target/classes;target/test-classes;target/dependency/*" integration.MasterIntegrationTest
```
Màn hình sẽ hiển thị bảng báo cáo chi tiết trực quan theo thời gian thực (Console Output).

---

## 3. Bảng ma trận kiểm thử tích hợp & Xử lý lỗi (Test Cases Matrix)
*(Phần việc phụ trách: **P. Tuấn** - Kiểm thử tích hợp & Xử lý lỗi)*

| STT | Phân nhóm kiểm thử | Kịch bản kiểm thử (Test Scenario) | Mã lỗi / Ngoại lệ mong đợi | Ý nghĩa bản chất mạng (Dành cho vấn đáp) | Kết quả |
| :---: | :--- | :--- | :---: | :--- | :---: |
| **1** | Gói tin lỗi (Malformed) | Header gửi thiếu byte (< 24 bytes) | `EOFException` | Client đóng giữa chừng, server không đọc tràn bộ nhớ | **PASSED** |
| **2** | Gói tin lỗi (Malformed) | Phiên bản giao thức sai (`version != 2`) | `IllegalArgumentException` | Kiểm tra tính tương thích phiên bản giao thức | **PASSED** |
| **3** | Gói tin lỗi (Malformed) | Loại gói tin lạ (`type = 0x99`) | `IllegalArgumentException` | Từ chối các thông điệp không nằm trong đặc tả | **PASSED** |
| **4** | Gói tin lỗi (Malformed) | Khai khống `payload_length` rồi ngắt | `EOFException` / `SocketException` | Bắt lỗi phân mảnh thiếu byte, không treo luồng đọc | **PASSED** |
| **5** | Gói tin lỗi (Malformed) | Gói tin vượt kích thước tối đa (> 65KB)| `IllegalArgumentException` | Tránh tấn công làm tràn bộ nhớ đệm (Buffer Overflow) | **PASSED** |
| **6** | Ngắt kết nối (Disconnect) | Client kết nối rồi đóng ngay lập tức | `EOF / Null packet` | Server giải phóng socket sạch sẽ, không quăng lỗi lạ | **PASSED** |
| **7** | Ngắt kết nối (Disconnect) | Client ngắt đột ngột bằng cờ TCP RST | `SocketException` | Bắt ngoại lệ Connection Reset mà không làm sập server | **PASSED** |
| **8** | Ngắt kết nối (Disconnect) | 5 client ngắt kết nối đồng thời | Concurrency Safe | Server đa luồng xử lý ổn định, vẫn nhận client mới | **PASSED** |
| **9** | Toàn vẹn file (Integrity)| Chia nhỏ file thành các chunk <= 1024B | `SHA-256 Match` | Đảm bảo kích thước chunk chống phân mảnh IP tầng mạng | **PASSED** |
| **10**| Toàn vẹn file (Integrity)| Phát hiện 1 byte bị sai lệch (Bit-flip) | `ErrorCode: 3002 (FILE_HASH_MISMATCH)` | Receiver phát hiện file hỏng, hủy file tạm và gửi lỗi | **PASSED** |
| **11**| Toàn vẹn file (Integrity)| Chunk UDP đến lộn xộn thứ tự | `Chunk Sorting` | Receiver tự sắp xếp lại theo `chunkOrder` trước khi ghép | **PASSED** |
| **12**| Bảo mật (Security) | Mật khẩu lưu trong hệ thống | `Salt + PBKDF2` | Mật khẩu không bao giờ lưu plain text trong CSDL | **PASSED** |
| **13**| Bảo mật (Security) | Tính duy nhất của Salt ngẫu nhiên | `Anti-Rainbow Table` | Cùng mật khẩu nhưng sinh ra mã băm khác nhau | **PASSED** |
| **14**| Bảo mật (Security) | Xác thực sai mật khẩu đăng nhập | `ErrorCode: 1001 (INVALID_CREDENTIALS)` | Trả về mã lỗi từ chối đăng nhập chính xác | **PASSED** |
| **15**| Bảo mật (Security) | Mật khẩu ngắn không đạt chuẩn (< 8 ký tự)| `ErrorCode: 1003 (INVALID_PAYLOAD)` | Kiểm tra ràng buộc hợp lệ đầu vào ngay từ đầu | **PASSED** |

---

## 4. Hướng dẫn trả lời vấn đáp nhanh (Oral Defense Cheat-Sheet)

1. **Hỏi: "Em làm phần gì trong nhóm?"**
   * *Trả lời:* "Dạ em là **P. Tuấn**, phụ trách phần **Kiểm thử tích hợp và Xử lý lỗi (Integration Testing & Fault Resilience)**. Em đảm bảo hệ thống có khả năng chịu lỗi cao: khi client gửi dữ liệu rác, ngắt kết nối đột ngột hoặc file bị sai mã hash thì Server và Client vẫn xử lý an toàn mà không bị crash."

2. **Hỏi: "Làm sao đảm bảo khi client ngắt đột ngột thì Server không bị đứng hoặc crash?"**
   * *Trả lời:* "Dạ trong `PacketIO.java` và các luồng xử lý socket, khi client ngắt đột ngột (`TCP RST` hoặc đứt cáp), hàm `readNBytes()` sẽ phát hiện kết nối đóng và ném ra `EOFException` hoặc `SocketException`. Server bắt các ngoại lệ này trong khối `try-catch`, đóng socket và thu hồi tài nguyên sạch sẽ thay vì để exception văng ra ngoài làm sập Server. Em đã kiểm chứng bằng ca test đồng thời 5 client ngắt kết nối trong `TestSuddenDisconnect.java`."

3. **Hỏi: "Cơ chế kiểm tra toàn vẹn file qua UDP hoạt động như thế nào?"**
   * *Trả lời:* "Dạ file được chia thành các chunk tối đa 1024 bytes kèm `chunkOrder`. Sau khi nhận đủ, Receiver sắp xếp lại đúng thứ tự và tính mã băm SHA-256 của toàn bộ file đã ghép. Nếu mã hash tính lại khác với mã hash trong Metadata ban đầu (dù chỉ lệch 1 bit), Receiver sẽ từ chối lưu file và trả về mã lỗi `3002 (FILE_HASH_MISMATCH)`."
