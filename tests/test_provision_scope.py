import unittest
from unittest import mock

from oci_zpr_visibility import provision_la


class ProvisionScopeTests(unittest.TestCase):
    def test_log_group_compartment_is_scoped_but_source_stays_tenancy_scoped(self):
        session = mock.Mock(tenancy_id="tenancy")
        with (
            mock.patch.object(provision_la, "_client", return_value=(session, mock.Mock(), "namespace")),
            mock.patch.object(provision_la, "ensure_fields", return_value={}),
            mock.patch.object(provision_la, "ensure_log_group", return_value="log-group") as ensure_group,
            mock.patch.object(provision_la, "ensure_parser", return_value="parser"),
            mock.patch.object(provision_la, "ensure_source", return_value="source") as ensure_source,
        ):
            self.assertEqual(provision_la.main([
                "--log-group-compartment-id", "observation-compartment",
            ]), 0)
        self.assertEqual(ensure_group.call_args.args[2], "observation-compartment")
        self.assertEqual(ensure_source.call_args.args[2], "tenancy")


if __name__ == "__main__":
    unittest.main()
