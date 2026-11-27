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

BUFFER_SIZE_FOR_EACH_FILE = 10 * ProtocolConstants.MAX_JSON_PAYLOAD_SIZE # Đơn vị Byte

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
    chunk_buffer: dict[int, bytes] = field(default_factory=dict)
    last_byte_read: int = 0
    finished: bool = False
    sending_started: bool = False
    receive_connection: socket.socket | None = None
    receive_stream: int = 0

    def add_chunk(self, chunk_data: bytes) -> None:
        self.file_io.write_chunk(chunk_data)

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

        self.lock = threading.RLock()

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
                        self._receive_file_request(packet, connection)

                    elif header.getMessageType() == MessageType.FILE_ACCEPTED:
                        try:
                            response: FileAccept = JsonPayloadCodec.decode(packet.getPayload(), FileAccept)
                        except (ValueError, TypeError): continue

                        threading.Thread(target=self.file_transmission, name="peer-file-sending", daemon=True, args=(header.getSenderID(), response.file_id, response.buffer_size)).start()

                    elif header.getMessageType() == MessageType.FILE_REJECTED:
                        try:
                            response: FileReject = JsonPayloadCodec.decode(packet.getPayload(), FileReject)
                        except (ValueError, TypeError): continue

                        with self.lock:
                            transfer_session = self.active_transfer.get(response.file_id)
                            if transfer_session is None or transfer_session.peer_id != header.senderID:
                                continue
                            transfer_session.finished = True
                            transfer_session.pending_chunks.clear()
                            transfer_session.file_io.close_source()

                        self.client.listener.display_error(response.error_code, response.error_message)

                    elif header.getMessageType() == MessageType.FILE_DONE:
                        try:
                            response: FileDone = JsonPayloadCodec.decode(packet.getPayload(), FileDone)
                        except (ValueError, TypeError): continue

                        with self.lock:
                            transfer_session = self.active_transfer.get(response.file_id)
                            if transfer_session is None or transfer_session.peer_id != header.senderID:
                                continue
                            transfer_session.finished = True
                            transfer_session.pending_chunks.clear()
                            transfer_session.file_io.close_source()

                    elif header.getMessageType() == MessageType.ERROR_FILE:
                        try:
                            response: ErrorFile = JsonPayloadCodec.decode(packet.getPayload(), ErrorFile)
                        except (ValueError, TypeError): continue

                        with self.lock:
                            transfer_session = self.active_transfer.get(response.file_id)
                            if transfer_session is None or transfer_session.peer_id != header.senderID:
                                continue
                            transfer_session.finished = True
                            transfer_session.pending_chunks.clear()
                            transfer_session.file_io.close_source()

                        self.client.listener.display_error(response.error_code, response.error_message)

            except (OSError, EOFError) as error:
                if self.client.get_running():
                    print(f"TCP error: {error}")
            finally:
                with self.lock:
                    for session in self.active_transfer.values():
                        if session.receive_connection is connection:
                            session.file_io.close_destination()
                            session.finished = True
                            session.chunk_buffer.clear()
                self.connection.remove_peer_connection(connection)

    def _receive_file_request(self, packet, connection):
        header = packet.header
        if header.receiverID != self.client.id:
            return
        try:
            request = JsonPayloadCodec.decode(packet.payload, FileReq)
        except (ValueError, TypeError):
            return

        chunk_size = ProtocolConstants.MAX_CHUNK_DATA_SIZE
        expected_chunks = (request.file_size + chunk_size - 1) // chunk_size
        name = request.file_name
        with self.lock:
            if (request.file_id in self.active_transfer
                    or request.total_chunks != expected_chunks
                    or name in (".", "..")
                    or "/" in name or "\\" in name or ":" in name):
                response = self.create_file_reject_packet(
                    header.senderID, request.file_id, ErrorCode(1003, "Invalid file request"))
                PacketIO.writePacket(connection, response)
                return

            file_io = FileIO()
            try:
                file_io.open_destination(self.destination_path / name)
            except (OSError, ValueError):
                response = self.create_file_reject_packet(
                    header.senderID, request.file_id,
                    ErrorCode(3004, "Cannot create destination; check folder or existing filename"))
                PacketIO.writePacket(connection, response)
                return

            file_io.file_name = name
            file_io.file_size = request.file_size
            file_io.file_checksum = request.checksum
            session = TransferSession(
                request.file_id, header.senderID,
                (connection.getpeername()[0], request.sender_udp_port),
                file_io, request.file_size, request.total_chunks, request.checksum,
                receive_connection=connection, receive_stream=header.streamID)
            self.active_transfer[request.file_id] = session
            try:
                if request.file_size == 0:
                    self._finish_receiving(session)
                else:
                    response = self.create_file_accept_packet(
                        header.senderID, request.file_id, BUFFER_SIZE_FOR_EACH_FILE)
                    PacketIO.writePacket(connection, response)
            except OSError:
                file_io.close_destination()
                session.finished = True
                raise

    def _finish_receiving(self, session):
        try:
            if session.file_io.verify_checksum(session.checksum):
                response = self.create_file_done_packet(session.peer_id, session.file_id)
            else:
                response = self.create_file_error_packet(
                    session.peer_id, session.file_id, 3002, "File hash mismatch")
        except OSError:
            response = self.create_file_error_packet(
                session.peer_id, session.file_id, 3004, "File verification failed")
        finally:
            session.finished = True
            session.file_io.close_destination()
        PacketIO.writePacket(session.receive_connection, response)

    def _receive_file_chunk(self, packet, source):
        try:
            chunk = FileChunkCodec.decode(packet.payload)
        except (ValueError, TypeError):
            return
        header = packet.header
        with self.lock:
            session = self.active_transfer.get(chunk.file_id)
            if session is None or session.receive_connection is None:
                return
            if (source != session.peer_udp_address or header.senderID != session.peer_id
                    or header.receiverID != self.client.id
                    or header.streamID != session.receive_stream):
                return

            data = chunk.payload_data
            sequence = header.sequenceNumber
            chunk_size = ProtocolConstants.MAX_CHUNK_DATA_SIZE
            start = sequence * chunk_size
            if start >= session.file_size:
                return
            if len(data) != min(chunk_size, session.file_size - start):
                return

            if start >= session.last_byte_read:
                if session.finished:
                    return
                if start + len(data) > session.last_byte_read + BUFFER_SIZE_FOR_EACH_FILE:
                    return
                if sequence not in session.chunk_buffer:
                    session.chunk_buffer[sequence] = data
                try:
                    while session.last_byte_read < session.file_size:
                        next_sequence = session.last_byte_read // chunk_size
                        if next_sequence not in session.chunk_buffer:
                            break
                        next_data = session.chunk_buffer[next_sequence]
                        session.add_chunk(next_data)
                        del session.chunk_buffer[next_sequence]
                        session.last_byte_read += len(next_data)
                except OSError:
                    session.finished = True
                    session.chunk_buffer.clear()
                    session.file_io.close_destination()
                    response = self.create_file_error_packet(
                        session.peer_id, session.file_id, 3004, "File write failed")
                    PacketIO.writePacket(session.receive_connection, response)
                    return

            ack = self.create_ack_packet(session.peer_id, header.streamID, sequence)
            UdpPacketIO.sendPacket(self.connection.file_udp_socket, source, ack)
            if session.last_byte_read == session.file_size and not session.finished:
                self._finish_receiving(session)

    def file_transmission(self, receiver: int, file_id: str, buffer_size: int) -> None:
        with self.lock:
            session = self.active_transfer[file_id]
            if session.finished or session.sending_started:
                return
            if buffer_size < session.mss:
                session.finished = True
                session.file_io.close_source()
                return
            session.sending_started = True
            session.rwnd = buffer_size
        threading.Thread(target=self.resend_file_chunks, name="resend-file-chunks",
                         daemon=True, args=(file_id,)).start()
        self.track_pending_chunks(file_id, receiver, 0)

    def track_pending_chunks(self, file_id: str, receiver: int, base_chunk_index: int):
        session = self.active_transfer[file_id]
        while self.client.get_running():
            with self.lock:
                if session.finished:
                    return
                for key, chunk in list(session.pending_chunks.items()):
                    if chunk.acked and not chunk.checked:
                        chunk.checked = True
                        if session.cwnd < session.ssthresh:
                            session.cwnd += session.mss
                        else:
                            session.cwnd += max(1, session.mss * session.mss // session.cwnd)
                        if not chunk.resend:
                            self.update_timeout_interval(file_id, chunk)
                    if chunk.acked and chunk.chunk_index == base_chunk_index:
                        base_chunk_index += 1
                        session.pending_chunks.pop(key)
                if base_chunk_index >= session.total_chunk:
                    return
                window = min(session.sr_wnd, session.rwnd // session.mss,
                             session.cwnd // session.mss)
                limit = min(base_chunk_index + window, session.total_chunk)
                while session.seq_num < limit and self.client.get_running():
                    self.send_file_chunk(receiver, file_id)
            time.sleep(0.01)

    def send_file_chunk(self, receiver: int, file_id: str) -> None:
        with self.lock:
            session = self.active_transfer[file_id]
            if session.finished:
                return
            chunk_data = session.file_io.read_chunk()
            packet = self.create_file_chunk_packet(receiver, file_id, chunk_data)
            key = (packet.header.streamID, packet.header.sequenceNumber)
            session.pending_chunks[key] = PendingChunk(
                packet.header.sequenceNumber, packet, time.monotonic())
            UdpPacketIO.sendPacket(self.connection.file_udp_socket, session.peer_udp_address, packet)

    def resend_file_chunks(self, file_id: str) -> None:
        session = self.active_transfer[file_id]
        while self.client.get_running():
            failed = False
            with self.lock:
                if session.finished:
                    return
                if session.seq_num >= session.total_chunk and not session.pending_chunks:
                    return
                now = time.monotonic()
                timeout = self.timeout_transfer[file_id].timeout_interval
                for chunk in session.pending_chunks.values():
                    if chunk.acked or now - chunk.sent_at < timeout:
                        continue
                    if chunk.retries >= 5:
                        session.finished = True
                        failed = True
                        break
                    chunk.resend = True
                    chunk.retries += 1
                    chunk.sent_at = now
                    session.ssthresh = max(session.mss, session.cwnd // 2)
                    session.cwnd = session.mss
                    UdpPacketIO.sendPacket(self.connection.file_udp_socket,
                                          session.peer_udp_address, chunk.packet)
                if failed:
                    session.pending_chunks.clear()
                    session.file_io.close_source()
            if failed:
                self.client.listener.display_error(3003, "Transfer timed out after 5 retries")
                return
            time.sleep(0.01)

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
                    self._receive_file_chunk(packet, source)

                elif header.messageType == MessageType.ACK:
                    response: ACK = JsonPayloadCodec.decode(packet.getPayload(), ACK)
                    if header.receiverID != self.client.id:
                        continue
                    key = (response.get_ack_stream_id(), response.get_ack_seq_num())
                    with self.lock:
                        for session in self.active_transfer.values():
                            if session.finished or session.receive_connection is not None:
                                continue
                            if session.peer_id != header.senderID or session.peer_udp_address != source:
                                continue
                            chunk = session.pending_chunks.get(key)
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

        with self.lock:
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

    def create_file_chunk_packet(self, receiver: int, file_id: str, chunk_data: bytes) -> Packet:
        file_chunk = FileChunk(file_id, chunk_data)
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
