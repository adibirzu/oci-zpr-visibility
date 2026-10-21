import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('estate_review',Path(__file__).parents[1]/'scripts/render_estate_review.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class EstateReviewPrivacyTests(unittest.TestCase):
    def test_native_receipts_allow_only_known_names_and_counts(self):
        report={'observed_at':'2026-10-09T11:00:00Z', 'indexed_records':723,
                'token':'private-token', 'dashboards':[
                    {'name':'Resource estate','status':'ADDED','widgets':6,'data':5,
                     'zero_allowed':1,'zero_unexpected':0,'errors':0,'id':'private-id'},
                    {'name':'private-customer-name','status':'ADDED','widgets':1}]}
        native=module.review_data({},[],{},report)['native']
        self.assertEqual(len(native['dashboards']),1)
        self.assertEqual(native['indexed_records'],723)
        for value in ('private-id','private-token','private-customer-name'):
            self.assertNotIn(value,str(native))

    def test_renderer_uses_opaque_aliases_instead_of_identifiers_and_addresses(self):
        snapshot={'resource_inventory':[{'resource_id':'private-resource-id','resource_name':'private-customer-name',
                   'resource_type':'instance','compartment_id':'private-compartment','vcn_id':'private-vcn',
                   'lifecycle_state':'RUNNING'}], 'resource_coverage':[]}
        flows=[{'data':{'sourceAddress':'10.1.2.3','destinationAddress':'10.4.5.6',
                        'action':'ACCEPT','destinationPort':443}}]
        data=module.review_data(snapshot,flows,{'flow_records':1,'window_minutes':15,'actions':{'ACCEPT':1}})
        encoded=str(data)
        for private in ('private-resource-id','private-customer-name','private-compartment','private-vcn','10.1.2.3','10.4.5.6'):
            self.assertNotIn(private,encoded)
        self.assertEqual(data['flows'][0]['records'],1)

    def test_summary_private_metadata_is_never_embedded(self):
        data=module.review_data({},[],{'flow_records':0,'target':'private-ocid','query':'private-query','token':'secret-token'})
        for value in ('private-ocid','private-query','secret-token'):
            self.assertNotIn(value,str(data))

    def test_empty_stale_and_inconsistent_inputs_do_not_claim_live_health(self):
        data=module.review_data({'snapshot_time':'2020-01-01T00:00:00Z'},[],
                               {'flow_records':10,'retrieved_at':'2020-01-01T00:00:00Z'})
        self.assertEqual(data['lab']['status'],'STALE_OR_UNAVAILABLE')
        self.assertEqual(data['lab']['running'],0)
        self.assertEqual(data['flowSummary']['status'],'STALE_OR_INVALID')
        self.assertEqual(data['flowSummary']['flow_records'],0)
        empty=module.review_data({},[],{})
        self.assertEqual(empty['freshness'],'UNAVAILABLE')
