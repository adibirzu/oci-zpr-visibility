import unittest

from oci_zpr_visibility.oci_clients import DEFAULT_TIMEOUT, should_retry


class RetryPolicyTests(unittest.TestCase):
    def test_retries_on_transient_and_throttle(self):
        for code in (429, 500, 502, 503, 504):
            self.assertTrue(should_retry(code), f"{code} should retry")

    def test_does_not_retry_on_client_errors(self):
        for code in (400, 401, 403, 404, 409):
            self.assertFalse(should_retry(code), f"{code} should not retry")

    def test_timeout_is_connect_read_tuple(self):
        self.assertEqual(len(DEFAULT_TIMEOUT), 2)
        connect, read = DEFAULT_TIMEOUT
        self.assertGreater(connect, 0)
        self.assertGreater(read, connect)


if __name__ == "__main__":
    unittest.main()
