import unittest
from types import SimpleNamespace as Obj
from unittest import mock
from oci_zpr_visibility.flow_logs import validate_flow_log_source


class FlowSourceTests(unittest.TestCase):
    def log(self, resource, service='flowlogs', enabled=True):
        return Obj(data=Obj(is_enabled=enabled, configuration=Obj(source=Obj(service=service, resource=resource))))

    def test_unrelated_subnet_is_rejected_before_search(self):
        logging=mock.Mock();logging.get_log.return_value=self.log('ocid1.subnet.test')
        network=mock.Mock();network.get_subnet.return_value=Obj(data=Obj(vcn_id='other'))
        with mock.patch('oci_zpr_visibility.flow_logs.client', side_effect=[logging,network]):
            with self.assertRaisesRegex(ValueError, 'outside'):
                validate_flow_log_source(None,'group','log','selected')

    def test_vnic_source_is_resolved_to_selected_vcn(self):
        logging=mock.Mock();logging.get_log.return_value=self.log('ocid1.vnic.test')
        network=mock.Mock();network.get_vnic.return_value=Obj(data=Obj(subnet_id='subnet'))
        network.get_subnet.return_value=Obj(data=Obj(vcn_id='selected'))
        with mock.patch('oci_zpr_visibility.flow_logs.client', side_effect=[logging,network]):
            validate_flow_log_source(None,'group','log','selected')
        network.get_subnet.assert_called_once_with('subnet')

    def test_disabled_or_nonflow_source_is_rejected(self):
        for log in (self.log('selected',enabled=False),self.log('selected',service='audit')):
            logging=mock.Mock();logging.get_log.return_value=log
            with mock.patch('oci_zpr_visibility.flow_logs.client',return_value=logging):
                with self.assertRaisesRegex(ValueError,'enabled VCN'):
                    validate_flow_log_source(None,'group','log','selected')

    def test_selected_vcn_source_needs_no_network_lookup(self):
        logging=mock.Mock();logging.get_log.return_value=self.log('selected')
        with mock.patch('oci_zpr_visibility.flow_logs.client',return_value=logging) as factory:
            validate_flow_log_source(None,'group','log','selected')
        self.assertEqual(factory.call_count,1)
