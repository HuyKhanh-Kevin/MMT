# Common Protocol — 38 test cases

Tài liệu chuyển 38 phương thức `@Test` trong bộ CommonProtocolTests sang dạng **Example → Output**. Một test có thể chứa nhiều biến thể đầu vào; các biến thể vẫn thuộc cùng một test.

**Output là kết quả mong đợi của test**, không phải kết quả chạy mới trên branch main. JSON trong output biểu diễn dữ liệu sau giải mã; thứ tự key và khoảng trắng không phải điều kiện so sánh, trừ các test đo kích thước.

Bộ test kiểm tra serialization, validation, packet framing và TCP loopback. Với Login request, encode/decode thành công chỉ chứng minh dữ liệu hợp lệ theo model; không tự tạo Login response, không kiểm tra tài khoản hay mật khẩu trên server. Các Login response bên dưới là dữ liệu mẫu độc lập.

| Nhóm | Số test |
| --- | ---: |
| 1. Login request | 2 |
| 2. Login response | 7 |
| 3. JSON payload | 6 |
| 4. PacketCodec | 10 |
| 5. TCP PacketIO | 9 |
| 6. FileChunkCodec | 4 |
| **Tổng** | **38** |

Các giới hạn đang được kiểm tra: common header **24 bytes**, big-endian; application packet tối đa **1.200 bytes**; JSON payload tối đa **1.100 UTF-8 bytes**; chat text tối đa **1.000 UTF-8 bytes**; dữ liệu mỗi file chunk tối đa **1.024 bytes**.

## Login request

Dùng đúng giá trị từ test gốc. Trừ khi ghi rõ, thao tác là tạo object → encode JSON UTF-8 → decode về cùng kiểu.

### 1.1. Giữ nguyên dữ liệu khi encode/decode

Test gốc: `JsonPayloadCodecTest.loginRequestRoundTrip`.

**Example 1.1a**

```json
{
  "username": "alice",
  "password": "test-only-password",
  "tcp_port": 5001,
  "file_udp_port": 5002
}
```

**Output 1.1b**

```json
{
  "username": "alice",
  "password": "test-only-password",
  "tcp_port": 5001,
  "file_udp_port": 5002
}
```

Cả bốn trường giữ nguyên; không có exception.

---

### 1.2. Username, password và port không hợp lệ

Test gốc: `JsonPayloadCodecTest.rejectInvalidUsernamePasswordAndPorts`.

**Example 1.2a**

Tạo trực tiếp `new LoginRequest(username, password, tcpPort, fileUdpPort)`. Mỗi dòng là một biến thể độc lập; các trường còn lại dùng `alice`, `pw`, `5001`, `5002`.

| Biến thể | Giá trị |
| --- | --- |
| Username | `null`, `""`, `"a".repeat(33)`, `"á"` |
| Password | `null`, `""` |
| TCP port | `-1`, `0`, `65536` |
| File UDP port | `-1`, `0`, `65536` |
| Trường hợp hợp lệ ở biên | `new LoginRequest("alice", "pw", 1, 65535)` |

**Output 1.2b**

Các biến thể không hợp lệ ném `IllegalArgumentException`. Trường hợp port `1` và `65535` tạo object thành công.

Test hiện tại chỉ yêu cầu password khác null và không rỗng; không có quy tắc tối thiểu 8 ký tự. Vì vậy `"abc"` không tự bị từ chối bởi quy tắc này. Đúng/sai mật khẩu tài khoản thuộc kiểm thử chức năng login trên server.

---

## Login response

Hai test đầu tạo LoginResponse rồi encode/decode. Các test còn lại decode JSON đầu vào thành LoginResponse.

### 2.1. Response thành công với reason null

Test gốc: `JsonPayloadCodecTest.loginSuccessRoundTripWithNullReason`.

**Example 2.1a**

```json
{
  "status": true,
  "session_id": "session-test",
  "user_id": 4294967295,
  "reason": null
}
```

**Output 2.1b**

```json
{
  "status": true,
  "session_id": "session-test",
  "user_id": 4294967295,
  "reason": null
}
```

`user_id` giữ nguyên giá trị 4.294.967.295, không bị tràn về số âm.

---

### 2.2. Response thất bại với session và user ID null

Test gốc: `JsonPayloadCodecTest.loginFailureRoundTripWithNullSessionAndUserId`.

**Example 2.2a**

```json
{
  "status": false,
  "session_id": null,
  "user_id": null,
  "reason": "Invalid credentials"
}
```

**Output 2.2b**

```json
{
  "status": false,
  "session_id": null,
  "user_id": null,
  "reason": "Invalid credentials"
}
```

Cho phép hai giá trị null này khi `status = false`.

---

### 2.3. Thành công nhưng thiếu giá trị session

Test gốc: `JsonPayloadCodecTest.rejectSuccessWithoutSession`.

**Example 2.3a**

```json
{
  "status": true,
  "session_id": null,
  "user_id": 1,
  "reason": null
}
```

**Output 2.3b**

`IOException` — response thành công không có session hợp lệ.

---

### 2.4. Thành công nhưng user ID không hợp lệ

Test gốc: `JsonPayloadCodecTest.rejectSuccessWithoutValidUserId`.

**Example 2.4a**

```json
{
  "status": true,
  "session_id": "s",
  "user_id": null,
  "reason": null
}
```

Lần lượt thử `user_id`: `null`, `0`, `-1`, `4294967296`.

**Output 2.4b**

`IOException` cho cả bốn biến thể.

---

### 2.5. Thất bại nhưng không có lý do

Test gốc: `JsonPayloadCodecTest.rejectFailureWithoutReason`.

**Example 2.5a**

```json
{
  "status": false,
  "session_id": null,
  "user_id": null,
  "reason": null
}
```

Lần lượt thử `reason`: `null`, `""`, `"   "`.

**Output 2.5b**

`IOException` cho cả ba biến thể.

---

### 2.6. Thiếu status hoặc status null

Test gốc: `JsonPayloadCodecTest.rejectMissingOrNullStatus`.

**Example 2.6a**

Biến thể A:

```json
{
  "session_id": null,
  "user_id": null,
  "reason": "bad"
}
```

Biến thể B:

```json
{
  "status": null,
  "session_id": null,
  "user_id": null,
  "reason": "bad"
}
```

**Output 2.6b**

`IOException` cho cả hai biến thể.

---

### 2.7. Phải có đủ bốn key trong Login response

Test gốc: `JsonPayloadCodecTest.allFourLoginResponseFieldsMustBePresent`.

**Example 2.7a**

```json
{
  "status": true,
  "session_id": "s",
  "user_id": 1
}
```

**Output 2.7b**

`IOException` vì thiếu key `reason`. Theo contract đang kiểm thử, phải có `"reason": null` thay vì bỏ key này.

---

## JSON payload

### 3.1. UserListRequest từ chối session null

Test gốc: `JsonPayloadCodecTest.otherPayloadStillRejectsNullSession`.

**Example 3.1a**

Decode thành `UserListRequest`:

```json
{
  "session_id": null
}
```

**Output 3.1b**

`IOException`. Việc cho phép null trong LoginResponse không được làm UserListRequest chấp nhận session null.

---

### 3.2. Heartbeat từ chối session null

Test gốc: `JsonPayloadCodecTest.heartbeatStillRejectsNullSession`.

**Example 3.2a**

Decode thành `Heartbeat`:

```json
{
  "sessionID": null,
  "heartbeatSeq": 1
}
```

**Output 3.2b**

`IOException`.

Tên key `sessionID` và `heartbeatSeq` giữ đúng test/model hiện tại.

---

### 3.3. Giới hạn chat được tính bằng UTF-8 bytes

Test gốc: `JsonPayloadCodecTest.chatMeasuresUtf8Bytes`.

**Example 3.3a**

```java
String text = "á".repeat(500);
// A: new ChatMessage(text), sau đó encode/decode.
// B: new ChatMessage(text + "á").
```

**Output 3.3b**

| Biến thể | Kết quả |
| --- | --- |
| A: 500 ký tự `á` = 1.000 UTF-8 bytes | Encode/decode thành công; text giữ nguyên |
| B: 501 ký tự `á` = 1.002 UTF-8 bytes | Constructor ném `IllegalArgumentException` |

---

### 3.4. Giới hạn JSON gồm cả key và ký tự escape

Test gốc: `JsonPayloadCodecTest.serializedJsonLimitIncludesEscapingAndFieldNames`.

**Example 3.4a**

Đo trên JSON compact, không thêm khoảng trắng hoặc xuống dòng.

| Biến thể | Thao tác |
| --- | --- |
| A | Encode `Map.of("x", "a".repeat(1092))`, rồi decode thành Map |
| B | Encode `Map.of("x", "a".repeat(1093))` |
| C | Decode JSON compact có key `x` và giá trị gồm 1.093 ký tự `a` |
| D | Tạo ChatMessage với 600 dấu ngoặc kép (`"`), rồi encode |

**Output 3.4b**

| Biến thể | Kết quả |
| --- | --- |
| A | JSON dài đúng 1.100 bytes; decode giữ nguyên giá trị |
| B | `IOException`: JSON dài 1.101 bytes |
| C | `IOException`: JSON đầu vào vượt 1.100 bytes |
| D | Constructor chấp nhận text; encode ném `IOException` vì JSON sau escape vượt 1.100 bytes |

---

### 3.5. Từ chối JSON sai cấu trúc

Test gốc: `JsonPayloadCodecTest.rejectMalformedDuplicateUnknownAndTrailingJson`.

**Example 3.5a**

Decode từng đầu vào riêng biệt thành `ChatMessage`:

```text
(1) Dãy byte rỗng
(2) []
(3) null
(4) {
(5) {"text":"a","text":"b"}
(6) {"text":"hi","extra":1}
(7) {"text":"hi"} {}
```

**Output 3.5b**

`IOException` cho cả bảy đầu vào: rỗng, sai kiểu, null, JSON chưa hoàn chỉnh, key trùng, key không xác định hoặc có dữ liệu JSON thừa.

---

### 3.6. Từ chối UTF-8 lỗi và ép kiểu số

Test gốc: `JsonPayloadCodecTest.rejectMalformedUtf8AndCoercedNumbers`.

**Example 3.6a**

Biến thể A: decode bytes hex `C3 28` thành ChatMessage.

Các biến thể B–D: decode thành LoginRequest:

```json
{
  "username": "alice",
  "password": "pw",
  "tcp_port": "5001",
  "file_udp_port": 5002
}
```

Thay `tcp_port` lần lượt bằng chuỗi `"5001"`, số thập phân `5001.5`, và `null`.

**Output 3.6b**

`IOException` cho UTF-8 lỗi và cho cả ba giá trị port. Không tự ép chuỗi hoặc số thập phân thành integer.

---

## PacketCodec

Fixture packet chung của phần này và phần TCP:

```text
version = 2
messageType = 0x03 (CHAT_MESSAGE)
flags = 0x1234
streamID = 0x01020304
sequenceNumber = 0x05060708
senderID = 0x11121314
receiverID = 0x21222324
payloadLength = số byte của payload
```

Thứ tự trên wire: version (1) → type (1) → flags (2) → stream ID (4) → sequence (4) → sender ID (4) → receiver ID (4) → payload length (4). Độ dài header là 24 bytes; payload length bắt đầu tại offset 20 (đếm từ 0).

Payload trong các test PacketCodec là byte thô để kiểm tra lớp đóng gói; không bắt buộc là JSON hợp lệ. Ký hiệu hex không tính khoảng trắng thành dữ liệu.

### 4.1. Round trip giữ đủ header và payload nhị phân

Test gốc: `PacketCodecTest.roundTripPreservesEveryFieldAndBinaryPayload`.

**Example 4.1a**

Encode rồi decode fixture với payload:

```text
00 01 7F 80 FF
```

**Output 4.1b**

Tất cả 8 trường header giữ nguyên; `payloadLength = 5`; payload sau decode vẫn là `00 01 7F 80 FF`.

---

### 4.2. Đối chiếu header big-endian với hex độc lập

Test gốc: `PacketCodecTest.wireMatchesIndependent24ByteBigEndianExample`.

**Example 4.2a**

Fixture với payload ASCII `abc` (`61 62 63`); encode packet và decode chuỗi hex chuẩn dưới đây.

**Output 4.2b**

```text
02 03 12 34 01 02 03 04 05 06 07 08
11 12 13 14 21 22 23 24 00 00 00 03
61 62 63
```

Encode phải khớp từng byte. Header = 24 bytes; tổng packet = 27 bytes. Decode hex chuẩn phải phục hồi đầy đủ fixture và payload `abc`.

---

### 4.3. Payload rỗng

Test gốc: `PacketCodecTest.zeroLengthPayloadRoundTrip`.

**Example 4.3a**

Encode/decode fixture với `new byte[0]`.

**Output 4.3b**

`payloadLength = 0`; packet dài đúng 24 bytes; mọi trường header giữ nguyên và payload giải mã rỗng.

---

### 4.4. Biên kích thước packet

Test gốc: `PacketCodecTest.packetSizeBoundary`.

**Example 4.4a**

| Biến thể | Đầu vào |
| --- | --- |
| A | Encode/decode fixture với 1.176 byte zero |
| B | Encode fixture với 1.177 byte zero |
| C | Decode mảng 1.201 byte zero |

**Output 4.4b**

| Biến thể | Kết quả |
| --- | --- |
| A | Thành công: 24 + 1.176 = 1.200 bytes; payload giải mã dài 1.176 |
| B | `IllegalArgumentException` |
| C | `IllegalArgumentException` |

Giới hạn envelope 1.200 bytes được kiểm tra riêng với giới hạn JSON payload 1.100 bytes.

---

### 4.5. Null và header chưa đủ

Test gốc: `PacketCodecTest.rejectNullAndIncompleteHeader`.

**Example 4.5a**

```java
PacketCodec.encode(null)
PacketCodec.decode(null)
PacketCodec.decode(new byte[23])
```

**Output 4.5b**

`IllegalArgumentException` cho cả ba trường hợp.

---

### 4.6. Header khai báo sai payload length khi encode

Test gốc: `PacketCodecTest.rejectMismatchOnEncode`.

**Example 4.6a**

```java
PacketHeader header = new PacketHeader(2, 3, 0, 1, 1, 99, 1, 2);
Packet packet = new Packet(header, new byte[3]);
PacketCodec.encode(packet);
```

**Output 4.6b**

`IllegalArgumentException`: header khai báo 99 bytes nhưng payload thực tế có 3 bytes.

---

### 4.7. Payload length âm hoặc lệch khi decode

Test gốc: `PacketCodecTest.rejectNegativeOrMismatchedLengthOnDecode`.

**Example 4.7a**

Encode fixture với 3 byte zero. Mỗi lần dùng bản sao mới và sửa integer big-endian tại offset 20 thành `-1`, `2` hoặc `4`, rồi decode.

**Output 4.7b**

`IllegalArgumentException` cho cả ba biến thể. Payload thực tế vẫn dài 3 bytes.

---

### 4.8. Version và message type không hỗ trợ

Test gốc: `PacketCodecTest.rejectUnknownVersionAndMessageType`.

**Example 4.8a**

| Biến thể | Thao tác |
| --- | --- |
| A | Fixture payload rỗng: sửa byte 0 thành `99`, rồi decode |
| B | Fixture payload rỗng: sửa byte 1 thành `0x09`, rồi decode |
| C | Encode header version `99`, type `0x03`; các trường còn lại bằng 0 và payload rỗng |
| D | Encode header version `2`, type `0x09`; các trường còn lại bằng 0 và payload rỗng |

**Output 4.8b**

`IllegalArgumentException` cho cả bốn biến thể. Type `0x09` không hợp lệ trong registry đang được kiểm thử.

---

### 4.9. Biên unsigned flags 16-bit

Test gốc: `PacketCodecTest.unsignedFlagsBoundary`.

**Example 4.9a**

Header version `2`, type `0x03`, payload rỗng, các trường ngoài flags bằng 0. Thử flags `0`, `65535`, `-1`, `65536`.

**Output 4.9b**

| Flags | Kết quả |
| --- | --- |
| `0` | Encode/decode giữ nguyên `0` |
| `65535` | Encode/decode giữ nguyên `65535` |
| `-1` | Encode ném `IllegalArgumentException` |
| `65536` | Encode ném `IllegalArgumentException` |

---

### 4.10. Packet sao chép payload để bảo vệ dữ liệu

Test gốc: `PacketCodecTest.packetDefensivelyCopiesPayload`.

**Example 4.10a**

```java
byte[] original = {1, 2, 3};
Packet p = packet(original); // fixture chung
original[0] = 9;
p.getPayload()[1] = 9;
```

**Output 4.10b**

```text
p.getPayload() = [1, 2, 3]
```

Sửa mảng đầu vào hoặc mảng getter trả về không làm thay đổi payload lưu trong Packet.

---

## TCP PacketIO

Các packet dùng fixture ở mục PacketCodec. `readPacket` phải đọc đủ một packet theo header và payload length, dù TCP chia/gộp dữ liệu tùy ý.

### 5.1. Một packet bị chia thành nhiều lần đọc

Test gốc: `PacketIOTest.packetSplitIntoManySmallReads`.

**Example 5.1a**

Encode fixture với payload `[1, 2, 3, 4, 5, 6, 7]`. Dùng ShortReadStream giới hạn mỗi lần đọc tối đa lần lượt `1`, `2`, `5`, `7` bytes; mỗi giới hạn dùng stream mới.

**Output 5.1b**

Ở cả bốn biến thể:

- Lần `readPacket` đầu phục hồi đúng toàn bộ header và payload.
- Có hơn 2 lần gọi đọc theo mảng byte.
- Lần `readPacket` kế tiếp trả `null` vì đã hết stream.

---

### 5.2. Nhiều packet nối tiếp trong một stream

Test gốc: `PacketIOTest.severalPacketsInOneStreamRemainSeparate`.

**Example 5.2a**

Ghi liên tiếp ba fixture vào cùng stream:

```text
Packet 1: payload [1, 2]
Packet 2: payload []
Packet 3: payload [9, 8, 7]
```

Đọc bằng stream thông thường, sau đó lặp lại với ShortReadStream tối đa 3 bytes mỗi lần đọc.

**Output 5.2b**

Ở cả hai kiểu stream:

```text
readPacket #1 → Packet 1
readPacket #2 → Packet 2
readPacket #3 → Packet 3
readPacket #4 → null
```

Mọi header/payload giữ nguyên; không gộp nhầm hoặc mất ranh giới packet.

---

### 5.3. EOF trước khi bắt đầu packet

Test gốc: `PacketIOTest.cleanEofReturnsNull`.

**Example 5.3a**

Gọi `readPacket` trên stream rỗng.

**Output 5.3b**

```text
null
```

Đây là EOF bình thường; không ném exception.

---

### 5.4. EOF giữa header

Test gốc: `PacketIOTest.eofDuringHeaderThrows`.

**Example 5.4a**

Stream chứa 23 byte zero rồi kết thúc. Gọi `readPacket`.

**Output 5.4b**

`EOFException` vì chưa đủ header 24 bytes.

---

### 5.5. EOF giữa payload

Test gốc: `PacketIOTest.eofDuringPayloadThrows`.

**Example 5.5a**

Encode fixture với 3 byte payload: tổng 27 bytes. Cắt bỏ byte cuối, chỉ cung cấp 26 bytes rồi gọi `readPacket`.

**Output 5.5b**

`EOFException` vì header khai báo 3 bytes payload nhưng stream chỉ còn 2 bytes.

---

### 5.6. Payload length bất hợp lệ trong TCP header

Test gốc: `PacketIOTest.badLengthRejectedBeforeReadingPayload`.

**Example 5.6a**

Dùng header fixture payload rỗng; sửa integer tại offset 20 lần lượt thành `-1`, `1177`, `2147483647`. Stream chỉ chứa header.

**Output 5.6b**

`IOException` cho cả ba biến thể. Test yêu cầu các đầu vào này bị từ chối; không tạo packet thành công.

---

### 5.7. Header lỗi được báo qua IOException

Test gốc: `PacketIOTest.malformedHeaderBecomesIOException`.

**Example 5.7a**

Fixture payload rỗng: sửa message type tại byte 1 thành `0x09`; đưa bytes vào `readPacket`.

**Output 5.7b**

`IOException` cho header có message type không hợp lệ.

---

### 5.8. Ghi đầy đủ packet

Test gốc: `PacketIOTest.writesCompletePacket`.

**Example 5.8a**

Gọi `writePacket` để ghi fixture payload `[1, 2, 3]` vào ByteArrayOutputStream.

**Output 5.8b**

Bytes trong output stream phải bằng chính xác `PacketCodec.encode(packet)`, bao gồm đủ 24 bytes header và 3 bytes payload.

---

### 5.9. Echo bằng kết nối TCP loopback thật

Test gốc: `PacketIOTest.realTcpLoopbackEcho`.

**Example 5.9a**

Server thử nghiệm lắng nghe địa chỉ loopback với port `0` để hệ điều hành chọn cổng. Client kết nối cổng được cấp và gửi fixture có payload hex `00 01 FF`. Server đọc một packet, ghi trả packet đó rồi đóng kết nối.

Timeout: accept/connect/read 3 giây; chờ server task tối đa 5 giây; giới hạn cả test 10 giây.

**Output 5.9b**

Client nhận packet có đủ 8 trường header và payload giống packet gửi. Lần đọc kế tiếp trả `null` sau khi server đóng kết nối. Server task hoàn tất, sockets được đóng.

Đây là echo server dùng trong test; không kiểm tra login hoặc server ứng dụng của nhóm.

---

## FileChunkCodec

Dữ liệu đưa vào FileChunkCodec gồm metadata 12 bytes: file ID (4) → chunk order (4) → data length (4), sau đó là data. Các kích thước dưới đây chưa cộng common packet header 24 bytes.

### 6.1. Đối chiếu metadata 12 bytes với hex chuẩn

Test gốc: `FileChunkCodecTest.wireMatches12ByteMetadataExample`.

**Example 6.1a**

```text
File_ID = 42
Chunk_Order = 7
Payload_Length = 3
Payload_Data = abc (hex 61 62 63)
```

Encode chunk; đồng thời decode hex chuẩn ở output.

**Output 6.1b**

```text
00 00 00 2A 00 00 00 07 00 00 00 03
61 62 63
```

Encode khớp từng byte, tổng 15 bytes. Decode cho file ID `42`, chunk order `7`, data length `3`, data `abc`.

---

### 6.2. Round trip tại các biên kích thước chunk

Test gốc: `FileChunkCodecTest.roundTripsBoundarySizes`.

**Example 6.2a**

Với mỗi kích thước `0`, `1`, `1024`, tạo mảng data và điền bằng `new Random(42).nextBytes(data)`. Tạo FileChunk có file ID `42`, chunk order `7`, rồi encode/decode.

**Output 6.2b**

| Data length | Tổng bytes chunk |
| ---: | ---: |
| 0 | 12 |
| 1 | 13 |
| 1024 | 1036 |

Mọi trường metadata và toàn bộ data giữ nguyên sau decode.

---

### 6.3. Từ chối chunk thiếu hoặc vượt kích thước

Test gốc: `FileChunkCodecTest.rejectsBadLengthAndOversize`.

**Example 6.3a**

| Biến thể | Thao tác |
| --- | --- |
| A | Decode 11 byte zero: chưa đủ metadata |
| B | Decode 1.037 byte zero: vượt 12 + 1.024 bytes |
| C | Tạo FileChunk file ID 42, order 0, data dài 1.025 bytes |
| D | Decode metadata file ID 42, order 0, length `-1`, không có data |
| E | Decode metadata file ID 42, order 0, length `3`, không có data |
| F | Decode metadata file ID 42, order 0, length `1025`, không có data |

**Output 6.3b**

`IllegalArgumentException` cho cả sáu biến thể.

---

### 6.4. Từ chối chunk order âm ở cả hai đường

Test gốc: `FileChunkCodecTest.rejectsNegativeChunkOrderOnBothPaths`.

**Example 6.4a**

Biến thể A: `new FileChunk(42, -1, new byte[0])`.

Biến thể B: decode bytes:

```text
00 00 00 2A FF FF FF FF 00 00 00 00
```

**Output 6.4b**

`IllegalArgumentException` ở cả constructor và decoder.

---
