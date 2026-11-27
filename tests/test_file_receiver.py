import hashlib
from pathlib import Path
import socket
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

from common.FileChunkCodec import FileChunkCodec
from common.JsonPayloadCodec import JsonPayloadCodec
from common.MessageType import MessageType
from common.Packet import Packet
from common.PacketHeader import PacketHeader
from common.PacketIO import PacketIO
from common.UdpPacketIO import UdpPacketIO
from common.payload.ErrorFile import ErrorFile
from common.payload.FileChunk import FileChunk
from common.payload.FileReq import FileReq
from file_transmission.file_transfer import FileTransfer


class TestFileReceiver(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.client = SimpleNamespace(id=2, get_running=lambda: True,
                                      get_outgoing_stream=lambda receiver: 7)
        self.transfer = FileTransfer(self.client)
        self.transfer.destination_path = self.folder
        self.transfer.connection = SimpleNamespace(file_udp_socket=object())
        self.tcp = Mock()
        self.tcp.getpeername.return_value = ('127.0.0.1', 5000)
        self.source = ('127.0.0.1', 6001)
        self.tcp_send = self.enterContext(patch.object(PacketIO, 'writePacket'))
        self.udp_send = self.enterContext(patch.object(UdpPacketIO, 'sendPacket'))
        self.addCleanup(self.close_files)

    def close_files(self):
        for session in self.transfer.active_transfer.values():
            session.file_io.close_destination()

    def packet(self, kind, payload, sequence=0, sender=1, receiver=2):
        return Packet(PacketHeader(2, kind, int(kind == MessageType.FILE_CHUNK),
                                   7, sequence, len(payload), sender, receiver), payload)

    def request(self, data, name='image.png', checksum=None):
        file_id = str(uuid.uuid4())
        if checksum is None:
            checksum = hashlib.sha256(data).hexdigest()
        request = FileReq(file_id, name, len(data), (len(data) + 1023) // 1024,
                          checksum, self.source[1])
        packet = self.packet(MessageType.FILE_REQUEST, JsonPayloadCodec.encode(request))
        self.transfer._receive_file_request(packet, self.tcp)
        return file_id

    def chunk(self, file_id, data, sequence, source=None, sender=1):
        payload = FileChunkCodec.encode(FileChunk(file_id, data))
        packet = self.packet(MessageType.FILE_CHUNK, payload, sequence, sender)
        self.transfer._receive_file_chunk(packet, source or self.source)

    def response_kind(self):
        return self.tcp_send.call_args.args[1].header.messageType

    def test_reorders_binary_data_and_acknowledges_duplicates(self):
        data = bytes(range(256)) * 10 + b'last bytes'
        file_id = self.request(data)
        self.chunk(file_id, data[1024:2048], 1)
        self.chunk(file_id, data[1024:2048], 1)
        self.chunk(file_id, data[2048:], 2)
        self.assertEqual(MessageType.FILE_ACCEPTED, self.response_kind())
        self.chunk(file_id, data[:1024], 0)
        self.assertEqual(data, (self.folder / 'image.png').read_bytes())
        self.assertEqual(MessageType.FILE_DONE, self.response_kind())
        self.assertEqual(2, self.tcp_send.call_count)
        self.chunk(file_id, data[:1024], 0)
        self.assertEqual(5, self.udp_send.call_count)
        self.assertEqual(2, self.tcp_send.call_count)
        self.assertEqual(data, (self.folder / 'image.png').read_bytes())

    def test_receive_window_moves_across_large_file(self):
        data = bytes(range(256)) * 200
        file_id = self.request(data)
        self.chunk(file_id, data[11264:12288], 11)
        self.udp_send.assert_not_called()
        for sequence, start in enumerate(range(0, len(data), 1024)):
            self.chunk(file_id, data[start:start + 1024], sequence)
        self.assertEqual(data, (self.folder / 'image.png').read_bytes())
        self.assertEqual(MessageType.FILE_DONE, self.response_kind())

    def test_bad_checksum_reports_error_and_closes_file(self):
        file_id = self.request(b'abc')
        self.chunk(file_id, b'xyz', 0)
        response = self.tcp_send.call_args.args[1]
        self.assertEqual(MessageType.ERROR_FILE, response.header.messageType)
        self.assertEqual(3002, JsonPayloadCodec.decode(response.payload, ErrorFile).error_code)
        self.assertIsNone(self.transfer.active_transfer[file_id].file_io.destination)

    def test_empty_file_finishes_without_waiting_for_udp(self):
        self.request(b'')
        self.assertEqual(MessageType.FILE_DONE, self.response_kind())
        self.assertEqual(b'', (self.folder / 'image.png').read_bytes())

    def test_existing_file_and_unsafe_filename_are_rejected(self):
        (self.folder / 'image.png').write_bytes(b'keep this')
        self.request(b'new')
        self.assertEqual(MessageType.FILE_REJECTED, self.response_kind())
        self.assertEqual(b'keep this', (self.folder / 'image.png').read_bytes())
        self.request(b'new', name='../outside.png')
        self.assertEqual(MessageType.FILE_REJECTED, self.response_kind())
        self.assertEqual({}, self.transfer.active_transfer)

    def test_wrong_peer_unknown_file_and_invalid_chunk_are_ignored(self):
        file_id = self.request(b'abc')
        self.chunk(file_id, b'abc', 0, source=('127.0.0.1', 9999))
        self.chunk(file_id, b'abc', 0, sender=3)
        self.chunk(str(uuid.uuid4()), b'abc', 0)
        self.chunk(file_id, b'ab', 0)
        self.chunk(file_id, b'abc', 1)
        self.udp_send.assert_not_called()
        self.assertEqual(0, self.transfer.active_transfer[file_id].last_byte_read)
        self.chunk(file_id, b'abc', 0)
        self.assertEqual(MessageType.FILE_DONE, self.response_kind())

    def test_disk_write_error_is_reported_without_acknowledging_chunk(self):
        file_id = self.request(b'abc')
        session = self.transfer.active_transfer[file_id]
        with patch.object(session.file_io, 'write_chunk', side_effect=OSError('disk full')):
            self.chunk(file_id, b'abc', 0)
        response = self.tcp_send.call_args.args[1]
        self.assertEqual(3004, JsonPayloadCodec.decode(response.payload, ErrorFile).error_code)
        self.udp_send.assert_not_called()
        self.assertIsNone(session.file_io.destination)


class TestFileReceiverSockets(unittest.TestCase):
    def test_tcp_request_udp_chunks_and_tcp_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(('127.0.0.1', 0))
                listener.listen()
                with socket.create_connection(listener.getsockname()) as sender:
                    receiver, _ = listener.accept()
                    with receiver, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_receiver:
                        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_sender:
                            sender.settimeout(2)
                            udp_receiver.bind(('127.0.0.1', 0))
                            udp_receiver.settimeout(0.1)
                            udp_sender.bind(('127.0.0.1', 0))
                            udp_sender.settimeout(2)
                            stopped = threading.Event()
                            client = SimpleNamespace(id=2, get_running=lambda: not stopped.is_set(),
                                                     get_outgoing_stream=lambda peer: 7)
                            transfer = FileTransfer(client)
                            transfer.destination_path = Path(folder)
                            transfer.connection = SimpleNamespace(
                                file_udp_socket=udp_receiver,
                                remove_peer_connection=lambda connection: None)
                            tcp_thread = threading.Thread(target=transfer.peer_tcp_receiving_loop,
                                                          args=(receiver,), daemon=True)
                            udp_thread = threading.Thread(target=transfer.peer_udp_receiving_loop,
                                                          daemon=True)
                            tcp_thread.start()
                            udp_thread.start()
                            try:
                                data = b'\x89PNG\r\n\x1a\n' + bytes(range(256)) * 9
                                file_id = str(uuid.uuid4())
                                request = FileReq(file_id, 'image.png', len(data), 3,
                                                  hashlib.sha256(data).hexdigest(), udp_sender.getsockname()[1])
                                body = JsonPayloadCodec.encode(request)
                                PacketIO.writePacket(sender, Packet(PacketHeader(
                                    2, MessageType.FILE_REQUEST, 0, 7, 0, len(body), 1, 2), body))
                                self.assertEqual(MessageType.FILE_ACCEPTED,
                                                 PacketIO.readPacket(sender).header.messageType)
                                for sequence in (1, 1, 2, 0):
                                    chunk = data[sequence * 1024:(sequence + 1) * 1024]
                                    body = FileChunkCodec.encode(FileChunk(file_id, chunk))
                                    packet = Packet(PacketHeader(2, MessageType.FILE_CHUNK, 1, 7,
                                                                 sequence, len(body), 1, 2), body)
                                    UdpPacketIO.sendPacket(udp_sender, udp_receiver.getsockname(), packet)
                                    self.assertEqual(MessageType.ACK,
                                                     UdpPacketIO.receivePacket(udp_sender).packet.header.messageType)
                                self.assertEqual(MessageType.FILE_DONE,
                                                 PacketIO.readPacket(sender).header.messageType)
                                self.assertEqual(data, (Path(folder) / 'image.png').read_bytes())
                            finally:
                                stopped.set()
                                sender.shutdown(socket.SHUT_RDWR)
                                tcp_thread.join(2)
                                udp_thread.join(2)
