import unittest
from scripts.verify_sources import verify


class SourceTests(unittest.TestCase):
    def test_all_frozen_source_hashes(self):
        self.assertGreater(verify(), 0)
