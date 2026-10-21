import unittest
from unittest import mock

from oci_zpr_visibility import refresh
from oci_zpr_visibility.cli import build_parser, cmd_collect


class CollectionScopeTests(unittest.TestCase):
    def test_collect_parser_repeated_scope_is_passed_to_collector(self):
        args = build_parser().parse_args(['collect', '--collection-compartment-id', 'one',
                                         '--collection-compartment-id', 'two'])
        collector = mock.Mock()
        collector.collect.return_value = {'snapshot_time': 'now'}
        collector.records_for_snapshot.return_value = []
        with (mock.patch('oci_zpr_visibility.cli._session', return_value='session'),
              mock.patch('oci_zpr_visibility.cli.ZprCollector', return_value=collector) as factory,
              mock.patch('oci_zpr_visibility.cli.write_json'),
              mock.patch('oci_zpr_visibility.cli.write_jsonl')):
            cmd_collect(args)
        factory.assert_called_once_with('session', compartment_ids=['one', 'two'])

    def test_refresh_scope_reaches_collector(self):
        collector = mock.Mock()
        collector.collect.return_value = {'snapshot_time': '2026-10-09T00:00:00Z'}
        collector.records_for_snapshot.return_value = []
        with (mock.patch('oci_zpr_visibility.refresh.build_session', return_value='session'),
              mock.patch('oci_zpr_visibility.refresh.ZprCollector', return_value=collector) as factory,
              mock.patch('oci_zpr_visibility.refresh.generate_findings', return_value=[]),
              mock.patch('oci_zpr_visibility.refresh.load_previous_records', return_value=[]),
              mock.patch('oci_zpr_visibility.refresh.compute_drift', return_value=[]),
              mock.patch('oci_zpr_visibility.refresh.save_records'),
              mock.patch('oci_zpr_visibility.refresh.provision_la.main', return_value=0),
              mock.patch('oci_zpr_visibility.metrics.publish_metrics', return_value=0)):
            self.assertEqual(refresh.main(['--state-bucket', 'state', '--quiet',
                             '--collection-compartment-id', 'one']), 0)
        factory.assert_called_once_with('session', compartment_ids=['one'])
