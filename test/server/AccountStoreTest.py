import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server.account_exception import AccountException
from server.account_store import AccountStore


class AccountStoreTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.file = Path(temporary.name) / "accounts.json"
        self.store = AccountStore(self.file)

    def test_password_hash_storage_and_identity_survive_restart(self):
        alice = self.store.signup("alice", "password123")
        self.store.signup("bob", "password123")
        raw = self.file.read_text()
        self.assertNotIn("password123", raw)
        records = json.loads(raw)
        self.assertEqual(210_000, records[0]["iterations"])
        self.assertEqual(16, len(base64.b64decode(records[0]["salt"])))
        self.assertEqual(32, len(base64.b64decode(records[0]["password_hash"])))
        self.assertNotEqual(records[0]["salt"], records[1]["salt"])
        self.assertNotEqual(records[0]["password_hash"], records[1]["password_hash"])
        reopened = AccountStore(self.file)
        self.assertEqual(alice, reopened.authenticate("alice", "password123"))
        self.assertGreater(reopened.signup("charlie", "password123").user_id, alice.user_id)

    def test_wrong_credentials_duplicates_and_validation(self):
        self.store.signup("Alice", "password123")
        self.store.signup("alice", "password123")
        for name, password, code in (("Alice", "wrongpass", 1001), ("missing", "password123", 1001)):
            with self.assertRaises(AccountException) as error:
                self.store.authenticate(name, password)
            self.assertEqual(code, error.exception.code)
        with self.assertRaises(AccountException) as error:
            self.store.signup("alice", "password123")
        self.assertEqual(1002, error.exception.code)
        for name, password in (("a b", "password123"), ("á", "password123"),
                               ("a" * 33, "password123"), ("valid", "short"),
                               ("valid", "x" * 129), ("valid", "password\n")):
            with self.subTest(name=name):
                with self.assertRaises(AccountException):
                    self.store.signup(name, password)

    def test_concurrent_signup_publishes_exactly_one_identity(self):
        def signup(_):
            try:
                return self.store.signup("alice", "password123")
            except AccountException as exc:
                self.assertEqual(1002, exc.code)
                return None
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(signup, range(6)))
        self.assertEqual(1, sum(value is not None for value in results))
        self.assertEqual(1, len(json.loads(self.file.read_text())))

    def test_failed_atomic_replace_preserves_disk_and_memory(self):
        self.store.signup("alice", "password123")
        before = self.file.read_bytes()
        with patch("server.account_store.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.store.signup("bob", "password123")
        self.assertEqual(before, self.file.read_bytes())
        with self.assertRaises(AccountException):
            self.store.authenticate("bob", "password123")
        self.assertEqual([], list(self.file.parent.glob("accounts-*.tmp")))

    def test_corrupt_database_is_rejected_without_overwriting(self):
        self.file.write_text('[{"user_id":1}]')
        with self.assertRaises(OSError):
            AccountStore(self.file)
        self.assertEqual('[{"user_id":1}]', self.file.read_text())
