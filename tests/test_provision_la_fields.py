from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest

from oci_zpr_visibility.provision_la import FIELD_TOKENS, ensure_fields


def test_reuse_native_text_fields_and_create_numeric_occurrence_count():
    fields = [SimpleNamespace(display_name=token, name="existing_" + token)
              for token in FIELD_TOKENS
              if token not in {"collection_operation", "error_category", "occurrence_count"}]
    fields.extend([SimpleNamespace(display_name="Operation", name="oper"),
                   SimpleNamespace(display_name="Category", name="cat")])
    la = Mock()
    la.upsert_field.return_value.data.name = "numeric_count"
    with patch("oci.pagination.list_call_get_all_results", return_value=SimpleNamespace(data=fields)):
        mapping = ensure_fields(la, "namespace")
    assert mapping["collection_operation"] == "oper"
    assert mapping["error_category"] == "cat"
    assert mapping["occurrence_count"] == "numeric_count"
    la.upsert_field.assert_called_once()
    details = la.upsert_field.call_args.kwargs["upsert_log_analytics_field_details"]
    assert details.display_name == "occurrence_count"
    assert details.data_type == "LONG"


def test_existing_occurrence_field_with_string_type_requires_migration():
    fields = [SimpleNamespace(display_name=token, name="existing_" + token, data_type="STRING")
              for token in FIELD_TOKENS]
    fields.extend([SimpleNamespace(display_name="Operation", name="oper", data_type="STRING"),
                   SimpleNamespace(display_name="Category", name="cat", data_type="STRING")])
    with patch("oci.pagination.list_call_get_all_results", return_value=SimpleNamespace(data=fields)):
        with pytest.raises(RuntimeError, match="separately reviewed field migration"):
            ensure_fields(Mock(), "namespace")
