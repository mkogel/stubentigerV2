"""Deliberately failing test: a throwaway PR showing that the `ci` check turns red."""

import unittest


class CiRedDemoTest(unittest.TestCase):
    def test_fails_on_purpose(self) -> None:
        self.fail("deliberate failure for the CI red demo (#26)")
