
import socket
import threading
import time

from client.client_account import Client
from common.Packet import Packet
from common.PacketHeader import PacketHeader
from common.MessageType import MessageType
from common.JsonPayloadCodec import JsonPayloadCodec
from common.UdpPacketIO import UdpPacketIO
from common.payload.UserInfo import UserInfo
from common.payload.UserListResponse import UserListResponse


class TestListener:
    def display_user_list(self, users):
        print("\n=== ONLINE USERS ===")
        for user in users:
            print(
                f"ID: {user.user_id} | "
                f"Username: {user.username} | "
                f"Status: {user.status}"
            )


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.bind(("127.0.0.1", 0))
    client_socket.settimeout(0.2)

    # Tạo Client để kiểm thử riêng UDP receive loop,
    # không cần mở TCP connection.
    client = Client.__new__(Client)
    client.running = True
    client.udp_socket = client_socket
    client.server_udp_address = server.getsockname()
    client.listener = TestListener()

    # Các biến dùng cho xử lý User List
    client.user_list_users = []
    client.user_list_seen_cursors = set()
    client.user_list_pending = True

    receiver = threading.Thread(
        target=client.udp_receive_loop,
        daemon=True
    )
    receiver.start()

    try:
        # Server giả lập tạo danh sách online
        response = UserListResponse(
            users=[
                UserInfo("Alice", "online", 101, "127.0.0.1", 3001, 3002),
                UserInfo("Bob", "online", 102, "127.0.0.1", 3003, 3004),
            ],
            next_cursor=None
        )

        payload = JsonPayloadCodec.encode(response)

        header = PacketHeader(
            2,
            MessageType.USER_LIST_RESPONSE,
            0,
            0,
            1,
            len(payload),
            0,
            101
        )

        packet = Packet(header, payload)

        # Server gửi response đến Client
        UdpPacketIO.sendPacket(
            server,
            client_socket.getsockname(),
            packet
        )

        time.sleep(0.5)

    finally:
        client.running = False
        receiver.join(timeout=1)
        client_socket.close()
        server.close()


if __name__ == "__main__":
    main()
