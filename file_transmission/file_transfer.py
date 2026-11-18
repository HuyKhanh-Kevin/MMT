import socket
import threading
from dataclasses import dataclass
from pathlib import Path

from common.FileChunkCodec import FileChunkCodec
from common.JsonPayloadCodec import JsonPayloadCodec
from common.MessageType import MessageType
from common.Packet import Packet
from common.PacketHeader import PacketHeader
from common.PacketIO import PacketIO
from common.ProtocolConstants import ProtocolConstants
from common.UdpPacketIO import UdpPacketIO
from common.payload import FileID
from common.payload.ErrorFile import ErrorFile
from common.payload.FileAccept import FileAccept
from common.payload.FileChunk import FileChunk
from common.payload.FileDone import FileDone
from common.payload.FileReject import FileReject
from common.payload.FileReq import FileReq
from common.payload.ACK import ACK
from file_transmission.file_connection import FileConnection
from file_transmission.file_io import FileIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from client.client_account import Client

@dataclass
class TransferSession:
    file_id: str
    peer_id: int
    peer_udp_address: tuple[str, int]
    file_io: FileIO
    file_size: int
    total_chunk: int
    checksum: str

class FileTransfer:
    def __init__(self, client: "Client"):
        self.client = client
        self.connection: FileConnection

        self.active_transfer: dict[str, TransferSession] = {}

        self.lock = threading.Lock()

        self.destination_path: Path = Path.home() / "Downloads"

    def set_file_connection(self, connection: FileConnection):
        self.connection = connection

    def peer_tcp_sending(self, peer_ip: str, peer_tcp_port: int, packet: Packet) -> None:
        with self.lock:
            self.connection.connect_peer(peer_ip, peer_tcp_port)
            connection = self.connection.get_peer_tcp_connection(peer_ip)
            if connection is not None:
                PacketIO.writePacket(connection, packet)

    def peer_tcp_receiving_loop(self, connection: socket.socket) -> None:
        if connection is not None:
            try:
                while self.client.get_running():
                    packet = PacketIO.readPacket(connection)

                    if packet is None: break

                    header = packet.getHeader()
                    if header.getMessageType() == MessageType.FILE_REQUEST:
                        response: FileReq = JsonPayloadCodec.decode(packet.getPayload(), FileReq)

                        file_io = FileIO()
                        file_io.open_destination(self.destination_path / response.file_name)
                        file_io.file_name = response.file_name
                        file_io.file_size = response.file_size
                        file_io.file_checksum = response.checksum

                        self.active_transfer[response.file_id] = TransferSession(response.file_id, header.getSenderID(), (connection.getpeername()[0], response.sender_udp_port), file_io, response.file_size, response.total_chunks, response.checksum)

                        file_acp = self.create_file_accept_packet(header.getSenderID(), response.file_id)
                        with self.lock:
                            PacketIO.writePacket(connection, file_acp)

                    elif header.getMessageType() == MessageType.FILE_ACCEPTED: pass
                    elif header.getMessageType() == MessageType.FILE_REJECTED: pass
                    elif header.getMessageType() == MessageType.FILE_DONE: pass
                    elif header.getMessageType() == MessageType.ERROR_FILE: pass

            except (OSError, EOFError) as error:
                if self.client.get_running():
                    print(f"TCP error: {error}")
            finally:
                self.connection.remove_peer_connection(connection)

    def peer_udp_sending(self, peer_ip: str, peer_udp_port: int, packet: Packet) -> None:
        UdpPacketIO.sendPacket(self.connection.file_udp_socket, (peer_ip, peer_udp_port), packet)

    def peer_udp_receiving_loop(self):
        while self.client.get_running():
            try:
                received_packet = UdpPacketIO.receivePacket(self.connection.file_udp_socket)
                packet = received_packet.packet
                source = received_packet.source

                if received_packet is None: continue

                header = packet.getHeader()
                if header.message_type == MessageType.FILE_CHUNK:
                    response: FileChunk = FileChunkCodec.decode(packet.getPayload())
                    if self.active_transfer[response.file_id] != source: continue
                elif header.message_type == MessageType.ACK:
                    response: ACK = JsonPayloadCodec.decode(packet.getPayload(), ACK)

            except socket.timeout:
                continue
            except OSError as error:
                if self.client.get_running():
                    print(f"UDP error: {error}")
                continue

    def create_file_request_packet(self, receiver: int, file_path: str, peer_ip: str, peer_udp_port: int) -> tuple[str, Packet]:
        if not self.client.get_authenticated():
            raise RuntimeError("You must login before sending a file")

        file_io = FileIO()

        try:
            file_io.open_source(file_path)
            file_io.calculate_hash()

            file_id = FileID.new_file_id()
            file_name = file_io.file_name
            file_size = file_io.file_size
            file_checksum = file_io.file_checksum
            total_chunk = (file_size + ProtocolConstants.MAX_CHUNK_DATA_SIZE - 1) // ProtocolConstants.MAX_CHUNK_DATA_SIZE

            file_req = FileReq(file_id, file_name, file_size, total_chunk, file_checksum, self.connection.get_file_udp_port())
            payload = JsonPayloadCodec.encode(file_req)
            header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.FILE_REQUEST, 0,
                                  self.client.get_outgoing_stream(receiver), self.client.next_tcp_sequence(),
                                  len(payload), self.client.id, receiver)
            packet = Packet(header, payload)
        except Exception:
            file_io.close_source()
            raise

        self.active_transfer[file_id] = TransferSession(file_id, receiver, (peer_ip, peer_udp_port), file_io, file_size, total_chunk, file_checksum)
        return file_id, packet

    def create_file_accept_packet(self, receiver: int, file_id: str) -> Packet:
        file_acp = FileAccept(file_id)
        payload = JsonPayloadCodec.encode(file_acp)
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.FILE_ACCEPTED, 0,
                              self.client.get_outgoing_stream(receiver), self.client.next_tcp_sequence(), len(payload),
                              self.client.id, receiver)
        return Packet(header, payload)

    def create_file_reject_packet(self, receiver: int, file_id: str, code: int, message: str) -> Packet:
        file_reject = FileReject(file_id, code, message)
        payload = JsonPayloadCodec.encode(file_reject)
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.FILE_REJECTED, 0,
                              self.client.get_outgoing_stream(receiver), self.client.next_tcp_sequence(), len(payload),
                              self.client.id, receiver)
        return Packet(header, payload)

    def create_file_done_packet(self, receiver: int, file_id: str) -> Packet:
        file_done = FileDone(file_id)
        payload = JsonPayloadCodec.encode(file_done)
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.FILE_DONE, 0,
                              self.client.get_outgoing_stream(receiver), self.client.next_tcp_sequence(), len(payload),
                              self.client.id, receiver)
        return Packet(header, payload)

    def create_file_error_packet(self, receiver: int, file_id: str, code: int, message: str) -> Packet:
        file_error = ErrorFile(file_id, code, message)
        payload = JsonPayloadCodec.encode(file_error)
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.ERROR_FILE, 0,
                              self.client.get_outgoing_stream(receiver), self.client.next_tcp_sequence(), len(payload),
                              self.client.id, receiver)
        return Packet(header, payload)

    def create_file_chunk_packet(self, receiver: int, file_id: str, chunk_index: int, chunk_data: bytes) -> Packet:
        file_chunk = FileChunk(file_id, chunk_index, chunk_data)
        payload = FileChunkCodec.encode(file_chunk)
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.FILE_CHUNK, 1,
                              self.client.get_outgoing_stream(receiver), self.client.next_udp_sequence(), len(payload),
                              self.client.id, receiver)
        return Packet(header, payload)

    def create_ack_packet(self, receiver: int, stream_id: int, seq_num: int) -> Packet:
        ack = ACK(stream_id, seq_num)
        payload = JsonPayloadCodec.encode(ack)
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.ACK, 0,
                              self.client.get_outgoing_stream(receiver), self.client.next_udp_sequence(), len(payload),
                              self.client.id, receiver)
        return Packet(header, payload)