import unittest

from common.JsonPayloadCodec import JsonPayloadCodec
from common.payload.user_info import UserInfo
from server.account_exception import AccountException
from server.online_directory import OnlineDirectory


class OnlineDirectoryTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.directory = OnlineDirectory(clock=lambda: self.now)
        self.users = tuple(UserInfo(f"user{i:028d}", "online", i + 1,
                                    "192.168.100.100", 65535, 65534) for i in range(20))

    def test_pages_are_complete_bounded_and_stable_during_presence_changes(self):
        page = self.directory.page("alice", None, self.users, 1)
        self.assertIsNotNone(page.next_cursor)
        result = []
        while True:
            self.assertLessEqual(len(JsonPayloadCodec.encode(page)), 1100)
            result.extend(page.users)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
            page = self.directory.page("alice", cursor, ())
            self.assertEqual(page, self.directory.page("alice", cursor, self.users))
        self.assertEqual(self.users, tuple(result))

    def test_first_page_retries_are_identical_even_when_users_change(self):
        first = self.directory.page("alice", None, self.users, 10)
        self.assertEqual(first, self.directory.page("alice", None, (), 10))
        self.assertEqual((), self.directory.page("alice", None, (), 11).users)

    def test_cursor_owner_ttl_eviction_and_logout_cleanup(self):
        cursor = self.directory.page("alice", None, self.users, 1).next_cursor
        for owner, value in (("bob", cursor), ("alice", "invalid"), ("alice", cursor + "0")):
            with self.assertRaises(AccountException):
                self.directory.page(owner, value, self.users)
        self.now = 30
        with self.assertRaises(AccountException):
            self.directory.page("alice", cursor, self.users)
        cursor = self.directory.page("alice", None, self.users, 2).next_cursor
        for sequence in range(3, 7):
            self.directory.page("alice", None, self.users, sequence)
        with self.assertRaises(AccountException):
            self.directory.page("alice", cursor, self.users)
        cursor = self.directory.page("alice", None, self.users, 7).next_cursor
        self.directory.cleanup(frozenset())
        with self.assertRaises(AccountException):
            self.directory.page("alice", cursor, self.users)
