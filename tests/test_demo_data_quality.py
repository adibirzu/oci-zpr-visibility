from oci_zpr_visibility import dashboard, provision_la


def test_policy_list_fields_are_mapped_as_multivalue():
    for name in ('attribute_references', 'cidrs', 'ips'):
        assert name in provision_la.FIELD_TOKENS
        assert name in provision_la.MULTI_VALUE_FIELDS


def test_raw_tables_remove_inapplicable_native_defaults():
    for widget in dashboard.iter_widgets(dashboard.load_dashboard()):
        if widget['visualization_type'] == 'table':
            for name in ('-Entity', "-'Entity Type'", "-'Host Name (Server)'", "-'Problem Priority'", '-Label'):
                assert name in widget['query'], widget['name']


def test_estate_has_family_specific_placement_views():
    tab = next(t for t in dashboard.load_dashboard()['tabs'] if t['name'] == 'Resource estate')
    queries = {w['name']: w['query'] for w in tab['widgets']}
    assert "resource_type = literal(instance)" in queries['Compute placement and lifecycle']
    assert "resource_type in ('oke_cluster', 'oke_node_pool')" in queries['OKE placement and lifecycle']
    assert "resource_type = 'autonomous_database'" in queries['Autonomous Database lifecycle and placement']
    assert 'subnet_ids' in queries['OKE placement and lifecycle']


def test_policy_table_includes_parser_evidence():
    w = next(w for w in dashboard.iter_widgets(dashboard.load_dashboard()) if w['name'] == 'Policy statement table')
    for field in ('action', 'source_type', 'destination_type', 'parser_confidence', 'has_unmodeled_policy_filters', 'attribute_references', 'cidrs', 'ips'):
        assert field in w['query']
