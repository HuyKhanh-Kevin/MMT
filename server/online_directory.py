import threading
import time
import uuid

from common.JsonPayloadCodec import JsonPayloadCodec
from common.payload.user_list_response import UserListResponse
from server.account_exception import AccountException


class OnlineDirectory:
    TTL = 30.0
    MAX_SNAPSHOTS_PER_SESSION = 4

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.RLock()
        self._snapshots = {}

    def page(self, owner, cursor, users, reference=None):

        with self._lock:
            self.cleanup()

            if cursor is not None:
                return self._read_page(owner, cursor)


            if reference is not None:
                for snapshot in self._snapshots.values():
                    if snapshot["owner"] == owner and snapshot["reference"] == reference:
                        return snapshot["pages"][0]

            identifier = uuid.uuid4().hex
            pages = self._split_users(users, identifier)

            owned = []
            for key, snapshot in self._snapshots.items():
                if snapshot["owner"] == owner:
                    owned.append(key)
            while len(owned) >= self.MAX_SNAPSHOTS_PER_SESSION:
                oldest = owned.pop(0)
                del self._snapshots[oldest]

            self._snapshots[identifier] = {
                "owner": owner,
                "pages": pages,
                "created": self._clock(),
                "reference": reference,
            }
            return pages[0]

    def _read_page(self, owner, cursor):
        if not isinstance(cursor, str):
            raise AccountException(1003, "INVALID_CURSOR")
        parts = cursor.split(":")
        if len(parts) != 2:
            raise AccountException(1003, "INVALID_CURSOR")
        identifier, page_number = parts

        if len(identifier) != 32:
            raise AccountException(1003, "INVALID_CURSOR")
        for character in identifier:
            if character not in "0123456789abcdef":
                raise AccountException(1003, "INVALID_CURSOR")
        if len(page_number) < 1 or len(page_number) > 10:
            raise AccountException(1003, "INVALID_CURSOR")
        if not page_number.isascii() or not page_number.isdecimal() or page_number[0] == "0":
            raise AccountException(1003, "INVALID_CURSOR")

        snapshot = self._snapshots.get(identifier)
        if snapshot is None or snapshot["owner"] != owner:
            raise AccountException(1003, "INVALID_CURSOR")
        index = int(page_number)
        if index >= len(snapshot["pages"]):
            raise AccountException(1003, "INVALID_CURSOR")
        return snapshot["pages"][index]

    def _split_users(self, users, identifier):
        groups = []
        group = []

        reserved_cursor = identifier + ":9999999999"
        for user in users:
            candidate = group.copy()
            candidate.append(user)
            if not self._fits(UserListResponse(tuple(candidate), reserved_cursor)):
                if len(group) == 0:
                    raise ValueError("Peer entry exceeds JSON payload limit")
                groups.append(tuple(group))
                group = []
                if not self._fits(UserListResponse((user,), reserved_cursor)):
                    raise ValueError("Peer entry exceeds JSON payload limit")
            group.append(user)
        if len(group) > 0 or len(groups) == 0:
            groups.append(tuple(group))

        pages = []
        for index in range(len(groups)):
            if index + 1 < len(groups):
                next_cursor = identifier + ":" + str(index + 1)
            else:
                next_cursor = None
            pages.append(UserListResponse(groups[index], next_cursor))
        return tuple(pages)

    def _fits(self, page):
        try:
            JsonPayloadCodec.encode(page)
            return True
        except ValueError:
            return False

    def cleanup(self, active_tokens=None):
        with self._lock:
            for key, snapshot in list(self._snapshots.items()):
                expired = self._clock() - snapshot["created"] >= self.TTL
                logged_out = False
                if active_tokens is not None:
                    if snapshot["owner"] not in active_tokens:
                        logged_out = True
                if expired or logged_out:
                    del self._snapshots[key]
