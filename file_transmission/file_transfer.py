import threading

from client.client_account import Client
from common.JsonPayloadCodec import JsonPayloadCodec
from common.MessageType import MessageType
from common.Packet import Packet
from common.PacketHeader import PacketHeader
from common.ProtocolConstants import ProtocolConstants
from common.payload.FileReq import FileReq
from file_transmission.file_io import FileIO

class FileTransfer:
    def __init__(self, client: Client):
        self.client = client

        self.file_id_generator = 1
        self.generator_lock = threading.Lock()

        self.active_transfer: dict[int, FileIO] = {}

    def next_file_id(self) -> int:
        with self.generator_lock:
            value = self.file_id_generator
            self.file_id_generator += 1
            return value

    def create_file_request_packet(self, receiver: int, file_path: str) -> Packet:
        file_io = FileIO()

        try:
            file_io.open_source(file_path)
            file_io.calculate_hash()
        except OSError:
            file_io.close_source()

        file_id = self.next_file_id()
        file_name = file_io.file_name
        file_size = file_io.file_size
        file_checksum = file_io.file_checksum
        total_chunk = file_size / ProtocolConstants.MAX_CHUNK_DATA_SIZE - 1

        self.active_transfer[file_id] = file_io

        file_req = FileReq(file_id, file_name, file_size, total_chunk, file_checksum)
        payload = JsonPayloadCodec.encode(file_req)
        header = PacketHeader(int(ProtocolConstants.PROTOCOL_VERSION), MessageType.FILE_REQUEST, 0, self.client.get_outgoing_stream(receiver), self.client.next_tcp_sequence(), len(payload), self.client.id, receiver)
        return Packet(header, payload)

    def create_file_accept_packet(self) -> Packet: pass
    def create_file_reject_packet(self) -> Packet: pass
    def create_file_done_packet(self) -> Packet: pass
    def create_file_error_packet(self) -> Packet: pass
    def create_file_chunk_packet(self) -> Packet: pass