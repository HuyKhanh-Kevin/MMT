# Chạy và tích hợp Account, Session & Presence (Python)

Chạy từ thư mục gốc bằng Python 3.10+; module chỉ cần standard library.
Đã kiểm thử trên Windows với Python 3.12. Nếu python trỏ vào Microsoft Store,
dùng đường dẫn Python đã cài.

## Chạy demo

Terminal server:

```powershell
cd D:\BKU\Project\MMT
python -m server.tracker_server
```

Mặc định 127.0.0.1, TCP 5000 và UDP 5000, file data/python_accounts.json.
Có thể chọn --tcp-port, --udp-port, --accounts. Chỉ một server ghi một file.

Mỗi terminal client:

```powershell
cd D:\BKU\Project\MMT
python -m client.account_demo
```

Gõ signup/login, nhập username và password khi được hỏi.
Trước login, kết nối không hoạt động trong 120 giây sẽ bị đóng; mở lại demo nếu
đã chờ quá lâu. Server giới hạn 64 kết nối TCP đang mở.
Có thể cấu hình thời gian nhập thông tin bằng --login-timeout; hạn heartbeat
sau login vẫn là 15 giây.

| Lệnh | Tác dụng |
| --- | --- |
| signup / login | Nhập tài khoản, gửi request TCP |
| users | Lấy đủ các trang online |
| endpoint | Nhập user_id để tìm TCP/file UDP |
| status | Xem connected, authenticated, user_id |
| logout | Hủy session, giữ TCP |
| pause / resume | Tắt/bật heartbeat để demo timeout |
| quit | Logout nếu còn phiên và đóng socket |

LAN: server dùng --host 0.0.0.0, client dùng --host địa_chỉ_IP_LAN_server.
Mạng/firewall cần cho phép TCP/UDP tương ứng và cổng peer của module chat/file.
Chưa có NAT traversal. CLI chỉ giữ socket peer để công bố cổng thực,
chưa chạy vòng nhận chat/file.

## Nghiệm thu thủ công

1. Mở A/B, signup alice/bob; thử tên trùng và mật khẩu sai.
2. Login cả hai; users thấy hai người, endpoint có đúng IP/cổng.
3. Mở C login alice; nhận ALREADY_ONLINE.
4. B logout: A nhận offline, users không có bob. B login lại: user_id giữ nguyên,
   token mới (kiểm chứng tự động trong test).
5. B pause, chờ khoảng 15 giây: A nhận offline; B status cho thấy mất kết nối.
   Mở lại B để login; resume không hồi sinh phiên đã hết hạn.
6. Đóng đột ngột B: A nhận offline khi server phát hiện EOF/reset.
7. Khởi động lại server: tài khoản cũ vẫn login được, phiên cũ không tồn tại.

## API tích hợp

Bind/listen socket peer trước, truyền cổng thực cho AccountClient:

```python
from client.AccountClient import AccountClient

def display_presence(update):
    print(update.username, update.status)

with AccountClient(server_ip, 5000, 5000,
                   peer_socket.getsockname()[1],
                   file_socket.getsockname()[1]) as account:
    account.on_presence(display_presence)
    result = account.login("alice", "password123")
    if result.status == "success":
        users = account.online_users()
        other = None
        for user in users:
            if user.user_id != account.user_id:
                other = user
                break
        if other is not None:
            endpoint = account.peer_endpoint(other.user_id)
            # Module chat/file dùng endpoint.tcp và endpoint.file_udp.
        account.logout()
```

Ví dụ giả định server_ip, peer_socket, file_socket do module tích hợp cung cấp.
signup() trả SignupResponse, login() trả LoginResponse. Lỗi giao thức/kết nối
phát sinh OSError; discovery timeout phát sinh TimeoutError.
is_connected/is_authenticated cập nhật khi TCP thấy server đóng.
Callback có thể tải lại danh sách; phần vẽ GUI cần đưa về luồng UI.

Client chung dùng `from client.Client import Client`, cùng constructor và API
signup/login/logout/online_users như AccountClient. Các thuộc tính id,
authenticated, running là alias đọc trực tiếp từ cùng trạng thái.
set_listener() tự gửi snapshot đầy đủ đến display_user_list; display_presence
là callback tùy chọn. API create_*_packet/send_*_packet cũ vẫn gọi được nhưng
account send nay chờ reply. Không mở thêm AccountClient để đăng nhập cùng user.

Với UI native, dùng account.on_users(callback) để cập nhật danh sách đầy đủ sau
presence và mỗi 5 giây. UI nhận danh sách rỗng khi logout/đứt TCP. Không tự áp dụng
event online/offline theo thứ tự đến vì UDP có thể đảo thứ tự hoặc mất gói.

## API HTTP account bằng Python

Trên **máy peer**, sau khi module peer mở các listener thật, chạy:

```powershell
python -m apps.account_http --tracker 127.0.0.1 --peer-tcp-port 5001 --file-udp-port 6001
```

Thay 5001/6001 bằng cổng thực. API chỉ bind 127.0.0.1:8081; chọn --http-port,
--tcp-port, --udp-port nếu cần. Lệnh này không tạo listener chat/file thay module
khác. Nó cung cấp backend account, chưa cung cấp trang HTML/JavaScript mới.

| Endpoint | Request | Kết quả |
| --- | --- | --- |
| POST /signup | JSON username,password | status,reason |
| POST /login | JSON username,password | status,access_token,user_id,username |
| GET /session | Authorization: Bearer access_token | Trạng thái phiên |
| GET /users | Bearer token | users đầy đủ, backend đọc hết các trang UDP |
| POST /heartbeat | Bearer token, body rỗng | Gia hạn lease trình duyệt |
| POST /logout | Bearer token, body rỗng | Hủy phiên browser và tracker |

Gửi Content-Type: application/json cho signup/login. API không nhận form-urlencoded
từ trang login.html mẫu cũ. UI cần gọi contract JSON trên; không gửi password vào
URL. access_token là token browser riêng, không phải session_id của tracker.
Gửi heartbeat hoặc request có xác thực mỗi 5 giây; sau 15 giây không có hoạt động,
backend đóng TCP/UDP của browser đó, ngừng heartbeat và dọn presence.

API giữ TCP tracker qua các HTTP request; lỗi login không tạo session. HTTP trả
200 khi thành công, 400 payload sai, 401 phiên không hợp lệ, 409 lỗi nghiệp vụ,
503 tracker không sẵn sàng. Request sai method nhận 405, endpoint lạ nhận 404.
Host/Origin bị giới hạn về localhost cùng cổng, không bật CORS. UI tích hợp cần
cùng origin hoặc mount AccountHttpRoutes vào host của nhóm với chính sách tương
đương; browser ở xa không được công bố cổng qua bridge localhost này.

Để tái sử dụng các route account trong sampleapp:

```python
from apps.account_sessions import AccountSessions
from apps.sampleapp import configure_account_sessions, create_sampleapp

with AccountSessions("127.0.0.1", 5000, 5000, peer_tcp_port, file_udp_port) as sessions:
    configure_account_sessions(sessions)
    try:
        create_sampleapp("127.0.0.1", 8081)
    finally:
        configure_account_sessions(None)
```

peer_tcp_port/file_udp_port là cổng native đã mở. sampleapp chưa cấu hình sẽ trả
ACCOUNT_API_NOT_CONFIGURED, không còn giả lập login thành công. Hook StreapRous
hiện trả bytes JSON; host HTTP account riêng xử lý đầy đủ HTTP status. Phần raw
transport/UI của StreapRous không được viết lại trong thay đổi account này.

## Kiểm thử

Kết quả ngày 16/11/2026 trên Windows/Python 3.12: **152 lượt test, OK, 48,650 giây**,
gồm 46 test trong test/server và 106 lượt từ bộ test chung hiện có.
Bộ MasterIntegrationTest hiện chạy lại một số test integration, nên đây là số
lượt thực thi unittest, không phải 152 tình huống độc lập.
Đã kiểm tra thêm --help của tracker/HTTP account và git diff --check.

Toàn bộ Python test:

```powershell
python -m unittest discover -s test -t . -p "*Test.py" -v
```

Chỉ module account mới:

```powershell
python -m unittest discover -s test/server -t . -p "*Test.py" -v
```

Giữ -t . để test/common không che package common.
Test dùng loopback, cổng tự cấp và thư mục dữ liệu tạm. Test timeout dùng đúng
chu kỳ 5 giây / hạn 15 giây. Sandbox cần cho phép bind/connect localhost.

Phạm vi: payload wire, hash/persistence, ghi file lỗi, signup/login đồng thời,
heartbeat replay, token/user/IP/cổng/TCP, snapshot/cursor/TTL, malformed packet,
disconnect/shutdown, 20 client đồng thời, mất phản hồi discovery, mất heartbeat
đầu, callback gọi discovery và endpoint mở được TCP/gửi UDP 1 KB.
Kiểm thử endpoint chưa thay thế end-to-end truyền file.
13 test tích hợp bổ sung kiểm tra API Client cũ dùng chung session, refresh sau
mất presence, cursor hết hạn, callback không chiếm reply account, browser token
riêng, nhiều HTTP request giữ một phiên, browser ngừng hoạt động, logout/relogin,
tracker disconnect, HTTP framing/origin và hook sampleapp xác thực thật.
Hai test sau khi rút gọn kiểm tra nhiều lời gọi discovery đồng thời trên cùng
client và đóng kết nối lúc đang chờ reply UDP. Toàn bộ 150 lượt test trước đó
được giữ nguyên.
Lần viết lại theo if/elif và vòng lặp for giữ nguyên toàn bộ 152 lượt test;
bao gồm TCP/UDP, 20 client, timeout, discovery, callback và API HTTP.

Đặc tả: [ACCOUNT_PROTOCOL_PYTHON.md](ACCOUNT_PROTOCOL_PYTHON.md).
Giải thích mã: [ACCOUNT_SESSION_PRESENCE.md](ACCOUNT_SESSION_PRESENCE.md).
