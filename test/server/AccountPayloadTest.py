import json
import unittest

from common.JsonPayloadCodec import JsonPayloadCodec
from common.payload.heartbeat import Heartbeat
from common.payload.presence_update import PresenceUpdate


class AccountPayloadTest(unittest.TestCase):
    def test_heartbeat_wire_and_validation(self):
        payload = Heartbeat("token", 0xFFFFFFFF)
        self.assertEqual({"session_id": "token", "heartbeat_seq": 0xFFFFFFFF},
                         json.loads(JsonPayloadCodec.encode(payload)))
        self.assertEqual(payload, JsonPayloadCodec.decode(JsonPayloadCodec.encode(payload), Heartbeat))
        for token, seq in (("", 1), (" ", 1), (None, 1), ("s", True), ("s", 0), ("s", 0x100000000)):
            with self.assertRaises((ValueError, TypeError)):
                Heartbeat(token, seq)

    def test_presence_carries_status_and_no_secret(self):
        for status in ("online", "offline"):
            payload = PresenceUpdate("alice", status)
            self.assertEqual({"username": "alice", "status": status},
                             json.loads(JsonPayloadCodec.encode(payload)))
            self.assertEqual(payload, JsonPayloadCodec.decode(JsonPayloadCodec.encode(payload), PresenceUpdate))
        with self.assertRaises(ValueError):
            PresenceUpdate("alice", "unknown")
