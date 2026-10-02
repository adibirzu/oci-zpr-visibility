from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from oci_zpr_visibility.deploy_dashboard import reconcile_owned_dashboards, record_dashboard_searches


class Journal:
    installation = "test-install"
    def __init__(self):
        self.entries = {}
    def get(self, kind, name):
        return self.entries.get((kind, name))
    def record(self, kind, name, identity, **kwargs):
        self.entries[kind, name] = {"identity": identity, **kwargs}


def dashboard(owner="test-install", identity="owned", revision="old"):
    return SimpleNamespace(display_name="view", dashboard_id=identity,
        compartment_id="scope", freeform_tags={"zpr-installation": owner, "zpr-revision": revision})


def test_owned_upgrade_imports_exact_id_and_never_deletes():
    md, journal = Mock(), Journal()
    journal.record("dashboard", "view", "owned", created=True)
    md.get_management_dashboard.return_value = SimpleNamespace(data=dashboard(), headers={"etag": "version"})
    reconcile_owned_dashboards(md, [{"displayName": "view"}], "scope", journal,
        inventory=lambda: [dashboard()])
    details = md.import_dashboard.call_args.args[0]
    assert details.dashboards[0]["dashboardId"] == "owned"
    assert md.import_dashboard.call_args.kwargs["if_match"] == "version"
    md.delete_management_dashboard.assert_not_called()


def test_foreign_collision_fails_before_import():
    md = Mock()
    with pytest.raises(ValueError, match="foreign"):
        reconcile_owned_dashboards(md, [{"displayName": "view"}], "scope", Journal(),
            inventory=lambda: [dashboard("foreign-install")])
    md.import_dashboard.assert_not_called()


def test_import_failure_preserves_owned_id():
    md, journal = Mock(), Journal()
    journal.record("dashboard", "view", "owned", created=True)
    md.get_management_dashboard.return_value = SimpleNamespace(data=dashboard(), headers={"etag": "version"})
    md.import_dashboard.side_effect = RuntimeError("failed import")
    with pytest.raises(RuntimeError):
        reconcile_owned_dashboards(md, [{"displayName": "view"}], "scope", journal,
            inventory=lambda: [dashboard()])
    assert journal.get("dashboard", "view")["identity"] == "owned"
    md.delete_management_dashboard.assert_not_called()


def test_partial_import_recovered_only_with_pending_intent():
    md, journal = Mock(), Journal()
    journal.record("dashboard", "view", None, created=True)
    md.get_management_dashboard.return_value = SimpleNamespace(data=dashboard(), headers={"etag": "version"})
    reconcile_owned_dashboards(md, [{"displayName": "view"}], "scope", journal,
        inventory=lambda: [dashboard()])
    assert journal.get("dashboard", "view")["identity"] == "owned"


def test_tag_alone_without_journal_does_not_adopt():
    with pytest.raises(ValueError, match="foreign"):
        reconcile_owned_dashboards(Mock(), [{"displayName": "view"}], "scope", Journal(),
            inventory=lambda: [dashboard()])


def test_dashboard_tile_saved_search_ids_are_verified_and_journaled():
    md, journal = Mock(), Journal()
    md.get_management_dashboard.return_value.data = SimpleNamespace(tiles=[
        SimpleNamespace(saved_search_id="search-a"), SimpleNamespace(saved_search_id=None)])
    md.get_management_saved_search.return_value.data = SimpleNamespace(
        compartment_id="scope", freeform_tags={"zpr-installation": "test-install"})
    record_dashboard_searches(md, "owned", "scope", journal)
    assert journal.get("saved_search", "search-a")["identity"] == "search-a"
