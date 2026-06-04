import unittest
from unittest import mock

from oci_zpr_visibility import cli


class CliSubcommandTests(unittest.TestCase):
    def test_new_subcommands_registered(self):
        parser = cli.build_parser()
        for name in ("provision-la", "validate-dashboards", "seed", "trigger"):
            args = parser.parse_args([name, "--profile", "cap"])
            self.assertEqual(args.command, name)
            # passthrough captures the remaining args verbatim
            self.assertEqual(args.args, ["--profile", "cap"])

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
        with mock.patch("oci_zpr_visibility.trigger.main", lambda argv: captured.setdefault("argv", argv) or 0):
            rc = cli.main(["trigger", "--out", "/tmp/x.jsonl"])
        self.assertEqual(rc, 0)
        self.assertEqual(captured["argv"], ["--out", "/tmp/x.jsonl"])


if __name__ == "__main__":
    unittest.main()
