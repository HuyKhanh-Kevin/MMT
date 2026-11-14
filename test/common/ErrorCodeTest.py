"""Tests for the ErrorCode registry and unknown-code fallback.

Run from the project root with:
    python -m unittest test.common.ErrorCodeTest -v
"""

import unittest

from common.ErrorCode import ErrorCode


EXPECTED_CODES = {
    0: "Success",
    1001: "Invalid credentials",
    1002: "Username taken",
    1003: "Invalid payload",
    1004: "Unauthenticated request",
    2001: "Recipient offline",
    3001: "Message/file too large",
    3002: "File hash mismatch",
    3003: "Transfer timed out",
    3004: "File write failed",
    4001: "Decryption failed",
    4002: "Window exceeded",
    4003: "Rate limit exceeded",
    5001: "Internal server error",
}


class ErrorCodeTest(unittest.TestCase):
    def test_registry_contains_expected_codes_and_messages(self):
        actual = {
            code: error.message
            for code, error in ErrorCode.error_codes.items()
        }
        self.assertEqual(EXPECTED_CODES, actual)

    def test_lookup_returns_registered_error(self):
        for code, message in EXPECTED_CODES.items():
            with self.subTest(code=code):
                error = ErrorCode.get_error_code(code)
                self.assertIs(error, ErrorCode.error_codes[code])
                self.assertEqual(code, error.code)
                self.assertEqual(message, error.message)

    def test_unknown_codes_return_unknown_error_without_changing_registry(self):
        registry_before = dict(ErrorCode.error_codes)

        for code in (-1, 9999):
            with self.subTest(code=code):
                error = ErrorCode.get_error_code(code)
                self.assertEqual(-1, error.code)
                self.assertEqual("Unknown error", error.message)
                self.assertNotIn(code, ErrorCode.error_codes)

        self.assertEqual(registry_before, ErrorCode.error_codes)

    def test_string_and_repr_are_readable(self):
        error = ErrorCode.get_error_code(1001)
        expected = "ErrorCode(code=1001, message='Invalid credentials')"

        self.assertEqual(expected, str(error))
        self.assertEqual(expected, repr(error))


if __name__ == "__main__":
    unittest.main()
