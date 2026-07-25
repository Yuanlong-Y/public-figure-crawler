import unittest

from crawler import normalize_url


class NormalizeUrlTests(unittest.TestCase):
    def test_removes_fragment(self):
        result = normalize_url("https://example.com/page#section")
        self.assertEqual(result, "https://example.com/page")


if __name__ == "__main__":
    unittest.main()