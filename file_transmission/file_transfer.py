import socket
import threading
import time
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

MAX_RETRIES = 10
RETRY_TIMEOUT = 10

@dataclass
class PendingChunk:
    chunk_index: int
    packet: Packet
    last_sent_at: float
    retries: int = 0
    acked: bool = False

@dataclass
class TransferSession:
    file_id: str
    peer_id: int
    peer_udp_address: tuple[str, int]
    file_io: FileIO
    file_size: int
    total_chunk: int
    checksum: str
    state: str
    pending_chunks: dict[tuple[int, int], PendingChunk] = field(default_factory=dict)
    condition: threading.Condition = field(default_factory=threading.Condition)

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
                        try:
                            response: FileReq = JsonPayloadCodec.decode(packet.getPayload(), FileReq)
                        except (ValueError, TypeError): continue

                        with self.lock:
                            if response.file_id in self.active_transfer:
                                file_reject_packet = self.create_file_reject_packet(header.getSenderID(), response.file_id, ErrorCode(1003, "Invalid payload"))
                                PacketIO.writePacket(connection, file_reject_packet)
                            else:
                                file_io = FileIO()

                                try:
                                    file_io.open_destination(self.destination_path / response.file_name)
                                except OSError:
                                    file_reject_packet = self.create_file_reject_packet(header.getSenderID(), response.file_id, ErrorCode(1003, "Invalid payload"))
                                    PacketIO.writePacket(connection, file_reject_packet)
                                    continue

                                file_io.file_name = response.file_name
                                file_io.file_size = response.file_size
                                file_io.file_checksum = response.checksum

                                self.active_transfer[response.file_id] = TransferSession(response.file_id, header.getSenderID(), (connection.getpeername()[0], response.sender_udp_port), file_io, response.file_size, response.total_chunks, response.checksum, "acceptance-pending")

                                try:
                                    file_accept_packet = self.create_file_accept_packet(header.getSenderID(), response.file_id)
                                    PacketIO.writePacket(connection, file_accept_packet)
                                except Exception:
                                    file_io.close_destination()
                                    self.active_transfer.pop(response.file_id)
                                    raise

                                self.active_transfer[response.file_id].state = "sending"

                    elif header.getMessageType() == MessageType.FILE_ACCEPTED:
                        try:
                            response: FileAccept = JsonPayloadCodec.decode(packet.getPayload(), FileAccept)
                        except (ValueError, TypeError): continue

                        transfer_session = self.active_transfer[response.file_id]
                        transfer_session.state = "sending"

                        threading.Thread(target=self.peer_udp_sending, name="peer-file-sending", daemon=True, args=(header.getSenderID(), response.file_id, response.buffer_size)).start()

                    elif header.getMessageType() == MessageType.FILE_REJECTED: pass

                    elif header.getMessageType() == MessageType.FILE_DONE:
                        try:
                            response: FileDone = JsonPayloadCodec.decode(packet.getPayload(), FileDone)
                        except (ValueError, TypeError): continue

                        transfer_session = self.active_transfer[response.file_id]

                        if transfer_session.peer_id == header.getSenderID():
                            with transfer_session.condition:
                                transfer_session.state = "sending done"
                                transfer_session.condition.notify_all()

                            transfer_session.file_io.close_source()

                    elif header.getMessageType() == MessageType.ERROR_FILE: pass

            except (OSError, EOFError) as error:
                if self.client.get_running():
                    print(f"TCP error: {error}")
            finally:
                self.connection.remove_peer_connection(connection)

    def peer_udp_sending(self, receiver: int, file_id: str, buffer_size: int) -> None:
        session = self.active_transfer[file_id]
        base_chunk_index: int = 0
        next_chunk_index: int = 0

        while base_chunk_index < session.total_chunk and session.state == "sending" and self.client.get_running():
            while next_chunk_index < min(base_chunk_index + buffer_size, session.total_chunk):
                chunk_data = session.file_io.read_chunk(next_chunk_index, session.total_chunk)
                file_chunk_packet = self.create_file_chunk_packet(receiver, file_id, next_chunk_index, chunk_data)

                with session.condition:
                    session.pending_chunks[(file_chunk_packet.getHeader().getStreamID(), file_chunk_packet.getHeader().getSequenceNumber())] = PendingChunk(next_chunk_index, file_chunk_packet, time.monotonic())

                UdpPacketIO.sendPacket(self.connection.file_udp_socket, session.peer_udp_address, file_chunk_packet)

                next_chunk_index += 1

            with session.condition:
                while True:
                    base_key = next((
                        key
                        for key, pending_chunk in session.pending_chunks.items()
                        if pending_chunk.chunk_index == base_chunk_index
                    ), None)

                    if base_key is None or not session.pending_chunks[base_key].acked:
                        break

                    session.pending_chunks.pop(base_key)
                    base_chunk_index += 1

                if base_chunk_index == session.total_chunk: break
                if next_chunk_index < min(base_chunk_index + buffer_size, session.total_chunk): continue

                earliest_send_time = min(
                    chunk.last_sent_at + RETRY_TIMEOUT
                    for chunk in session.pending_chunks.values()
                    if not chunk.acked
                )

                remaining_wait_time = earliest_send_time - time.monotonic()

                if remaining_wait_time > 0:
                    session.condition.wait(timeout=remaining_wait_time)

                while True:
                    base_key = next((
                        key
                        for key, pending_chunk in session.pending_chunks.items()
                        if pending_chunk.chunk_index == base_chunk_index
                    ), None)

                    if base_key is None or not session.pending_chunks[base_key].acked:
                        break

                    session.pending_chunks.pop(base_key)
                    base_chunk_index += 1

            packets_to_resend = []

            with session.condition:
                now = time.monotonic()
                for pending_chunk in session.pending_chunks.values():
                    if pending_chunk.acked == False and time.monotonic() - pending_chunk.last_sent_at > RETRY_TIMEOUT and pending_chunk.retries < MAX_RETRIES:
                        pending_chunk.retries += 1
                        pending_chunk.last_sent_at = now
                        packets_to_resend.append(pending_chunk.packet)

            for packet in packets_to_resend:
                UdpPacketIO.sendPacket(self.connection.file_udp_socket, session.peer_udp_address, packet)

        if base_chunk_index == session.total_chunk:
            session.state = "waiting done"

    def peer_udp_receiving_loop(self):
        while self.client.get_running():
            try:
                received_packet = UdpPacketIO.receivePacket(self.connection.file_udp_socket)
                packet = received_packet.packet
                source = received_packet.source

                if received_packet is None: continue

                header = packet.getHeader()
                if header.getMessageType() == MessageType.FILE_CHUNK:
                    response: FileChunk = FileChunkCodec.decode(packet.getPayload())
                    if self.active_transfer[response.file_id] != source: continue

                elif header.getMessageType() == MessageType.ACK:
                    response: ACK = JsonPayloadCodec.decode(packet.getPayload(), ACK)

                    key = (response.get_ack_stream_id(), response.get_ack_seq_num())
                    for session in self.active_transfer.values():
                        if session.peer_id != header.getSenderID(): continue
                        if session.peer_udp_address != source: continue

                        with session.condition:
                            chunk = session.pending_chunks.get(key, None)
                            if chunk is not None:
                                chunk.acked = True
                                session.condition.notify()
                                break

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

        self.active_transfer[file_id] = TransferSession(file_id, receiver, (peer_ip, peer_udp_port), file_io, file_size, total_chunk, file_checksum, "acceptance-pending")
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