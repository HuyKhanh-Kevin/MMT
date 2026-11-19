"""Tests for control packet construction.

Run from the project root with:
    python -m unittest test.common.ControlPacketsTest -v
"""

import json
import unittest

from common.ControlPackets import ControlPackets
from common.JsonPayloadCodec import JsonPayloadCodec
from common.MessageType import MessageType
from common.ProtocolConstants import ProtocolConstants
from common.payload.LoginRequest import LoginRequest


class ControlPacketsTest(unittest.TestCase):
    def test_create_builds_control_header_and_json_payload(self):
        body = LoginRequest("alice", "password", 5001, 5002)
        packet = ControlPackets.create("0x01", 17, 123, 456, body)

        self.assertEqual(ProtocolConstants.PROTOCOL_VERSION, packet.header.version)
        self.assertEqual(MessageType.LOGIN_REQUEST, packet.header.messageType)
        self.assertEqual(0, packet.header.flags)
        self.assertEqual(0, packet.header.streamID)
        self.assertEqual(17, packet.header.sequenceNumber)
        self.assertEqual(123, packet.header.senderID)
        self.assertEqual(456, packet.header.receiverID)
        self.assertEqual(len(packet.payload), packet.header.payloadLength)
        self.assertEqual(
            json.loads(JsonPayloadCodec.encode(body)),
            json.loads(packet.payload),
        )

    def test_create_accepts_decimal_message_type_string(self):
        packet = ControlPackets.create("12", 1, 0, 0, {"username": "alice"})
        self.assertEqual(MessageType.SIGNUP_REQUEST, packet.header.messageType)

    def test_create_rejects_invalid_message_type_text(self):
        with self.assertRaises(ValueError):
            ControlPackets.create("LOGIN_REQUEST", 1, 0, 0, {"x": 1})

    def test_create_rejects_invalid_header_ranges(self):
        for sequence, sender, receiver in (
            (-1, 0, 0),
            (0x100000000, 0, 0),
            (1, -1, 0),
            (1, 0, 0x100000000),
        ):
            with self.subTest(sequence=sequence, sender=sender, receiver=receiver):
                with self.assertRaises(ValueError):
                    ControlPackets.create("1", sequence, sender, receiver, {"x": 1})

    def test_create_rejects_null_or_non_object_json_payloads(self):
        for body in (None, "text", [1, 2, 3]):
            with self.subTest(body=body):
                with self.assertRaises((TypeError, ValueError)):
                    ControlPackets.create("1", 1, 0, 0, body)


if __name__ == "__main__":
    unittest.main()
