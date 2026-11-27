from client.client_account import Client
from client.client_listener import Listener
from common.payload.UserInfo import UserInfo

class Console(Listener):
    def __init__(self, client: Client):
        self.client = client

    def display_menu(self):
        print("Choose one of the options")
        if not self.client.get_authenticated():
            print("1. Signup")
            print("2. Login")
            print("3. Exit")
        else:
            print("1. Online users list")
            print("2. Private chat")
            print("3. Global chat")
            print("4. Send file")
            print("5. Logout")

    def start_sending(self):
        while self.client.get_running():
            self.display_menu()
            command = input("Choose one of the options: ")
            if not self.client.get_running(): break
            if self.client.get_authenticated():
                if command == "1":
                    self.client.request_user_list()
                elif command == "2":
                    receiver = int(input("Enter receiver ID: "))
                    message = input("Enter message: ")
                    packet = self.client.create_private_message_packet(receiver, message)
                    self.client.send_tcp_packet(packet)
                elif command == "3":
                    message = input("Enter message: ")
                    packet = self.client.create_global_message_packet(message)
                    self.client.send_tcp_packet(packet)
                elif command == "4":
                    receiver = int(input("Enter receiver ID: "))
                    file_path = input("Enter file path: ")
                    peer_ip = input("Enter peer IP: ")
                    peer_udp_port = int(input("Enter peer UDP port: "))
                    file_id_and_packet = self.client.file_transfer.create_file_request_packet(receiver, file_path, peer_ip, peer_udp_port)
                    print("File ID: ", file_id_and_packet[0])
                    self.client.file_transfer.peer_tcp_sending(peer_ip, peer_udp_port, file_id_and_packet[1])
                elif command == "5":
                    packet = self.client.create_logout_packet()
                    self.client.send_tcp_packet(packet)
            else:
                if command == "1":
                    username = input("Enter username: ")
                    password = input("Enter password: ")
                    packet = self.client.create_signup_packet(username, password)
                    self.client.send_tcp_packet(packet)
                elif command == "2":
                    username = input("Enter username: ")
                    password = input("Enter password: ")
                    packet = self.client.create_login_packet(username, password)
                    self.client.send_tcp_packet(packet)
                elif command == "3":
                    self.client.exit_program()

    def display_user_list(self, users: list[UserInfo]) -> None:
        for user in users:
            print(f"Id: {user.user_id} | Username: {user.username} | Status: {user.status} | Ip: {user.ip} | TCP port: {user.tcp_port} | UDP port: {user.file_udp_port}")

    def display_message(self, sender_id, message) -> None:
        print(f"Id: {sender_id} | Message: {message}")

    def display_signup_response(self, status, reason) -> None:
        if status == "success":
            print("Signup successful")
        else: print(f"Signup failed with reason: {reason}")

    def display_login_response(self, status, reason) -> None:
        if status == "success":
            print("Login successful")
        else: print(f"Login failed with reason: {reason}")

    def display_logout_response(self, status) -> None:
        print(f"Logout {status}")

    def display_error(self, code, message) -> None:
        print(f"Code: {code} | Message: {message}")

    def display_presence(self, update) -> None:
        print(f"{update.username}: {update.status}")
