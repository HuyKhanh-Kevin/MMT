import argparse

from client.client_account import Client
from client.client_console import Console
from file_transmission.file_connection import FileConnection
from file_transmission.file_transfer import FileTransfer


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--server-ip", type=str, required=True)
    parser.add_argument("--server-port", type=int, required=True)
    parser.add_argument("--udp-port", type=int, required=True)

    args = parser.parse_args()

    client = None

    try:
        connection = FileConnection()
        client = Client(args.server_ip, args.server_port, args.udp_port, connection.get_peer_tcp_port(), connection.get_file_udp_port())
        transfer = FileTransfer(client)
        transfer.set_file_connection(connection)
        console = Console(client)
        client.set_listener(console)

        client.start_receiving()
        console.start_sending()
    except (KeyboardInterrupt, EOFError):
        print("Exiting")
    except OSError as error:
        print(f"Connection error: {error}")
    finally:
        if client is not None:
            client.close_connection()

if __name__ == '__main__':
    main()