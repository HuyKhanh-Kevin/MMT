"""Unit tests for common.JsonPayloadCodec (Python unittest).

Adapted from the supplied Java JsonPayloadCodecTest to the team's Python
LoginResponse contract: status is "success" or "failed" (not a JSON bool).

Contract under test:
- JSON object encoded as strict UTF-8, maximum 1100 encoded bytes.
- LoginResponse has all four keys, including explicit null for conditional fields.
- Typed decoding rejects invalid, duplicate, unknown, missing, and coerced fields.

Run at project root:
    python -m unittest test.common.JsonPayloadCodecTest -v
"""

import json
import unittest

from common.JsonPayloadCodec import JsonPayloadCodec
from common.payload.ChatMessage import ChatMessage
from common.payload.Heartbeat import Heartbeat
from common.payload.LoginRequest import LoginRequest
from common.payload.LoginResponse import LoginResponse
from common.payload.UserListRequest import UserListRequest


# Python codecs typically raise OSError/ValueError/TypeError for invalid input.
# The test asserts that validation happens, without coupling to a single
# exception class as Java's IOException would.
CODEC_ERRORS = (OSError, ValueError, TypeError)
MODEL_ERRORS = (ValueError, TypeError)


class JsonPayloadCodecTest(unittest.TestCase):

    @staticmethod
    def utf8(text: str) -> bytes:
        return text.encode("utf-8")

    @staticmethod
    def login(json_text: str) -> LoginResponse:
        return JsonPayloadCodec.decode(json_text.encode("utf-8"), LoginResponse)

    def test_login_success_round_trip_with_null_reason(self):
        original = LoginResponse(
            status="success",
            session_id="session-test",
            user_id=0xFFFFFFFF,
            reason=None,
        )
        wire = JsonPayloadCodec.encode(original)
        self.assertEqual(
            {"status", "session_id", "user_id", "reason"},
            set(json.loads(wire)),
            "LoginResponse wire JSON must contain all four fields",
        )
        self.assertIsNone(json.loads(wire)["reason"])

        result = JsonPayloadCodec.decode(wire, LoginResponse)
        self.assertEqual("success", result.status)
        self.assertEqual("session-test", result.session_id)
        self.assertEqual(0xFFFFFFFF, result.user_id)
        self.assertIsNone(result.reason)

    def test_login_failure_round_trip_with_null_session_and_user_id(self):
        original = LoginResponse(
            status="failed",
            session_id=None,
            user_id=None,
            reason="Invalid credentials",
        )
        wire = JsonPayloadCodec.encode(original)
        obj = json.loads(wire)
        self.assertEqual(
            {"status", "session_id", "user_id", "reason"}, set(obj)
        )
        self.assertIsNone(obj["session_id"])
        self.assertIsNone(obj["user_id"])

        result = JsonPayloadCodec.decode(wire, LoginResponse)
        self.assertEqual("failed", result.status)
        self.assertIsNone(result.session_id)
        self.assertIsNone(result.user_id)
        self.assertEqual("Invalid credentials", result.reason)

    def test_reject_success_without_session(self):
        with self.assertRaises(CODEC_ERRORS):
            self.login(
                '{"status":"success","session_id":null,'
                '"user_id":1,"reason":null}'
            )

    def test_reject_success_without_valid_user_id(self):
        for user_id in ("null", "0", "-1", "4294967296"):
            with self.subTest(user_id=user_id):
                with self.assertRaises(CODEC_ERRORS):
                    self.login(
                        '{"status":"success","session_id":"s",'
                        f'"user_id":{user_id},"reason":null}}'
                    )

    def test_reject_failure_without_reason(self):
        for reason in ("null", '""', '"   "'):
            with self.subTest(reason=reason):
                with self.assertRaises(CODEC_ERRORS):
                    self.login(
                        '{"status":"failed","session_id":null,'
                        f'"user_id":null,"reason":{reason}}}'
                    )

    def test_reject_missing_or_null_status(self):
        for json_text in (
            '{"session_id":null,"user_id":null,"reason":"bad"}',
            '{"status":null,"session_id":null,"user_id":null,"reason":"bad"}',
        ):
            with self.subTest(json_text=json_text):
                with self.assertRaises(CODEC_ERRORS):
                    self.login(json_text)

    def test_all_four_login_response_fields_must_be_present(self):
        # Same explicit-null contract as the supplied Java test.
        with self.assertRaises(CODEC_ERRORS):
            self.login('{"status":"success","session_id":"s","user_id":1}')

    def test_other_payload_still_rejects_null_session(self):
        with self.assertRaises(CODEC_ERRORS):
            JsonPayloadCodec.decode(
                self.utf8('{"session_id":null,"cursor":null}'),
                UserListRequest,
            )

    def test_heartbeat_still_rejects_null_session(self):
        # Actual snake_case JSON keys are session_id and heartbeat_seq.
        with self.assertRaises(CODEC_ERRORS):
            JsonPayloadCodec.decode(
                self.utf8('{"session_id":null,"heartbeat_seq":1}'),
                Heartbeat,
            )

    def test_login_request_round_trip(self):
        original = LoginRequest("alice", "test-only-password", 5001, 5002)
        result = JsonPayloadCodec.decode(
            JsonPayloadCodec.encode(original), LoginRequest
        )
        self.assertEqual("alice", result.username)
        self.assertEqual("test-only-password", result.password)
        self.assertEqual(5001, result.tcp_port)
        self.assertEqual(5002, result.file_udp_port)

    def test_reject_invalid_username_password_and_ports(self):
        for username in (None, "", "a" * 33, "á"):
            with self.subTest(username=username):
                with self.assertRaises(MODEL_ERRORS):
                    LoginRequest(username, "pw", 5001, 5002)

        for password in (None, ""):
            with self.subTest(password=password):
                with self.assertRaises(MODEL_ERRORS):
                    LoginRequest("alice", password, 5001, 5002)

        for port in (-1, 0, 65536):
            with self.subTest(port=port):
                with self.assertRaises(MODEL_ERRORS):
                    LoginRequest("alice", "pw", port, 5002)
                with self.assertRaises(MODEL_ERRORS):
                    LoginRequest("alice", "pw", 5001, port)

        LoginRequest("alice", "pw", 1, 65535)

    def test_chat_measures_utf8_bytes(self):
        text = "á" * 500  # 500 characters = 1000 UTF-8 bytes
        result = JsonPayloadCodec.decode(
            JsonPayloadCodec.encode(ChatMessage(text)), ChatMessage
        )
        self.assertEqual(text, result.text)
        with self.assertRaises(MODEL_ERRORS):
            ChatMessage(text + "á")

    def test_serialized_json_limit_includes_escaping_and_field_names(self):
        # {"x":"..."} has 8 bytes of syntax (with compact JSON formatting).
        at_limit = JsonPayloadCodec.encode({"x": "a" * 1092})
        self.assertEqual(1100, len(at_limit))
        self.assertEqual(
            "a" * 1092, JsonPayloadCodec.decode(at_limit, dict)["x"]
        )

        with self.assertRaises(CODEC_ERRORS):
            JsonPayloadCodec.encode({"x": "a" * 1093})
        with self.assertRaises(CODEC_ERRORS):
            JsonPayloadCodec.decode(
                self.utf8('{"x":"' + "a" * 1093 + '"}'), dict
            )

        # 600 quote characters become 1200 escaped bytes before field overhead.
        with self.assertRaises(CODEC_ERRORS):
            JsonPayloadCodec.encode(ChatMessage('"' * 600))

    def test_reject_malformed_duplicate_unknown_and_trailing_json(self):
        for json_text in (
            "", "[]", "null", "{",
            '{"text":"a","text":"b"}',
            '{"text":"hi","extra":1}',
            '{"text":"hi"} {}',
        ):
            with self.subTest(json_text=json_text):
                with self.assertRaises(CODEC_ERRORS):
                    JsonPayloadCodec.decode(self.utf8(json_text), ChatMessage)

    def test_reject_malformed_utf8_and_coerced_numbers(self):
        with self.assertRaises(CODEC_ERRORS):
            JsonPayloadCodec.decode(b"\xc3\x28", ChatMessage)

        for port in ('"5001"', "5001.5", "null"):
            with self.subTest(port=port):
                with self.assertRaises(CODEC_ERRORS):
                    JsonPayloadCodec.decode(
                        self.utf8(
                            '{"username":"alice","password":"pw",'
                            f'"tcp_port":{port},"file_udp_port":5002}}'
                        ),
                        LoginRequest,
                    )


if __name__ == "__main__":
    unittest.main()
