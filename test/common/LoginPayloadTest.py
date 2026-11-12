"""Validation and JSON compatibility tests for login payloads.

Run from the project root with:
    python -m unittest test.common.LoginPayloadTest -v
"""

import json
import unittest

from common.JsonPayloadCodec import JsonPayloadCodec
from common.payload.LoginRequest import LoginRequest
from common.payload.LoginResponse import LoginResponse


MODEL_ERRORS = (TypeError, ValueError)
CODEC_ERRORS = (TypeError, ValueError, UnicodeError)


class LoginPayloadTest(unittest.TestCase):
    def test_login_request_accepts_boundary_values(self):
        self.assertEqual("a", LoginRequest("a", "p", 1, 1).username)
        self.assertEqual(
            32,
            len(LoginRequest("a" * 32, "p", 65535, 65535).username),
        )

    def test_login_request_rejects_invalid_username_and_password(self):
        for username in (None, 123, "", "a" * 33, "álîce"):
            with self.subTest(username=username):
                with self.assertRaises(MODEL_ERRORS):
                    LoginRequest(username, "password", 5001, 5002)

        for password in (None, 123, ""):
            with self.subTest(password=password):
                with self.assertRaises(MODEL_ERRORS):
                    LoginRequest("alice", password, 5001, 5002)

    def test_login_request_rejects_invalid_ports(self):
        invalid_ports = (None, "5001", 1.5, True, False, -1, 0, 65536)
        for port in invalid_ports:
            with self.subTest(field="tcp_port", port=port):
                with self.assertRaises(MODEL_ERRORS):
                    LoginRequest("alice", "pw", port, 5002)
            with self.subTest(field="file_udp_port", port=port):
                with self.assertRaises(MODEL_ERRORS):
                    LoginRequest("alice", "pw", 5001, port)

    def test_login_request_json_round_trip_and_port_getters(self):
        original = LoginRequest("alice", "password", 5001, 5002)
        encoded = JsonPayloadCodec.encode(original)
        self.assertEqual(
            {
                "username": "alice",
                "password": "password",
                "tcp_port": 5001,
                "file_udp_port": 5002,
            },
            json.loads(encoded),
        )

        decoded = JsonPayloadCodec.decode(encoded, LoginRequest)
        self.assertEqual(original, decoded)
        self.assertEqual(5001, decoded.get_tcp_port())
        self.assertEqual(5002, decoded.get_file_udp_port())
        self.assertEqual(5002, decoded.get_udp_port())

    def test_login_response_accepts_success_and_failure_contracts(self):
        success = LoginResponse("success", "session-1", 0xFFFFFFFF, None)
        failure = LoginResponse("failed", None, None, "Invalid credentials")

        self.assertTrue(success.is_success)
        self.assertFalse(failure.is_success)
        self.assertEqual(1, LoginResponse("success", "s", 1, None).user_id)

    def test_login_response_rejects_invalid_status_and_field_types(self):
        for status in (None, 1, "SUCCESS", "unknown"):
            with self.subTest(status=status):
                with self.assertRaises(MODEL_ERRORS):
                    LoginResponse(status, "s", 1, None)

        for session_id in (1, ""):
            with self.subTest(session_id=session_id):
                with self.assertRaises(MODEL_ERRORS):
                    LoginResponse("success", session_id, 1, None)

        for user_id in (True, 0, -1, 0x100000000, "1"):
            with self.subTest(user_id=user_id):
                with self.assertRaises(MODEL_ERRORS):
                    LoginResponse("success", "s", user_id, None)

        with self.assertRaises(MODEL_ERRORS):
            LoginResponse("success", "s", 1, "unexpected reason")
        with self.assertRaises(MODEL_ERRORS):
            LoginResponse("failed", "s", None, "failed")
        with self.assertRaises(MODEL_ERRORS):
            LoginResponse("failed", None, 1, "failed")
        for reason in (None, "", "   ", 42):
            with self.subTest(reason=reason):
                with self.assertRaises(MODEL_ERRORS):
                    LoginResponse("failed", None, None, reason)

    def test_login_response_json_round_trip_preserves_explicit_nulls(self):
        cases = (
            LoginResponse("success", "session-1", 42, None),
            LoginResponse("failed", None, None, "Invalid credentials"),
        )
        for original in cases:
            with self.subTest(status=original.status):
                encoded = JsonPayloadCodec.encode(original)
                fields = json.loads(encoded)
                self.assertEqual(
                    {"status", "session_id", "user_id", "reason"},
                    set(fields),
                )
                decoded = JsonPayloadCodec.decode(encoded, LoginResponse)
                self.assertEqual(original, decoded)

    def test_login_response_from_result_validates_and_selects_fields(self):
        success = LoginResponse.from_result(
            True, session_id="session-1", user_id=7, reason="ignored"
        )
        failure = LoginResponse.from_result(
            False, session_id="ignored", user_id=7, reason="Denied"
        )

        self.assertEqual(LoginResponse("success", "session-1", 7, None), success)
        self.assertEqual(LoginResponse("failed", None, None, "Denied"), failure)
        for value in (1, "true", None):
            with self.subTest(success=value):
                with self.assertRaises(TypeError):
                    LoginResponse.from_result(value)

    def test_login_response_json_rejects_missing_unknown_and_wrongly_typed_fields(self):
        invalid_json = (
            b'{"status":"success","session_id":"s","user_id":1}',
            b'{"status":"failed","session_id":null,"user_id":null,'
            b'"reason":"Denied","extra":1}',
            b'{"status":"success","session_id":"s","user_id":"1",'
            b'"reason":null}',
        )
        for payload in invalid_json:
            with self.subTest(payload=payload):
                with self.assertRaises(CODEC_ERRORS):
                    JsonPayloadCodec.decode(payload, LoginResponse)


if __name__ == "__main__":
    unittest.main()
