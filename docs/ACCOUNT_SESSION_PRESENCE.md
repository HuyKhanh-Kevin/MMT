# Account, Session & Presence — phần của Đồng

Bản Python triển khai đăng ký, đăng nhập, đăng xuất, quản lý phiên, danh sách online,
heartbeat và peer discovery. Bảng đối chiếu lý thuyết từng chương trong docs/slide
và wire contract nằm tại [ACCOUNT_PROTOCOL_PYTHON.md](ACCOUNT_PROTOCOL_PYTHON.md).
Cách chạy: [INTEGRATION_ACCOUNT_SESSION.md](INTEGRATION_ACCOUNT_SESSION.md).

## Các thành phần

| File | Trách nhiệm |
| --- | --- |
| server/account_store.py | Validate, PBKDF2, lưu JSON, xác minh mật khẩu |
| server/account_exception.py | Mã lỗi và lý do nghiệp vụ |
| server/session_registry.py | Token, kết nối/endpoint, heartbeat, timeout, presence |
| server/online_directory.py | Snapshot, cursor, phân trang theo byte |
| server/account_request_handler.py | Kiểm tra packet, dispatch, reply/error cùng reference |
| server/tracker_server.py | Socket TCP/UDP, các luồng nhận, quét timeout và phát presence |
| apps/routes/auth_routes.py | Route signup/login/logout qua TCP |
| apps/routes/tracker_routes.py | Route heartbeat/user list qua UDP |
| client/AccountClient.py | API, nhận nền, heartbeat, retry, callback |
| client/Client.py | API client chung, tái sử dụng cùng AccountClient/session/socket |
| client/account_demo.py | CLI demo |
| apps/account_sessions.py | Giữ kết nối tracker cho từng phiên trình duyệt, dọn lease hết hạn |
| apps/routes/account_http_routes.py | API HTTP signup/login/logout/users/session/heartbeat |
| apps/account_http.py | Host HTTP account qua socket TCP trên localhost |
| common/payload/ | DTO account và JSON validation |
| test/server/ | Unit test và integration test socket thật |

Payload snake_case tái sử dụng DTO hiện có để tránh hai bộ model khác nhau.
Riêng module heartbeat được alias trong common/payload/__init__.py vì Windows
không phân biệt Heartbeat.py và heartbeat.py. Import mới
`from common.payload.heartbeat import Heartbeat` và import cũ dùng cùng lớp.
Hai file routes định tuyến **packet**, không phải HTTP endpoints.
HTTP endpoints nằm riêng trong account_http_routes.py. sampleapp.py dùng cùng
backend khi được configure_account_sessions(), không còn trả login thành công giả.

## Cách tổ chức đã rút gọn

- Message type dùng trực tiếp số nguyên trong common.MessageType, không có lớp
  chuyển đổi Enum/chuỗi hex riêng ở client.
- Client xử lý từng request account theo thứ tự. Một hàng đợi nhận reply là đủ;
  không cần hai bảng Future cho TCP và UDP. Reply vẫn được đối chiếu transport
  và sequence. Đóng kết nối đánh thức request đang chờ.
- Server giữ một dictionary session theo token. Với quy mô 10–20 client của đề,
  tìm user/kết nối bằng vòng lặp rõ ràng, không cần đồng bộ thêm hai bảng chỉ mục.
- Luồng cập nhật danh sách chỉ khởi động khi UI đăng ký on_users. Client chỉ dùng
  signup/login/heartbeat không tạo thêm luồng này.
- Snapshot dùng dict thông thường, không cần OrderedDict.

Khóa dữ liệu dùng chung, hash mật khẩu, heartbeat/timeout, retry UDP và phân trang
vẫn cần giữ: chúng giải quyết truy cập đồng thời, xác thực, mất gói và giới hạn
kích thước packet. Đây là lựa chọn triển khai dựa trên lý thuyết, không phải mọi
chi tiết đều phải có nguyên mẫu trong slide. Cầu nối HTTP và các API tương thích
đang có caller/test nên xóa chúng sẽ làm mất chức năng tương ứng.

## Account và lưu trữ

Account tồn tại qua lần khởi động lại; session chỉ tồn tại trong RAM.
Username phân biệt hoa thường, khớp `[A-Za-z0-9_]{1,32}`; password dài 8–128 ký tự
ASCII in được. Đăng ký không tự login. Signup đồng thời một tên chỉ có một bên
thành công.

Password dùng PBKDF2-HMAC-SHA256, salt ngẫu nhiên 16 byte, 210.000 vòng, hash 32 byte;
so sánh bằng hmac.compare_digest. File mặc định data/python_accounts.json lưu
user_id, username, salt, password_hash, iterations; không lưu password gốc/token.
Server ghi file tạm cùng thư mục, flush/fsync, os.replace rồi mới cập nhật RAM.
File lỗi khiến server từ chối khởi động thay vì tự xóa dữ liệu.
Một file chỉ dành cho một tiến trình server. Schema Python khác Java; không có
migration tự động và không giả định tương thích wire giữa hai implementation.

## Session, endpoint và heartbeat

Login tạo token ngẫu nhiên 32 byte, URL-safe 43 ký tự. Mỗi account chỉ online một
phiên. Token gắn với user_id và ID kết nối TCP do server tạo. IP lấy từ socket
TCP; client chỉ khai cổng peer TCP và file UDP (1–65535). Đây là cổng lắng nghe,
khác cổng nguồn TCP tạm và socket UDP điều khiển dùng heartbeat/discovery.

Heartbeat đầu chốt IP/cổng UDP nhận presence. Gói sau phải khớp token, user_id,
IP và cổng; sequence cũ/trùng không gia hạn. Client gửi ngay sau login, định kỳ
5 giây và trước mỗi lần thử discovery để khôi phục heartbeat đầu bị mất.
Riêng packet discovery không gia hạn phiên.

Server dùng time.monotonic. Sau 15 giây không nhận heartbeat mới, session hết
hiệu lực, TCP bị đóng và các client khác nhận offline. Vòng quét chạy mỗi 100 ms;
xác thực từ chối token hết hạn ngay trước lượt quét. EOF/reset TCP cũng dọn phiên.
Cleanup idempotent, không tạo hai sự kiện offline.

Logout phải từ đúng TCP đã login. Logout giữ TCP để login lại với token mới;
token cũ không dùng được. Sau timeout/server disconnect, tạo AccountClient mới.
Đổi IP/cổng cũng cần phiên mới.
Thời gian chờ trước login là 120 giây, tùy chỉnh bằng --login-timeout; đây là
giới hạn khác với hạn heartbeat 15 giây của phiên đã xác thực.

## Discovery và presence

Danh sách bao gồm người yêu cầu, chứa user_id, username, status, IP, hai cổng peer,
không chứa token. Phân trang theo JSON thực tối đa 1.100 byte; packet tối đa 1.200
byte. Cursor thuộc snapshot bất biến của session, TTL 30 giây, tối đa 4 snapshot
mỗi session. Retry cùng reference trang đầu nhận lại cùng nội dung.
Cursor sai/hết hạn/khác session trả ERROR 1003 / INVALID_CURSOR; ứng dụng có thể
gọi lại online_users() để bắt đầu snapshot mới.
Client hiện tự bắt đầu lại toàn bộ snapshot một lần khi nhận INVALID_CURSOR;
nếu tiếp tục lỗi thì báo ra ngoài, không lặp vô hạn hoặc ghép hai snapshot.

Client thử mỗi trang tối đa 3 lần, mỗi lần chờ 1 giây; online_users() trả đủ trang.
Discovery trước heartbeat nhận HEARTBEAT_REQUIRED; client gửi heartbeat rồi thử
lại trong cùng giới hạn. Presence mang username và status online/offline, phát
UDP unicast tới các session khác đã đăng ký endpoint. UDP có thể mất/trễ/đảo thứ
tự; UI nên tải lại danh sách để xác nhận trạng thái.
on_users(callback) thực hiện việc này: tải đủ danh sách khi có presence và mỗi
5 giây, kể cả lúc thông báo UDP bị mất. Logout/mất kết nối xóa danh sách của UI.
Presence chỉ là gợi ý có thay đổi, không được dùng để khẳng định peer nhận được file.

## Lỗi và tích hợp

Signup/login lỗi nghiệp vụ trả status=failed và reason: USERNAME_TAKEN,
INVALID_CREDENTIALS, ALREADY_ONLINE. JSON sai/thiếu/thừa trường, cổng không hợp lệ,
header/transport sai trả ERROR 1003. Token/user/endpoint/TCP sai trả ERROR 1004.
Key optional vẫn hiện diện với giá trị null theo codec Python.
TCP framing sai đóng kết nối; UDP không giải mã được bị loại.
JSON sai trong frame đầy đủ nhận error, kết nối vẫn xử lý request tiếp theo.

Server tích hợp AccountRequestHandler.handle_tcp/handle_udp phải xử lý cả EOF,
expire, đóng TCP hết hạn và phát presence; TrackerServer đã cung cấp vòng đời này.
SessionRegistry.find_online_user(user_id), online_peers() trả bản sao bất biến
không chứa token. AccountClient.peer_endpoint(user_id) lấy endpoint mới hoặc báo
RECIPIENT_OFFLINE. Callback on_presence chạy riêng nên gọi được online_users();
GUI cần chuyển thao tác vẽ về luồng UI.

Client.py kế thừa AccountClient, không có session hoặc heartbeat thứ hai.
API create_*_packet/send_*_packet cho account vẫn dùng được, nhưng send chờ
phản hồi đã đối chiếu; start_receiving() không tạo thêm luồng đọc.
Các callback chat hiện có được phân luồng khỏi phản hồi account, chưa bổ sung
chat routing vào tracker. Các handler chat/file khác vẫn cần dispatcher riêng.

Backend HTTP chạy trên máy peer và giữ TCP/UDP qua nhiều HTTP request. Browser
nhận access_token riêng, không nhận token tracker. Gửi Bearer token ở request
tiếp theo và heartbeat/poll mỗi 5 giây; 15 giây không có hoạt động sẽ đóng client
native để tránh treo online khi đóng trình duyệt. Chỉ công bố cổng listener native
thực trên máy bridge; browser ở máy khác không trở thành peer qua bridge này.

Module hash mật khẩu trên đĩa nhưng chưa mã hóa đường truyền.
Token/IP/cổng không thay thế TLS hay xác thực mật mã. HTTP UI, NAT traversal,
chat, reliable file transfer, BBR/CUBIC và mã hóa payload thuộc phần tích hợp khác.
