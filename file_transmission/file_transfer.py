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

BUFFER_SIZE_FOR_EACH_FILE = 3 * 1024 # Đơn vị Byte

@dataclass
class PendingChunk:
    chunk_index: int
    packet: Packet
    sent_at: float
    retries: int = 0
    resend: bool = False
    checked: bool = False
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
    rwnd: int = 0
    mss: int = ProtocolConstants.MAX_JSON_PAYLOAD_SIZE
    ssthresh: int = 64 * 1024
    cwnd: int = mss
    sr_wnd: int = pow(2, 31)
    seq_num: int = 0
    pending_chunks: dict[tuple[int, int], PendingChunk] = field(default_factory=dict)
    chunk_buffer: list[FileChunk | None] = field(
        default_factory=lambda: [None] * (BUFFER_SIZE_FOR_EACH_FILE // ProtocolConstants.MAX_CHUNK_DATA_SIZE)
    )
    curr_chunk_order: int = 0
    def add_chunk(self, chunk_index: int, chunk_data: bytes) -> None:
        self.file_io.write_chunk(chunk_index, self.total_chunk, self.file_size, chunk_data)

@dataclass
class TimeoutPerTransfer:
    estimated_rtt: float | None = None
    dev_rtt: float | None = None
    timeout_interval: float = 1.0

class FileTransfer:
    def __init__(self, client: "Client"):
        self.client = client
        self.connection: FileConnection

        self.active_transfer: dict[str, TransferSession] = {}
        self.timeout_transfer: dict[str, TimeoutPerTransfer] = {}

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

                                self.active_transfer[response.file_id] = TransferSession(response.file_id, header.getSenderID(), (connection.getpeername()[0], response.sender_udp_port), file_io, response.file_size, response.total_chunks, response.checksum)

                                try:
                                    buffer_size = BUFFER_SIZE_FOR_EACH_FILE 
                                    file_acp = self.create_file_accept_packet(header.getSenderID(), response.file_id, buffer_size)
                                    PacketIO.writePacket(connection, file_acp)
                                except Exception:
                                    file_io.close_destination()
                                    self.active_transfer.pop(response.file_id)
                                    raise

                    elif header.getMessageType() == MessageType.FILE_ACCEPTED:
                        try:
                            response: FileAccept = JsonPayloadCodec.decode(packet.getPayload(), FileAccept)
                        except (ValueError, TypeError): continue

                        threading.Thread(target=self.file_transmission, name="peer-file-sending", daemon=True, args=(header.getSenderID(), response.file_id, response.buffer_size)).start()

                    elif header.getMessageType() == MessageType.FILE_REJECTED:
                        try:
                            response: FileReject = JsonPayloadCodec.decode(packet.getPayload(), FileReject)
                        except (ValueError, TypeError): continue

                        transfer_session = self.active_transfer[response.file_id]
                        transfer_session.file_io.close_source()

                        self.client.listener.display_error(response.error_code, response.error_message)

                    elif header.getMessageType() == MessageType.FILE_DONE:
                        try:
                            response: FileDone = JsonPayloadCodec.decode(packet.getPayload(), FileDone)
                        except (ValueError, TypeError): continue

                        transfer_session = self.active_transfer[response.file_id]
                        transfer_session.file_io.close_source()

                    elif header.getMessageType() == MessageType.ERROR_FILE:
                        try:
                            response: ErrorFile = JsonPayloadCodec.decode(packet.getPayload(), ErrorFile)
                        except (ValueError, TypeError): continue

                        transfer_session = self.active_transfer[response.file_id]
                        transfer_session.file_io.close_source()

                        self.client.listener.display_error(response.error_code, response.error_message)

            except (OSError, EOFError) as error:
                if self.client.get_running():
                    print(f"TCP error: {error}")
            finally:
                self.connection.remove_peer_connection(connection)

    def file_transmission(self, receiver: int, file_id: str, buffer_size: int) -> None:
        session = self.active_transfer[file_id]
        base_chunk_index: int = 0
        next_chunk_index: int = 0
        session.rwnd = buffer_size
        while next_chunk_index < min(base_chunk_index + min(session.sr_wnd, session.rwnd // session.mss, session.cwnd // session.mss), session.total_chunk) and self.client.get_running():
            next_chunk_index = self.send_file_chunk(next_chunk_index, receiver, file_id)
        threading.Thread(target=self.resend_file_chunks, name="resend-file-chunks", daemon=True, args=file_id).start()
        threading.Thread(target=self.track_pending_chunks, name="track-pending-chunks", daemon=True, args=(file_id, receiver, base_chunk_index, next_chunk_index)).start()

    def track_pending_chunks(self, file_id: str, receiver: int, base_chunk_index: int, next_chunk_index: int):
        session = self.active_transfer[file_id]
        while base_chunk_index < session.total_chunk and self.client.get_running():
            for key, chunk in list(session.pending_chunks.items()):
                if chunk.acked and not chunk.resend and not chunk.checked:
                    chunk.checked = True
                    if session.cwnd < session.ssthresh:
                        session.cwnd += session.mss
                    else:
                        session.cwnd += session.mss * (session.mss // session.cwnd)
                    self.update_timeout_interval(file_id, chunk)
                if chunk.acked and chunk.chunk_index == base_chunk_index:
                    base_chunk_index += 1
                    if next_chunk_index < min(base_chunk_index + min(session.sr_wnd, session.rwnd // session.mss, session.cwnd // session.mss), session.total_chunk) and self.client.get_running():
                        next_chunk_index = self.send_file_chunk(next_chunk_index, receiver, file_id)
                    session.pending_chunks.pop(key)

    def send_file_chunk(self, chunk_index: int, receiver: int, file_id: str) -> int:
        session = self.active_transfer[file_id]
        chunk_data = session.file_io.read_chunk(chunk_index, session.total_chunk)
        file_chunk_packet = self.create_file_chunk_packet(receiver, file_id, chunk_index, chunk_data)
        session.pending_chunks[(file_chunk_packet.getHeader().getStreamID(), file_chunk_packet.getHeader().getSequenceNumber())] = PendingChunk(chunk_index, file_chunk_packet, time.monotonic())
        UdpPacketIO.sendPacket(self.connection.file_udp_socket, session.peer_udp_address, file_chunk_packet)
        return chunk_index + 1

    def resend_file_chunks(self, file_id: str) -> None:
        session = self.active_transfer[file_id]
        timeout = self.timeout_transfer[file_id]
        while self.client.get_running():
            while len(session.pending_chunks) > 0:
                packets_to_resend = []
                for chunk in session.pending_chunks.values():
                    if not chunk.acked and chunk.sent_at + timeout.timeout_interval > time.monotonic():
                        chunk.resend = True
                        session.ssthresh = session.cwnd // 2
                        session.cwnd = session.mss
                        packets_to_resend.append(chunk.packet)
                for packet in packets_to_resend:
                    UdpPacketIO.sendPacket(self.connection.file_udp_socket, session.peer_udp_address, packet)

    def update_timeout_interval(self, file_id: str, chunk: PendingChunk) -> None:
        timeout = self.timeout_transfer[file_id]
        sample_rtt = time.monotonic() - chunk.sent_at
        if timeout.dev_rtt is None:
            timeout.dev_rtt = sample_rtt / 2
        else:
            timeout.dev_rtt = (1 - 0.25) * timeout.dev_rtt + 0.25 * abs(sample_rtt - timeout.estimated_rtt)
        if timeout.estimated_rtt is None:
            timeout.estimated_rtt = sample_rtt
        else:
            timeout.estimated_rtt = (1 - 0.125) * timeout.estimated_rtt + 0.125 * sample_rtt
        timeout.timeout_interval = timeout.estimated_rtt + 4 * timeout.dev_rtt
        if timeout.timeout_interval < 1.0:
            timeout.timeout_interval = 1.0

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
                                session.add_chunk(chunk.chunk_order, chunk.payload_data)
                                session.curr_chunk_order += 1
                                flushed_count += 1
                            else:
                                break 
                        session.chunk_buffer = session.chunk_buffer[flushed_count:] + [None] * flushed_count
                    else:
                        session.chunk_buffer[response.chunk_order - session.curr_chunk_order] = response
                    print(f"[UDP receiver] {header.senderID} buffer: {[chunk.chunk_order if chunk is not None else None for chunk in session.chunk_buffer]}")

                    ack = self.create_ack_packet(header.getSenderID(), header.getStreamID(), header.getSequenceNumber())
                    UdpPacketIO.sendPacket(self.connection.file_udp_socket, source, ack)
                    
                    if session.curr_chunk_order == session.total_chunk:
                        file_done = self.create_file_done_packet(header.getSenderID(), session.file_id)
                        PacketIO.writePacket(self.connection.peer_tcp_connections[source[0]], file_done)

                elif header.messageType == MessageType.ACK:
                    response: ACK = JsonPayloadCodec.decode(packet.getPayload(), ACK)
                    # NOTE: Để tạm để test
                    print(f"[UDP receiver] {header.senderID} sent ACK: {response.ack_seq_num}")

                    key = (response.get_ack_stream_id(), response.get_ack_seq_num())
                    for session in self.active_transfer.values():
                        if session.peer_id != header.getSenderID(): continue
                        if session.peer_udp_address != source: continue
                        chunk = session.pending_chunks.get(key, None)
                        if chunk is not None:
                            chunk.acked = True

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
                                  self.client.get_outgoing_stream(receiver), 0,
                                  len(payload), self.client.id, receiver)
            packet = Packet(header, payload)
        except Exception:
            file_io.close_source()
            raise

        self.active_transfer[file_id] = TransferSession(file_id, receiver, (peer_ip, peer_udp_port), file_io, file_size, total_chunk, file_checksum)
        self.timeout_transfer[file_id] = TimeoutPerTransfer()
        return file_id, packet

    def create_file_accept_packet(self, receiver: int, file_id: str, buffer_size: int) -> Packet:
        file_acp = FileAccept(file_id, buffer_size)
        payload = JsonPayloadCodec.encode(file_acp)
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.FILE_ACCEPTED, 0,
                              self.client.get_outgoing_stream(receiver), 0, len(payload),
                              self.client.id, receiver)
        return Packet(header, payload)

    def create_file_reject_packet(self, receiver: int, file_id: str, error: ErrorCode) -> Packet:
        file_reject = FileReject(file_id, error.code, error.message)
        payload = JsonPayloadCodec.encode(file_reject)
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.FILE_REJECTED, 0,
                              self.client.get_outgoing_stream(receiver), 0, len(payload),
                              self.client.id, receiver)
        return Packet(header, payload)

    def create_file_done_packet(self, receiver: int, file_id: str) -> Packet:
        file_done = FileDone(file_id)
        payload = JsonPayloadCodec.encode(file_done)
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.FILE_DONE, 0,
                              self.client.get_outgoing_stream(receiver), 0, len(payload),
                              self.client.id, receiver)
        return Packet(header, payload)

    def create_file_error_packet(self, receiver: int, file_id: str, code: int, message: str) -> Packet:
        file_error = ErrorFile(file_id, code, message)
        payload = JsonPayloadCodec.encode(file_error)
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.ERROR_FILE, 0,
                              self.client.get_outgoing_stream(receiver), 0, len(payload),
                              self.client.id, receiver)
        return Packet(header, payload)

    def create_file_chunk_packet(self, receiver: int, file_id: str, chunk_index: int, chunk_data: bytes) -> Packet:
        file_chunk = FileChunk(file_id, chunk_index, chunk_data)
        payload = FileChunkCodec.encode(file_chunk)
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.FILE_CHUNK, 1,
                              self.client.get_outgoing_stream(receiver), self.next_transfer_session_seq_num(file_id), len(payload),
                              self.client.id, receiver)
        return Packet(header, payload)

    def create_ack_packet(self, receiver: int, stream_id: int, seq_num: int) -> Packet:
        ack = ACK(stream_id, seq_num)
        payload = JsonPayloadCodec.encode(ack)
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.ACK, 0,
                              self.client.get_outgoing_stream(receiver), 0, len(payload),
                              self.client.id, receiver)
        return Packet(header, payload)

    def next_transfer_session_seq_num(self, file_id: str) -> int:
        session = self.active_transfer[file_id]
        value = session.seq_num
        session.seq_num += 1
        return value