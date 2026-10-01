import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest
import oci

from oci_zpr_visibility.cleanup import cleanup
from oci_zpr_visibility.ownership import Ownership


def session():
    return NS(tenancy_id="tenancy", region="region")


def test_bucket_owner_mismatch_fails_before_reading_journal():
    storage = Mock()
    storage.get_namespace.return_value.data = "namespace"
    storage.get_bucket.return_value.data = NS(compartment_id="other", freeform_tags={})
    with patch("oci_zpr_visibility.ownership.client", return_value=storage):
        with pytest.raises(ValueError, match="compartment"):
            Ownership(session(), "bucket", "test-install", "scope")
    storage.get_object.assert_not_called()


def test_journal_is_bound_to_target_and_cas_version():
    storage = Mock()
    storage.get_namespace.return_value.data = "namespace"
    storage.get_bucket.return_value.data = NS(compartment_id="scope", freeform_tags={"zpr-installation": "test-install"})
    data = {"version": 1, "target": {"installation": "test-install", "tenancy": "tenancy", "region": "region", "compartment": "scope"}, "resources": {}}
    storage.get_object.return_value = NS(data=NS(content=json.dumps(data).encode()), headers={"etag": "v1"})
    storage.put_object.return_value.headers = {"etag": "v2"}
    with patch("oci_zpr_visibility.ownership.client", return_value=storage):
        journal = Ownership(session(), "bucket", "test-install", "scope")
        journal.record("field", "token", "shared", created=False)
    assert storage.put_object.call_args.kwargs["if_match"] == "v1"
    assert journal.etag == "v2"
    with pytest.raises(ValueError, match="identity"):
        journal.record("field", "token", "foreign", created=True)


def journal(entries):
    return NS(installation="test-install", ns="namespace", data={"resources": entries}, save=Mock())


def entry(kind, identity):
    return {"kind": kind, "name": identity, "identity": identity, "created": True, "deleted": False}


def tagged():
    return NS(compartment_id="scope", freeform_tags={"zpr-installation": "test-install"})


def test_cleanup_checks_all_ownership_before_any_delete_and_preserves_fields():
    md, la = Mock(), Mock()
    md.list_management_dashboards.return_value = NS(data=NS(items=[]), headers={})
    md.get_management_dashboard.return_value = NS(data=tagged(), headers={"etag": "d"})
    la.get_parser.return_value = NS(data=NS(description="foreign"), headers={"etag": "p"})
    ledger = journal({"d": entry("dashboard", "dashboard"), "p": entry("parser", "parser")})
    with pytest.raises(ValueError, match="ownership"):
        cleanup(ledger, la, md, "scope", execute=True)
    md.delete_management_dashboard.assert_not_called()
    la.delete_parser.assert_not_called()


def test_cleanup_dependency_order_and_preserved_shared_fields():
    md, la = Mock(), Mock()
    events = []
    md.list_management_dashboards.return_value = NS(data=NS(items=[NS(dashboard_id="dashboard")]), headers={})
    md.get_management_dashboard.return_value = NS(data=tagged(), headers={"etag": "d"})
    la.get_parser.return_value = NS(data=NS(description="ZPR visibility installation=test-install"), headers={"etag": "p"})
    la.get_source.return_value = NS(data=NS(description="ZPR visibility installation=test-install"), headers={"etag": "s"})
    la.get_log_analytics_log_group.return_value = NS(data=tagged(), headers={"etag": "g"})
    md.delete_management_dashboard.side_effect = lambda *a, **kw: events.append("dashboard")
    la.delete_source.side_effect = lambda *a, **kw: events.append("source")
    la.delete_parser.side_effect = lambda *a, **kw: events.append("parser")
    la.delete_log_analytics_log_group.side_effect = lambda *a, **kw: events.append("log_group")
    ledger = journal({k: entry(k, k) for k in ("log_group", "parser", "field", "source", "dashboard")})
    result = cleanup(ledger, la, md, "scope", execute=True)
    assert events == ["dashboard", "source", "parser", "log_group"]
    assert result["preserved_shared_fields"] == 1
    assert ledger.data["cleanup_complete"]
    la.delete_field.assert_not_called()


def test_pending_creation_blocks_cleanup_without_deleting_other_content():
    md = Mock()
    md.list_management_dashboards.return_value = NS(data=NS(items=[]), headers={})
    with pytest.raises(ValueError, match="pending"):
        cleanup(journal({"pending": entry("dashboard", None)}), Mock(), md, "scope", execute=True)
    md.delete_management_dashboard.assert_not_called()


def test_failed_parser_creation_is_absent_only_after_authorized_inventory():
    la, md = Mock(), Mock()
    md.list_management_dashboards.return_value = NS(data=NS(items=[]), headers={})
    la.get_parser.side_effect = oci.exceptions.ServiceError(404, "NotAuthorizedOrNotFound", {}, "not found")
    ledger = journal({"parser": entry("parser", "owned-parser")})
    with patch("oci.pagination.list_call_get_all_results", return_value=NS(data=[])):
        cleanup(ledger, la, md, "scope", execute=True)
    assert ledger.data["resources"]["parser"]["deleted"]
    la.delete_parser.assert_not_called()


def test_failed_inventory_never_turns_404_into_cleanup_success():
    la, md = Mock(), Mock()
    md.list_management_dashboards.return_value = NS(data=NS(items=[]), headers={})
    la.get_parser.side_effect = oci.exceptions.ServiceError(404, "NotAuthorizedOrNotFound", {}, "not found")
    ledger = journal({"parser": entry("parser", "owned-parser")})
    with patch("oci.pagination.list_call_get_all_results", side_effect=RuntimeError("denied")):
        with pytest.raises(RuntimeError):
            cleanup(ledger, la, md, "scope", execute=True)
    assert not ledger.data.get("cleanup_complete")
    la.delete_parser.assert_not_called()
