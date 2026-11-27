from collections import Counter
from contextlib import ExitStack
import io
from pathlib import Path
import socket
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

from common.JsonPayloadCodec import JsonPayloadCodec
from common.MessageType import MessageType
from common.PacketIO import PacketIO
from common.UdpPacketIO import UdpPacketIO
from common.payload.ACK import ACK
from file_transmission.file_io import FileIO
from file_transmission.file_transfer import FileTransfer, TransferSession, TimeoutPerTransfer


class TestFileSender(unittest.TestCase):
    def transfer_file(self, lose_packets):
        with ExitStack() as stack:
            folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            source = folder / 'source.bin'
            data = bytes(range(256)) * 200 + b'last chunk'
            source.write_bytes(data)
            destination = folder / 'received'
            destination.mkdir()
            listener = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            sender_tcp = stack.enter_context(socket.create_connection(listener.getsockname()))
            receiver_tcp = stack.enter_context(listener.accept()[0])
            sender_udp = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
            receiver_udp = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
            for sock in (sender_udp, receiver_udp):
                sock.bind(('127.0.0.1', 0))
                sock.settimeout(0.1)
            stopped = threading.Event()
            sender_client = SimpleNamespace(id=1, get_running=lambda: not stopped.is_set(),
                                            get_authenticated=lambda: True,
                                            get_outgoing_stream=lambda peer: 7, listener=Mock())
            receiver_client = SimpleNamespace(id=2, get_running=lambda: not stopped.is_set(),
                                              get_outgoing_stream=lambda peer: 7, listener=Mock())
            sender = FileTransfer(sender_client)
            receiver = FileTransfer(receiver_client)
            receiver.destination_path = destination
            sender.connection = SimpleNamespace(file_udp_socket=sender_udp,
                get_file_udp_port=lambda: sender_udp.getsockname()[1], remove_peer_connection=lambda sock: None)
            receiver.connection = SimpleNamespace(file_udp_socket=receiver_udp,
                remove_peer_connection=lambda sock: None)
            errors = []
            stack.enter_context(patch.object(threading, 'excepthook', side_effect=errors.append))
            counts = Counter()
            timestamps = {}
            dropped = set()
            original = UdpPacketIO.sendPacket

            def send(sock, address, packet):
                if packet.header.messageType == MessageType.FILE_CHUNK:
                    sequence = packet.header.sequenceNumber
                    counts[sequence] += 1
                    timestamps.setdefault(sequence, []).append(time.monotonic())
                    if lose_packets and sequence == 3 and 'chunk' not in dropped:
                        dropped.add('chunk')
                        return
                if lose_packets and packet.header.messageType == MessageType.ACK:
                    ack = JsonPayloadCodec.decode(packet.payload, ACK)
                    if ack.ack_seq_num == 0 and 'ack' not in dropped:
                        dropped.add('ack')
                        return
                original(sock, address, packet)

            stack.enter_context(patch.object(UdpPacketIO, 'sendPacket', side_effect=send))
            threads = []
            for transfer, tcp in ((sender, sender_tcp), (receiver, receiver_tcp)):
                threads.append(threading.Thread(target=transfer.peer_tcp_receiving_loop, args=(tcp,), daemon=True))
                threads.append(threading.Thread(target=transfer.peer_udp_receiving_loop, daemon=True))
            for thread in threads:
                thread.start()
            file_id = None
            try:
                file_id, request = sender.create_file_request_packet(
                    2, str(source), '127.0.0.1', receiver_udp.getsockname()[1])
                PacketIO.writePacket(sender_tcp, request)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and not errors:
                    with sender.lock:
                        finished = sender.active_transfer[file_id].finished
                    if finished:
                        break
                    time.sleep(0.01)
                self.assertEqual([], errors)
                self.assertTrue(sender.active_transfer[file_id].finished)
                self.assertEqual(data, (destination / 'source.bin').read_bytes())
                sender_client.listener.display_error.assert_not_called()
                receiver_client.listener.display_error.assert_not_called()
                self.assertFalse(sender.active_transfer[file_id].pending_chunks)
                if lose_packets:
                    self.assertEqual({'ack', 'chunk'}, dropped)
                    self.assertEqual(2, counts[0])
                    self.assertEqual(2, counts[3])
                    self.assertGreaterEqual(timestamps[0][1] - timestamps[0][0], 0.9)
                    self.assertGreaterEqual(timestamps[3][1] - timestamps[3][0], 0.9)
                else:
                    self.assertTrue(all(count == 1 for count in counts.values()))
            finally:
                stopped.set()
                for sock in (sender_tcp, receiver_tcp):
                    sock.shutdown(socket.SHUT_RDWR)
                for thread in threads:
                    thread.join(2)
                for transfer in (sender, receiver):
                    for session in transfer.active_transfer.values():
                        session.file_io.close_source()
                        session.file_io.close_destination()

    def test_normal_transfer_does_not_resend_chunks(self):
        self.transfer_file(False)

    def test_lost_chunk_and_ack_are_retried_after_timeout(self):
        self.transfer_file(True)

    def test_missing_ack_stops_after_five_retries(self):
        client = SimpleNamespace(id=1, get_running=lambda: True,
                                 get_outgoing_stream=lambda peer: 7, listener=Mock())
        transfer = FileTransfer(client)
        transfer.connection = SimpleNamespace(file_udp_socket=object())
        file_io = FileIO()
        file_io.source = io.BytesIO(b'abc')
        file_id = str(uuid.uuid4())
        session = TransferSession(file_id, 2, ('127.0.0.1', 6000), file_io, 3, 1, '')
        transfer.active_transfer[file_id] = session
        transfer.timeout_transfer[file_id] = TimeoutPerTransfer(timeout_interval=0.02)
        with patch.object(UdpPacketIO, 'sendPacket') as send:
            transfer.send_file_chunk(2, file_id)
            worker = threading.Thread(target=transfer.resend_file_chunks, args=(file_id,), daemon=True)
            worker.start()
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(6, send.call_count)
        self.assertTrue(session.finished)
        self.assertIsNone(file_io.source)
        self.assertEqual({}, session.pending_chunks)
        self.assertEqual(3003, client.listener.display_error.call_args.args[0])
