import argparse
import getpass
import socket

from client.AccountClient import AccountClient


def display_presence(event):
    print(f"\n[presence] {event.username}: {event.status}")


def main():
    parser = argparse.ArgumentParser(description="Account/session/presence demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--tcp-port", type=int, default=5000)
    parser.add_argument("--udp-port", type=int, default=5000)
    args = parser.parse_args()


    with socket.socket() as peer, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as file:
        peer.bind(("0.0.0.0", 0))
        peer.listen(1)
        file.bind(("0.0.0.0", 0))
        with AccountClient(args.host, args.tcp_port, args.udp_port,
                           peer.getsockname()[1], file.getsockname()[1]) as account:
            account.on_presence(display_presence)
            print("Commands: signup, login, users, endpoint, status, logout, pause, resume, quit")
            try:
                while True:
                    command = input("> ").strip()
                    try:
                        if command in ("signup", "login"):
                            username = input("Username: ").strip()
                            password = getpass.getpass("Password: ")
                            if command == "signup":
                                response = account.signup(username, password)
                            else:
                                response = account.login(username, password)
                            print(response.status, response.reason or "")
                        elif command == "users":
                            for user in account.online_users():
                                print(f"{user.user_id} {user.username} {user.ip} "
                                      f"TCP={user.tcp_port} file UDP={user.file_udp_port}")
                        elif command == "endpoint":
                            print(account.peer_endpoint(int(input("Recipient user_id: "))))
                        elif command == "status":
                            print(f"connected={account.is_connected} online={account.is_authenticated} "
                                  f"user_id={account.user_id}")
                        elif command == "logout":
                            account.logout()
                            print("Logged out; TCP remains connected.")
                        elif command in ("pause", "resume"):
                            account.set_heartbeats_enabled(command == "resume")
                            print("Heartbeat", command)
                        elif command == "quit":
                            break
                        else:
                            print("Commands: signup, login, users, endpoint, status, logout, pause, resume, quit")
                    except (OSError, ValueError, TypeError) as exc:
                        print(f"Request failed: {exc}")
            except (EOFError, KeyboardInterrupt):
                pass
            finally:
                if account.is_authenticated:
                    try:
                        account.logout()
                    except OSError:
                        pass


if __name__ == "__main__":
    main()
