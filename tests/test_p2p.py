"""
tests.test_p2p
~~~~~~~~~~~~~~

Integration tests for Peer-to-Peer (P2P) communication and endpoint models.

Tests cover:
- PeerEndpoint model validation (user IDs, usernames, TCP/UDP socket tuples)
- Direct peer messaging with CHAT_MESSAGE, ACK, and HEARTBEAT
- In-memory socket simulated P2P duplex transmission
- Sequence number progression and stream preservation

Run from project root:
    python -m unittest tests.test_p2p -v
"""

import socket
import unittest

from client.PeerEndpoint import PeerEndpoint
from common.MessageType import MessageType
from common.Packet import Packet
from common.PacketCodec import PacketCodec
from common.PacketHeader import PacketHeader
from common.ProtocolConstants import ProtocolConstants


def _make_p2p_packet(msg_type: int, payload: bytes, seq: int = 1, stream_id: int = 100,
                     sender_id: int = 10, receiver_id: int = 20) -> Packet:
    """Helper: build a P2P packet between two peer endpoints."""
    return Packet(
        PacketHeader(
            ProtocolConstants.PROTOCOL_VERSION,
            msg_type,
            0,             # flags
            stream_id,     # stream_id (distinct stream per P2P session)
            seq,           # sequence_number
            len(payload),
            sender_id,     # peer A
            receiver_id,   # peer B
        ),
        payload,
    )


class TestPeerEndpointValidation(unittest.TestCase):
    """Tests for client.PeerEndpoint data class and validation logic."""

    def test_valid_peer_endpoint_creation(self):
        """A properly formatted PeerEndpoint must initialize without error."""
        peer = PeerEndpoint(
            user_id=101,
            username="alice",
            tcp=("192.168.1.50", 8888),
            file_udp=("192.168.1.50", 9999),
        )
        self.assertEqual(101, peer.user_id)
        self.assertEqual("alice", peer.username)
        self.assertEqual(("192.168.1.50", 8888), peer.tcp)
        self.assertEqual(("192.168.1.50", 9999), peer.file_udp)

    def test_reject_invalid_user_id(self):
        """user_id must be an integer between 1 and 0xFFFFFFFF."""
        for invalid_id in (0, -1, 0x100000000, "101", None):
            with self.subTest(invalid_id=invalid_id):
                with self.assertRaises((ValueError, TypeError)):
                    PeerEndpoint(
                        user_id=invalid_id,
                        username="alice",
                        tcp=("127.0.0.1", 8888),
                        file_udp=("127.0.0.1", 9999),
                    )

    def test_reject_empty_or_non_string_username(self):
        """Username must be a non-empty string."""
        for invalid_name in ("", None, 12345):
            with self.subTest(invalid_name=invalid_name):
                with self.assertRaises((ValueError, TypeError)):
                    PeerEndpoint(
                        user_id=1,
                        username=invalid_name,
                        tcp=("127.0.0.1", 8888),
                        file_udp=("127.0.0.1", 9999),
                    )

    def test_reject_invalid_tcp_address(self):
        """TCP address must be a (str, int) tuple with valid port 1..65535."""
        invalid_addresses = [
            ("127.0.0.1", 0),          # Port 0 invalid
            ("127.0.0.1", 70000),      # Port > 65535
            ("", 8888),                # Empty host
            ("127.0.0.1",),            # Length != 2
            "127.0.0.1:8888",          # Not a tuple
        ]
        for addr in invalid_addresses:
            with self.subTest(addr=addr):
                with self.assertRaises((ValueError, TypeError)):
                    PeerEndpoint(
                        user_id=1,
                        username="bob",
                        tcp=addr,
                        file_udp=("127.0.0.1", 9999),
                    )

    def test_reject_invalid_udp_address(self):
        """UDP address must be a (str, int) tuple with valid port 1..65535."""
        with self.assertRaises((ValueError, TypeError)):
            PeerEndpoint(
                user_id=1,
                username="bob",
                tcp=("127.0.0.1", 8888),
                file_udp=("127.0.0.1", -5),
            )


class TestP2PMessageEncoding(unittest.TestCase):
    """Tests for P2P message types (CHAT_MESSAGE, ACK, HEARTBEAT, PRESENCE)."""

    def test_chat_message_roundtrip(self):
        """Direct peer CHAT_MESSAGE must preserve message text across encode/decode."""
        chat_text = "Hello peer! This is direct streaming chat.".encode("utf-8")
        pkt = _make_p2p_packet(MessageType.CHAT_MESSAGE, chat_text, seq=1)
        encoded = PacketCodec.encode(pkt)
        decoded = PacketCodec.decode(encoded)

        self.assertEqual(MessageType.CHAT_MESSAGE, decoded.getHeader().getMessageType())
        self.assertEqual(chat_text, decoded.getPayload())
        self.assertEqual(1, decoded.getHeader().getSequenceNumber())
        self.assertEqual(10, decoded.getHeader().getSenderID())
        self.assertEqual(20, decoded.getHeader().getReceiverID())

    def test_ack_packet_roundtrip(self):
        """Direct peer ACK message must preserve acknowledged sequence."""
        ack_payload = b'{"ack_seq": 1, "status": "delivered"}'
        pkt = _make_p2p_packet(MessageType.ACK, ack_payload, seq=2)
        decoded = PacketCodec.decode(PacketCodec.encode(pkt))

        self.assertEqual(MessageType.ACK, decoded.getHeader().getMessageType())
        self.assertEqual(ack_payload, decoded.getPayload())

    def test_heartbeat_packet_roundtrip(self):
        """P2P keepalive HEARTBEAT packet must be accepted."""
        pkt = _make_p2p_packet(MessageType.HEARTBEAT, b"", seq=3)
        decoded = PacketCodec.decode(PacketCodec.encode(pkt))

        self.assertEqual(MessageType.HEARTBEAT, decoded.getHeader().getMessageType())
        self.assertEqual(b"", decoded.getPayload())

    def test_presence_update_message_type(self):
        """PRESENCE_UPDATE message type (18) must be recognized."""
        self.assertTrue(MessageType.isValidMessage(MessageType.PRESENCE_UPDATE))
        payload = b'{"user_id": 10, "status": "online"}'
        pkt = _make_p2p_packet(MessageType.PRESENCE_UPDATE, payload)
        decoded = PacketCodec.decode(PacketCodec.encode(pkt))
        self.assertEqual(MessageType.PRESENCE_UPDATE, decoded.getHeader().getMessageType())


class TestP2PSocketDuplexSimulation(unittest.TestCase):
    """Simulates direct socket conversation between two peers."""

    def test_peer_duplex_chat_and_ack(self):
        """Peer A sends CHAT_MESSAGE to Peer B; Peer B replies with ACK."""
        peer_a_sock, peer_b_sock = socket.socketpair()
        with peer_a_sock, peer_b_sock:
            # 1. Peer A sends chat message to Peer B
            msg = _make_p2p_packet(MessageType.CHAT_MESSAGE, b"Hi Peer B", seq=1)
            peer_a_sock.sendall(PacketCodec.encode(msg))

            # 2. Peer B receives and decodes
            raw_data = peer_b_sock.recv(1024)
            received_msg = PacketCodec.decode(raw_data)
            self.assertEqual(b"Hi Peer B", received_msg.getPayload())
            self.assertEqual(1, received_msg.getHeader().getSequenceNumber())

            # 3. Peer B sends ACK back to Peer A
            ack = _make_p2p_packet(
                MessageType.ACK,
                b"ACK:1",
                seq=1,
                sender_id=20,
                receiver_id=10,
            )
            peer_b_sock.sendall(PacketCodec.encode(ack))

            # 4. Peer A receives and validates ACK
            raw_ack = peer_a_sock.recv(1024)
            received_ack = PacketCodec.decode(raw_ack)
            self.assertEqual(MessageType.ACK, received_ack.getHeader().getMessageType())
            self.assertEqual(b"ACK:1", received_ack.getPayload())
            self.assertEqual(20, received_ack.getHeader().getSenderID())
            self.assertEqual(10, received_ack.getHeader().getReceiverID())

    def test_peer_streaming_sequence_order(self):
        """Multiple messages sent across peer socket maintain strict sequence order."""
        sender, receiver = socket.socketpair()
        with sender, receiver:
            messages = [b"stream chunk 1", b"stream chunk 2", b"stream chunk 3"]
            for i, data in enumerate(messages, start=1):
                pkt = _make_p2p_packet(MessageType.CHAT_MESSAGE, data, seq=i)
                sender.sendall(PacketCodec.encode(pkt))

            for expected_seq, expected_data in enumerate(messages, start=1):
                # Header (24) + payload
                expected_len = ProtocolConstants.HEADER_SIZE + len(expected_data)
                raw = receiver.recv(expected_len)
                pkt = PacketCodec.decode(raw)
                self.assertEqual(expected_seq, pkt.getHeader().getSequenceNumber())
                self.assertEqual(expected_data, pkt.getPayload())


if __name__ == "__main__":
    unittest.main()
