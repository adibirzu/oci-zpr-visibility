"""Estate fields reuse semantic labels and avoid exhausting STRING slots."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
from oci_zpr_visibility import provision_la


def test_alias_reuses_existing_semantic_field():
    la = Mock()
    with patch.object(provision_la, 'FIELD_TOKENS', ['lifecycle_state']), patch.object(
        provision_la.oci.pagination, 'list_call_get_all_results',
        return_value=SimpleNamespace(data=[SimpleNamespace(display_name='Lifecycle State', name='existing',
                                                           data_type='STRING', is_multi_valued=False)]),
    ):
        assert provision_la.ensure_fields(la, 'namespace') == {'lifecycle_state': 'existing'}
    la.upsert_field.assert_not_called()


def test_count_and_subnet_fields_have_correct_types():
    la = Mock()
    la.upsert_field.side_effect = [SimpleNamespace(data=SimpleNamespace(name='count')), SimpleNamespace(data=SimpleNamespace(name='subnets'))]
    with patch.object(provision_la, 'FIELD_TOKENS', ['available_count', 'subnet_ids']), patch.object(
        provision_la.oci.pagination, 'list_call_get_all_results', return_value=SimpleNamespace(data=[]),
    ):
        provision_la.ensure_fields(la, 'namespace')
    count, subnets = [c.kwargs['upsert_log_analytics_field_details'] for c in la.upsert_field.call_args_list]
    assert count.data_type == 'LONG' and not count.is_multi_valued
    assert subnets.data_type == 'STRING' and subnets.is_multi_valued


def test_incompatible_existing_field_fails_closed():
    la = Mock()
    with patch.object(provision_la, 'FIELD_TOKENS', ['available_count']), patch.object(
        provision_la.oci.pagination, 'list_call_get_all_results',
        return_value=SimpleNamespace(data=[SimpleNamespace(display_name='available_count', name='foreign',
                                                           data_type='STRING', is_multi_valued=False)]),
    ):
        try:
            provision_la.ensure_fields(la, 'namespace')
        except ValueError as exc:
            assert 'available_count' in str(exc)
            assert 'LONG' in str(exc)
        else:
            raise AssertionError('incompatible existing field was reused')
