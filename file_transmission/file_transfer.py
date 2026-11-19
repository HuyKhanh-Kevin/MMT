import socket
import threading
from dataclasses import dataclass, field
from pathlib import Path

from common.ErrorCode import ErrorCode
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

BUFFER_SIZE_FOR_EACH_FILE = 3 * 1024 # Đơn vị Byte
@dataclass
class TransferSession:
    file_id: str
    peer_id: int
    peer_udp_address: tuple[str, int]
    file_io: FileIO
    file_size: int
    total_chunk: int
    checksum: str
    chunk_buffer: list[FileChunk | None] = field(
        default_factory=lambda: [None] * (BUFFER_SIZE_FOR_EACH_FILE // ProtocolConstants.MAX_CHUNK_DATA_SIZE)
    )
    curr_chunk_order: int = 0
    def addChunk(self, chunk_index: int, chunk_data: bytes) -> None: 
        self.file_io.write_chunk(chunk_index, self.total_chunk, self.file_size, chunk_data)

class FileTransfer:
    def __init__(self, client: "Client"):
        self.client = client
        self.connection: FileConnection

        self.active_transfer: dict[str, TransferSession] = {}

        self.lock = threading.Lock()

        self.destination_path: Path = Path.home() / "Downloads"

    def set_file_connection(self, connection: FileConnection):
        self.connection = connection
        self.connection.set_file_transfer(self)

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
                        try:
                            response: FileReq = JsonPayloadCodec.decode(packet.getPayload(), FileReq)
                        except (ValueError, TypeError): continue

                        with self.lock:
                            if response.file_id in self.active_transfer:
                                file_reject = self.create_file_reject_packet(header.getSenderID(), response.file_id, ErrorCode(1003, "Invalid payload"))
                                PacketIO.writePacket(connection, file_reject)
                            else:
                                file_io = FileIO()

                                try:
                                    file_io.open_destination(self.destination_path / response.file_name)
                                except OSError:
                                    file_reject = self.create_file_reject_packet(header.getSenderID(), response.file_id, ErrorCode(1003, "Invalid payload"))
                                    PacketIO.writePacket(connection, file_reject)
                                    continue

                                file_io.file_name = response.file_name
                                file_io.file_size = response.file_size
                                file_io.file_checksum = response.checksum

                                self.active_transfer[response.file_id] = TransferSession(response.file_id, header.getSenderID(), (connection.getpeername()[0], response.sender_udp_port), file_io, response.file_size, response.total_chunks, response.checksum)

                                try:
                                    buffer_size = BUFFER_SIZE_FOR_EACH_FILE 
                                    file_acp = self.create_file_accept_packet(header.getSenderID(), response.file_id, buffer_size)
                                    PacketIO.writePacket(connection, file_acp)
                                except Exception:
                                    file_io.close_destination()
                                    self.active_transfer.pop(response.file_id)
                                    raise

                    elif header.getMessageType() == MessageType.FILE_ACCEPTED: pass
                    elif header.getMessageType() == MessageType.FILE_REJECTED: pass
                    elif header.getMessageType() == MessageType.FILE_DONE: 
                        # pass
                        # NOTE: Để tạm để test
                        done_payload: FileDone = JsonPayloadCodec.decode(packet.getPayload(), FileDone)
                        
                        print(f"[TCP receiver] {header.senderID} sent FILE_DONE: {done_payload.file_id}")
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
                if received_packet is None: continue

                packet = received_packet.packet
                source = received_packet.source

                header = packet.getHeader()
                if header.messageType == MessageType.FILE_CHUNK:
                    response: FileChunk = FileChunkCodec.decode(packet.getPayload())
                    session: TransferSession = self.active_transfer[response.file_id]
                    if session.peer_udp_address != source: continue
                    
                    if response.chunk_order == session.curr_chunk_order:
                        session.chunk_buffer[0] = response
                        flushed_count = 0
                        for chunk in session.chunk_buffer:
                            if chunk is not None:
                                session.addChunk(chunk.chunk_order, chunk.payload_data)
                                session.curr_chunk_order += 1
                                flushed_count += 1
                            else:
                                break 
                        session.chunk_buffer = session.chunk_buffer[flushed_count:] + [None] * flushed_count
                    else:
                        session.chunk_buffer[response.chunk_order - session.curr_chunk_order] = response
                    
                    ack = self.create_ack_packet(header.getReceiverID(), header.getStreamID(), header.getSequenceNumber())
                    UdpPacketIO.sendPacket(self.connection.file_udp_socket, source, ack)
                    
                    if(session.curr_chunk_order == session.total_chunk):
                        file_done = self.create_file_done_packet(header.receiverID, session.file_id)
                        PacketIO.writePacket(self.connection.peer_tcp_connections[source[0]], file_done)

                elif header.messageType == MessageType.ACK:
                    response: ACK = JsonPayloadCodec.decode(packet.getPayload(), ACK)
                    # NOTE: Để tạm để test
                    print(f"[UDP receiver] {header.senderID} sent ACK: {response.ack_seq_num}")

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

    def create_file_accept_packet(self, receiver: int, file_id: str, buffer_size: int) -> Packet:
        file_acp = FileAccept(file_id, buffer_size)
        payload = JsonPayloadCodec.encode(file_acp)
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.FILE_ACCEPTED, 0,
                              self.client.get_outgoing_stream(receiver), self.client.next_tcp_sequence(), len(payload),
                              self.client.id, receiver)
        return Packet(header, payload)

    def create_file_reject_packet(self, receiver: int, file_id: str, error: ErrorCode) -> Packet:
        file_reject = FileReject(file_id, error.code, error.message)
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