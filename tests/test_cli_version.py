import unittest

from oci_zpr_visibility import cli


class CliVersionTests(unittest.TestCase):
    def test_version_flag_prints_version_and_exits_zero(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)

    def test_package_exposes_version(self):
        import oci_zpr_visibility

        self.assertRegex(oci_zpr_visibility.__version__, r"^\d+\.\d+\.\d+")


if __name__ == "__main__":
    unittest.main()
