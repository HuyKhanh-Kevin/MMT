"""
tests.test_auth
~~~~~~~~~~~~~~~

Integration tests for authentication-related packet types.

Tests that the protocol handles LOGIN_REQUEST, LOGIN_RESPONSE,
SIGNUP_REQUEST, SIGNUP_RESPONSE, LOGOUT_REQUEST, and LOGOUT_RESPONSE
message types correctly during encode/decode.

Run from project root:
    python -m unittest tests.test_auth -v
"""

import unittest

from common.MessageType import MessageType
from common.Packet import Packet
from common.PacketCodec import PacketCodec
from common.PacketHeader import PacketHeader
from common.ProtocolConstants import ProtocolConstants


def _make_auth_packet(msg_type: int, payload: bytes) -> Packet:
    """Helper: build an auth packet with the given message type and payload."""
    return Packet(
        PacketHeader(
            ProtocolConstants.PROTOCOL_VERSION,
            msg_type,
            0,            # flags
            0,            # stream_id
            1,            # sequence_number
            len(payload),
            1,            # sender_id (client)
            0,            # receiver_id (server)
        ),
        payload,
    )


class TestLoginPacket(unittest.TestCase):
    """Tests for LOGIN_REQUEST (type 1) and LOGIN_RESPONSE (type 2)."""

    def test_login_request_message_type_is_valid(self):
        """LOGIN_REQUEST message type must be accepted by the protocol."""
        self.assertTrue(MessageType.isValidMessage(MessageType.LOGIN_REQUEST))

    def test_login_response_message_type_is_valid(self):
        """LOGIN_RESPONSE message type must be accepted by the protocol."""
        self.assertTrue(MessageType.isValidMessage(MessageType.LOGIN_RESPONSE))

    def test_encode_login_request_succeeds(self):
        """LOGIN_REQUEST packet must encode without error."""
        payload = b'{"username":"alice","password":"pass123"}'
        pkt = _make_auth_packet(MessageType.LOGIN_REQUEST, payload)
        encoded = PacketCodec.encode(pkt)
        self.assertIsInstance(encoded, bytes)
        self.assertEqual(ProtocolConstants.HEADER_SIZE + len(payload), len(encoded))

    def test_roundtrip_login_request(self):
        """LOGIN_REQUEST must survive encode/decode with correct message type."""
        payload = b'{"username":"bob","password":"secret"}'
        pkt = _make_auth_packet(MessageType.LOGIN_REQUEST, payload)
        decoded = PacketCodec.decode(PacketCodec.encode(pkt))
        self.assertEqual(MessageType.LOGIN_REQUEST, decoded.getHeader().getMessageType())
        self.assertEqual(payload, decoded.getPayload())

    def test_roundtrip_login_response(self):
        """LOGIN_RESPONSE must survive encode/decode with correct message type."""
        payload = b'{"status":"ok","user_id":42}'
        pkt = _make_auth_packet(MessageType.LOGIN_RESPONSE, payload)
        decoded = PacketCodec.decode(PacketCodec.encode(pkt))
        self.assertEqual(MessageType.LOGIN_RESPONSE, decoded.getHeader().getMessageType())
        self.assertEqual(payload, decoded.getPayload())


class TestSignupPacket(unittest.TestCase):
    """Tests for SIGNUP_REQUEST (type 12) and SIGNUP_RESPONSE (type 13)."""

    def test_signup_request_message_type_is_valid(self):
        """SIGNUP_REQUEST message type must be recognized."""
        self.assertTrue(MessageType.isValidMessage(MessageType.SIGNUP_REQUEST))

    def test_signup_response_message_type_is_valid(self):
        """SIGNUP_RESPONSE message type must be recognized."""
        self.assertTrue(MessageType.isValidMessage(MessageType.SIGNUP_RESPONSE))

    def test_roundtrip_signup_request(self):
        """SIGNUP_REQUEST must round-trip correctly."""
        payload = b'{"username":"carol","password":"newpass"}'
        pkt = _make_auth_packet(MessageType.SIGNUP_REQUEST, payload)
        decoded = PacketCodec.decode(PacketCodec.encode(pkt))
        self.assertEqual(MessageType.SIGNUP_REQUEST, decoded.getHeader().getMessageType())
        self.assertEqual(payload, decoded.getPayload())

    def test_roundtrip_signup_response(self):
        """SIGNUP_RESPONSE must round-trip correctly."""
        payload = b'{"status":"created"}'
        pkt = _make_auth_packet(MessageType.SIGNUP_RESPONSE, payload)
        decoded = PacketCodec.decode(PacketCodec.encode(pkt))
        self.assertEqual(MessageType.SIGNUP_RESPONSE, decoded.getHeader().getMessageType())
        self.assertEqual(payload, decoded.getPayload())


class TestLogoutPacket(unittest.TestCase):
    """Tests for LOGOUT_REQUEST (type 19) and LOGOUT_RESPONSE (type 20)."""

    def test_logout_request_message_type_is_valid(self):
        """LOGOUT_REQUEST message type must be recognized."""
        self.assertTrue(MessageType.isValidMessage(MessageType.LOGOUT_REQUEST))

    def test_logout_response_message_type_is_valid(self):
        """LOGOUT_RESPONSE message type must be recognized."""
        self.assertTrue(MessageType.isValidMessage(MessageType.LOGOUT_RESPONSE))

    def test_roundtrip_logout_request(self):
        """LOGOUT_REQUEST must round-trip correctly with empty payload."""
        pkt = _make_auth_packet(MessageType.LOGOUT_REQUEST, b"")
        decoded = PacketCodec.decode(PacketCodec.encode(pkt))
        self.assertEqual(MessageType.LOGOUT_REQUEST, decoded.getHeader().getMessageType())
        self.assertEqual(b"", decoded.getPayload())

    def test_roundtrip_logout_response(self):
        """LOGOUT_RESPONSE must round-trip correctly."""
        payload = b'{"status":"ok"}'
        pkt = _make_auth_packet(MessageType.LOGOUT_RESPONSE, payload)
        decoded = PacketCodec.decode(PacketCodec.encode(pkt))
        self.assertEqual(MessageType.LOGOUT_RESPONSE, decoded.getHeader().getMessageType())
        self.assertEqual(payload, decoded.getPayload())


class TestAuthPayloadSecurity(unittest.TestCase):
    """Security-related tests for auth packets."""

    def test_auth_payload_does_not_exceed_max_size(self):
        """Auth payload within limit must encode; oversized must be rejected."""
        # Normal login: well within limit
        small_payload = b'{"username":"user","password":"pass"}'
        pkt = _make_auth_packet(MessageType.LOGIN_REQUEST, small_payload)
        encoded = PacketCodec.encode(pkt)
        self.assertLessEqual(len(encoded), ProtocolConstants.MAX_PACKET_SIZE)

    def test_oversized_auth_payload_is_rejected(self):
        """Auth payload exceeding max size must be rejected by encoder."""
        big_payload = b"x" * (ProtocolConstants.MAX_PACKET_SIZE + 1)
        header = PacketHeader(
            ProtocolConstants.PROTOCOL_VERSION,
            MessageType.LOGIN_REQUEST,
            0, 0, 1, len(big_payload), 1, 0,
        )
        with self.assertRaises((ValueError, TypeError)):
            PacketCodec.encode(Packet(header, big_payload))

    def test_message_type_values_match_expected_constants(self):
        """Auth message type constants must have the expected integer values."""
        self.assertEqual(1, MessageType.LOGIN_REQUEST)
        self.assertEqual(2, MessageType.LOGIN_RESPONSE)
        self.assertEqual(12, MessageType.SIGNUP_REQUEST)
        self.assertEqual(13, MessageType.SIGNUP_RESPONSE)
        self.assertEqual(19, MessageType.LOGOUT_REQUEST)
        self.assertEqual(20, MessageType.LOGOUT_RESPONSE)


if __name__ == "__main__":
    unittest.main()
