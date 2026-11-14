"""Persistent accounts. Use one AccountStore instance per database/server process."""

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
from dataclasses import dataclass

from server.account_exception import AccountException


@dataclass(frozen=True)
class Account:
    user_id: int
    username: str


class AccountStore:
    ITERATIONS = 210_000

    def __init__(self, file: str | Path):
        self.file = Path(file).resolve()
        self._lock = threading.RLock()
        self._accounts: dict[str, dict] = {}
        self._next_id = 1
        if self.file.exists():
            self._load()

    @staticmethod
    def validate_credentials(username: str, password: str) -> None:
        if (not isinstance(username, str)
                or re.fullmatch(r"[A-Za-z0-9_]{1,32}", username) is None
                or not isinstance(password, str)
                or re.fullmatch(r"[\x20-\x7e]{8,128}", password) is None):
            raise AccountException(1003, "INVALID_CREDENTIALS_FORMAT")

    def _load(self) -> None:
        try:
            entries = json.loads(self.file.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                raise ValueError("Expected account array")
            ids = set()
            for entry in entries:
                if not isinstance(entry, dict) or set(entry) != {
                    "user_id", "username", "salt", "password_hash", "iterations"
                }:
                    raise ValueError("Invalid account record")
                user_id = entry["user_id"]
                name = entry["username"]
                self.validate_credentials(name, "validation-only")
                if (type(user_id) is not int or not 1 <= user_id <= 0xFFFFFFFF
                        or user_id in ids or name in self._accounts
                        or type(entry["iterations"]) is not int
                        or not 1 <= entry["iterations"] <= 2_000_000
                        or len(base64.b64decode(entry["salt"], validate=True)) != 16
                        or len(base64.b64decode(entry["password_hash"], validate=True)) != 32):
                    raise ValueError("Invalid account record")
                ids.add(user_id)
                self._accounts[name] = entry
                self._next_id = max(self._next_id, user_id + 1)
        except (ValueError, TypeError, KeyError, AccountException) as exc:
            raise OSError("Invalid account database") from exc

    @staticmethod
    def _hash(password: str, salt: bytes, iterations: int) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("ascii"), salt, iterations, 32)

    def signup(self, username: str, password: str) -> Account:
        self.validate_credentials(username, password)
        with self._lock:
            if username in self._accounts:
                raise AccountException(1002, "USERNAME_TAKEN")
        salt = secrets.token_bytes(16)
        digest = self._hash(password, salt, self.ITERATIONS)
        with self._lock:
            # Hash outside the lock; recheck before publishing concurrent signups.
            if username in self._accounts:
                raise AccountException(1002, "USERNAME_TAKEN")
            if self._next_id > 0xFFFFFFFF:
                raise OSError("User ID space exhausted")
            entry = dict(user_id=self._next_id, username=username,
                         salt=base64.b64encode(salt).decode("ascii"),
                         password_hash=base64.b64encode(digest).decode("ascii"),
                         iterations=self.ITERATIONS)
            updated = sorted([*self._accounts.values(), entry], key=lambda row: row["user_id"])
            self._persist(updated)
            self._accounts[username] = entry
            self._next_id += 1
            return Account(entry["user_id"], username)

    def _persist(self, entries: list[dict]) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        # Same-directory replacement avoids publishing a partially written database.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.file.parent,
                                             prefix="accounts-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(entries, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.file)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def authenticate(self, username: str, password: str) -> Account:
        self.validate_credentials(username, password)
        with self._lock:
            entry = self._accounts.get(username)
        # Do a hash even for unknown usernames, using the same default work factor.
        salt = base64.b64decode(entry["salt"]) if entry else bytes(16)
        iterations = entry["iterations"] if entry else self.ITERATIONS
        digest = self._hash(password, salt, iterations)
        expected = base64.b64decode(entry["password_hash"]) if entry else bytes(32)
        if not hmac.compare_digest(digest, expected) or entry is None:
            raise AccountException(1001, "INVALID_CREDENTIALS")
        return Account(entry["user_id"], entry["username"])
