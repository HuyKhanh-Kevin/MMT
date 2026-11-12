"""Python port of the PBKDF2 password storage scenarios.

Run from the project root with:
    python -m unittest test.integration.PasswordSecurityTest -v

These tests cover the standalone hashing contract from the Java test. They do
not exercise the Java AccountStore; the server package tests require that
server's missing Java common classes to be restored or the server ported.
"""

import base64
import hashlib
import hmac
import secrets
import unittest
from dataclasses import dataclass

from common.ErrorCode import ErrorCode


ITERATIONS = 20_000


def hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, ITERATIONS, dklen=32
    )
    return base64.b64encode(digest).decode("ascii")


def valid_password(password: str | None) -> bool:
    return password is not None and 8 <= len(password) <= 128


@dataclass(frozen=True)
class StoredAccount:
    user_id: int
    username: str
    salt: str
    password_hash: str


class PasswordSecurityTest(unittest.TestCase):
    def test_password_is_not_stored_as_plaintext(self):
        password = "SuperSecretPassword123!"
        salt = secrets.token_bytes(16)
        account = StoredAccount(
            1,
            "alice",
            base64.b64encode(salt).decode("ascii"),
            hash_password(password, salt),
        )

        self.assertNotEqual(password, account.password_hash)
        self.assertNotIn(password, account.password_hash)
        self.assertNotIn(password, account.salt)
        self.assertEqual(16, len(base64.b64decode(account.salt)))
        self.assertEqual(32, len(base64.b64decode(account.password_hash)))

    def test_random_salts_make_equal_passwords_hash_differently(self):
        password = "CommonPassword456@"
        salt1 = secrets.token_bytes(16)
        salt2 = secrets.token_bytes(16)

        self.assertNotEqual(salt1, salt2)
        self.assertNotEqual(hash_password(password, salt1), hash_password(password, salt2))

    def test_authentication_accepts_correct_password_and_rejects_wrong_one(self):
        correct = "CorrectPassword789#"
        wrong = "WrongPassword000#"
        salt = secrets.token_bytes(16)
        stored = hash_password(correct, salt)

        self.assertTrue(hmac.compare_digest(stored, hash_password(correct, salt)))
        self.assertFalse(hmac.compare_digest(stored, hash_password(wrong, salt)))
        self.assertEqual(1001, ErrorCode.get_error_code(1001).code)

    def test_password_policy_maps_short_password_to_invalid_payload(self):
        self.assertFalse(valid_password("12345"))
        self.assertEqual(1003, ErrorCode.get_error_code(1003).code)
        self.assertTrue(valid_password("password"))
        self.assertTrue(valid_password("p" * 128))
        self.assertFalse(valid_password("p" * 129))
        self.assertFalse(valid_password(None))


if __name__ == "__main__":
    unittest.main()
