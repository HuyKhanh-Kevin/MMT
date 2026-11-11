import argparse

from client.client_account import Client
from client.client_console import Console


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--server-ip", type=str, required=True)
    parser.add_argument("--server-port", type=int, required=True)
    parser.add_argument("--udp-port", type=int, required=True)
    parser.add_argument("--peer-tcp-port", type=int, required=True)
    parser.add_argument("--file-udp-port", type=int, required=True)

    args = parser.parse_args()

    client = Client(args.server_ip, args.server_port, args.udp_port, args.peer_tcp_port, args.file_udp_port)

    try:
        console = Console(client)
        client.set_listener(console)

        client.start_receiving()
        console.start_sending()
    except (KeyboardInterrupt, EOFError):
        print("Exiting")
    except OSError as error:
        print(f"Connection error: {error}")
    finally:
        client.close_connection()

if __name__ == '__main__':
    main()