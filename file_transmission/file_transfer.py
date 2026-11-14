from dataclasses import dataclass
from uuid import uuid4

from common.FileChunkCodec import FileChunkCodec
from common.JsonPayloadCodec import JsonPayloadCodec
from common.MessageType import MessageType
from common.Packet import Packet
from common.PacketHeader import PacketHeader
from common.ProtocolConstants import ProtocolConstants
from common.payload.ErrorFile import ErrorFile
from common.payload.FileAccept import FileAccept
from common.payload.FileChunk import FileChunk
from common.payload.FileDone import FileDone
from common.payload.FileReject import FileReject
from common.payload.FileReq import FileReq
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

    def set_file_connection(self, connection: FileConnection):
        self.connection = connection

    def create_file_request_packet(self, receiver: int, file_path: str, peer_ip: str, peer_udp_port: int) -> tuple[str, Packet]:
        if not self.client.get_authenticated():
            raise RuntimeError("You must login before sending a file")

        file_io = FileIO()

        try:
            file_io.open_source(file_path)
            file_io.calculate_hash()

            file_id = str(uuid4())
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