from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from oci_zpr_visibility.deploy_dashboard import import_new_dashboard_suite


def response(items=(), next_page=None):
    return SimpleNamespace(data=SimpleNamespace(items=list(items)),
                           headers={"opc-next-page": next_page} if next_page else {})


def test_foreign_same_name_preserved_without_import_or_delete():
    md = Mock()
    md.list_management_dashboards.return_value = response([
        SimpleNamespace(display_name="existing", dashboard_id="foreign")])
    with pytest.raises(ValueError, match="existing"):
        import_new_dashboard_suite(md, [{"displayName": "existing"}], "scope")
    md.delete_management_dashboard.assert_not_called()
    md.import_dashboard.assert_not_called()


def test_discovery_error_fails_closed():
    md = Mock()
    md.list_management_dashboards.side_effect = RuntimeError("inventory unavailable")
    with pytest.raises(RuntimeError):
        import_new_dashboard_suite(md, [{"displayName": "new"}], "scope")
    md.import_dashboard.assert_not_called()
    md.delete_management_dashboard.assert_not_called()


def test_conflict_on_later_page_prevents_entire_suite_import():
    md = Mock()
    md.list_management_dashboards.side_effect = [response(next_page="page2"),
        response([SimpleNamespace(display_name="new", dashboard_id="foreign")])]
    with pytest.raises(ValueError):
        import_new_dashboard_suite(md, [{"displayName": "new"}], "scope")
    assert md.list_management_dashboards.call_args.kwargs["page"] == "page2"
    md.import_dashboard.assert_not_called()


def test_import_failure_never_deletes_existing_content():
    md = Mock()
    md.list_management_dashboards.return_value = response()
    md.import_dashboard.side_effect = RuntimeError("import failed")
    with pytest.raises(RuntimeError):
        import_new_dashboard_suite(md, [{"displayName": "new"}], "scope")
    md.delete_management_dashboard.assert_not_called()


def test_empty_complete_inventory_allows_one_import():
    md = Mock()
    md.list_management_dashboards.return_value = response()
    import_new_dashboard_suite(md, [{"displayName": "new"}], "scope")
    md.import_dashboard.assert_called_once()
    md.delete_management_dashboard.assert_not_called()
