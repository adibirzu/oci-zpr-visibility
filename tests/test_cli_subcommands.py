import unittest
from unittest import mock

from oci_zpr_visibility import cli


class CliSubcommandTests(unittest.TestCase):
    def test_new_subcommands_listed_in_help(self):
        help_text = cli.build_parser().format_help()
        for name in ("provision-la", "validate-dashboards", "seed", "trigger"):
            self.assertIn(name, help_text)

    def test_passthrough_preserves_leading_flags(self):
        captured = {}

        def fake_main(argv):
            captured["argv"] = argv
            return 0

        with mock.patch("oci_zpr_visibility.validate_dashboards.main", fake_main):
            rc = cli.main(["validate-dashboards", "--profile", "cap", "--lookback-days", "7"])
        self.assertEqual(rc, 0)
        self.assertEqual(captured["argv"], ["--profile", "cap", "--lookback-days", "7"])

    def test_provision_la_routes_to_module(self):
        captured = {}

        def fake_main(argv):
            captured["argv"] = argv
            return 0

        with mock.patch("oci_zpr_visibility.provision_la.main", fake_main):
            rc = cli.main(["provision-la", "--profile", "cap", "--upload", "x.jsonl"])

        self.assertEqual(rc, 0)
        self.assertEqual(captured["argv"], ["--profile", "cap", "--upload", "x.jsonl"])

    def test_trigger_routes_to_module(self):
        captured = {}

        def fake_main(argv):
            captured["argv"] = argv
            return 0

        with mock.patch("oci_zpr_visibility.trigger.main", fake_main):
            rc = cli.main(["trigger", "--out", "/tmp/x.jsonl"])
        self.assertEqual(rc, 0)
        self.assertEqual(captured["argv"], ["--out", "/tmp/x.jsonl"])


if __name__ == "__main__":
    unittest.main()
