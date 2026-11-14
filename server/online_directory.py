"""Bounded, session-owned snapshots for stable discovery over lossy UDP."""

from dataclasses import dataclass
import re
import threading
import time
import uuid

from common.JsonPayloadCodec import JsonPayloadCodec
from common.payload.user_info import UserInfo
from common.payload.user_list_response import UserListResponse
from server.account_exception import AccountException


@dataclass(frozen=True)
class _Snapshot:
    owner: str
    pages: tuple[UserListResponse, ...]
    created: float
    reference: int | None


class OnlineDirectory:
    TTL = 30.0
    MAX_SNAPSHOTS_PER_SESSION = 4

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.RLock()
        self._snapshots: dict[str, _Snapshot] = {}

    def page(self, owner: str, cursor: str | None, users: tuple[UserInfo, ...],
             reference: int | None = None) -> UserListResponse:
        """Call only after authenticating this request, including all retries."""
        with self._lock:
            self.cleanup()
            if cursor is not None:
                if not isinstance(cursor, str) or re.fullmatch(r"[a-f0-9]{32}:[1-9][0-9]{0,9}", cursor) is None:
                    raise AccountException(1003, "INVALID_CURSOR")
                identifier, index = cursor.split(":")
                snapshot = self._snapshots.get(identifier)
                if snapshot is None or snapshot.owner != owner or int(index) >= len(snapshot.pages):
                    raise AccountException(1003, "INVALID_CURSOR")
                return snapshot.pages[int(index)]
            if reference is not None:
                for snapshot in self._snapshots.values():
                    if snapshot.owner == owner and snapshot.reference == reference:
                        return snapshot.pages[0]

            identifier = uuid.uuid4().hex
            groups = []
            group = []
            for user in users:
                candidate = (*group, user)
                if not self._fits(UserListResponse(candidate, identifier + ":2147483647")):
                    if not group:
                        raise ValueError("Peer entry exceeds JSON payload limit")
                    groups.append(tuple(group))
                    group = []
                    if not self._fits(UserListResponse((user,), identifier + ":2147483647")):
                        raise ValueError("Peer entry exceeds JSON payload limit")
                group.append(user)
            if group or not groups:
                groups.append(tuple(group))
            pages = tuple(UserListResponse(group, f"{identifier}:{i + 1}" if i + 1 < len(groups) else None)
                          for i, group in enumerate(groups))
            for page in pages:
                JsonPayloadCodec.encode(page)
            owned = [key for key, value in self._snapshots.items() if value.owner == owner]
            while len(owned) >= self.MAX_SNAPSHOTS_PER_SESSION:
                del self._snapshots[owned.pop(0)]
            self._snapshots[identifier] = _Snapshot(owner, pages, self._clock(), reference)
            return pages[0]

    @staticmethod
    def _fits(page: UserListResponse) -> bool:
        try:
            JsonPayloadCodec.encode(page)
            return True
        except ValueError:
            return False

    def cleanup(self, active_tokens: frozenset[str] | None = None) -> None:
        with self._lock:
            for key, snapshot in tuple(self._snapshots.items()):
                if (self._clock() - snapshot.created >= self.TTL
                        or (active_tokens is not None and snapshot.owner not in active_tokens)):
                    del self._snapshots[key]
