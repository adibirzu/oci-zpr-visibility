import argparse
import unittest

from oci_zpr_visibility.config import RunConfig


class RunConfigTests(unittest.TestCase):
    def test_valid_config(self):
        cfg = RunConfig(auth="api_key", config_file=None, profile="example-profile", region="eu-frankfurt-1")
        self.assertEqual(cfg.profile, "example-profile")

    def test_invalid_auth_rejected(self):
        with self.assertRaises(ValueError):
            RunConfig(auth="banana", config_file=None, profile="example-profile", region=None)

    def test_empty_profile_rejected(self):
        with self.assertRaises(ValueError):
            RunConfig(auth="api_key", config_file=None, profile="  ", region=None)

    def test_is_frozen(self):
        cfg = RunConfig(auth="api_key", config_file=None, profile="DEFAULT", region=None)
        with self.assertRaises(Exception):
            cfg.profile = "other"  # type: ignore[misc]

    def test_from_args(self):
        ns = argparse.Namespace(auth="instance_principal", config_file=None, profile="example-profile", region="eu-frankfurt-1")
        cfg = RunConfig.from_args(ns)
        self.assertEqual(cfg.auth, "instance_principal")
        self.assertEqual(cfg.region, "eu-frankfurt-1")


if __name__ == "__main__":
    unittest.main()
