"""Aggregate the self-contained ports of the four Java integration suites.

Run from the project root with:
    python -m unittest test.integration.MasterIntegrationTest -v
"""

import unittest

from test.integration.FileIntegrityTest import FileIntegrityTest
from test.integration.MalformedPacketsTest import MalformedPacketsTest
from test.integration.PasswordSecurityTest import PasswordSecurityTest
from test.integration.SuddenDisconnectTest import SuddenDisconnectTest


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for test_case in (
        MalformedPacketsTest,
        SuddenDisconnectTest,
        FileIntegrityTest,
        PasswordSecurityTest,
    ):
        suite.addTests(loader.loadTestsFromTestCase(test_case))
    return suite
