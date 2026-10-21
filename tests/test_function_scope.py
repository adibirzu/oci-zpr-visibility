import importlib.util
import io
import json
from pathlib import Path
import types
import unittest
from unittest import mock


class FunctionScopeTests(unittest.TestCase):
    def load_handler(self):
        response=types.SimpleNamespace(Response=lambda ctx,**kwargs:kwargs)
        with mock.patch.dict('sys.modules',{'fdk':types.SimpleNamespace(response=response)}):
            spec=importlib.util.spec_from_file_location('estate_function',Path(__file__).parents[1]/'functions/func.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_invalid_explicit_scope_never_invokes_refresh(self):
        module=self.load_handler()
        for value in ('[]','[""]','[3]','{"tenant":"secret-target"}'):
            ctx=types.SimpleNamespace(Config=lambda:{'STATE_BUCKET':'state','COLLECTION_COMPARTMENT_IDS':value})
            with mock.patch.object(module.refresh,'main') as run, mock.patch.dict('os.environ',{},clear=True):
                result=module.handler(ctx,io.BytesIO())
            self.assertEqual(result['status_code'],400)
            self.assertNotIn('secret-target',result['response_data']);run.assert_not_called()

    def test_function_propagates_scope_and_flow_validation(self):
        module=self.load_handler()
        cfg={'STATE_BUCKET':'state','COLLECTION_COMPARTMENT_IDS':'["scope1", "scope2"]',
             'FLOW_LOG_GROUP_ID':'group','FLOW_LOG_ID':'log','FLOW_VCN_ID':'vcn'}
        ctx=types.SimpleNamespace(Config=lambda:cfg)
        with mock.patch.object(module.refresh,'main',return_value=0) as run,mock.patch.dict('os.environ',{},clear=True):
            result=module.handler(ctx)
        self.assertEqual(result['status_code'],200)
        args=run.call_args.args[0]
        self.assertEqual(args.count('--collection-compartment-id'),2)
        self.assertIn('--flow-vcn-id',args);self.assertIn('vcn',args)

    def test_function_propagates_log_group_compartment(self):
        module=self.load_handler()
        ctx=types.SimpleNamespace(Config=lambda:{
            'STATE_BUCKET':'state',
            'LOG_GROUP_COMPARTMENT_ID':'log-compartment',
        })
        with mock.patch.object(module.refresh,'main',return_value=0) as run,mock.patch.dict('os.environ',{},clear=True):
            result=module.handler(ctx)
        self.assertEqual(result['status_code'],200)
        args=run.call_args.args[0]
        self.assertEqual(args[args.index('--log-group-compartment-id') + 1], 'log-compartment')

    def test_partial_flow_flags_return_400_without_refresh(self):
        module=self.load_handler()
        for cfg in (
            {'FLOW_LOG_GROUP_ID':'group'},
            {'FLOW_LOG_ID':'log'},
            {'FLOW_VCN_ID':'vcn'},
            {'FLOW_LOG_COMPARTMENT_ID':'compartment'},
        ):
            cfg['STATE_BUCKET'] = 'state'
            ctx=types.SimpleNamespace(Config=lambda cfg=cfg:cfg)
            with mock.patch.object(module.refresh,'main') as run,mock.patch.dict('os.environ',{},clear=True):
                result=module.handler(ctx)
            self.assertEqual(result['status_code'],400)
            run.assert_not_called()
