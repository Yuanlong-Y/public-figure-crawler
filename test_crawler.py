import unittest

from crawler import domain_allowed, normalize_url


class NormalizeUrlTests(unittest.TestCase):
    def test_removes_fragment(self):
        result = normalize_url("https://example.com/page#section")
        self.assertEqual(result, "https://example.com/page")

    def test_rejects_non_http_url(self):
        with self.assertRaises(ValueError):
            normalize_url("ftp://example.com/file")

class DomainAllowedTests(unittest.TestCase):
    def test_allows_domain_and_subdomain(self):
        allowed = ("example.com",)

        self.assertTrue(domain_allowed("https://example.com/page", allowed))
        self.assertTrue(domain_allowed("https://news.example.com/page", allowed))

    def test_rejects_similar_domain(self):
        allowed = ("example.com",)

        self.assertFalse(domain_allowed("https://notexample.com/page", allowed))


if __name__ == "__main__":
    unittest.main()