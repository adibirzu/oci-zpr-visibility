"""Guard the declarative identity boundary; live IAM evaluation remains separate."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).parents[1]


class FunctionPrincipalScopeTests(unittest.TestCase):
    def test_function_grants_reference_one_exact_function_not_its_compartment(self):
        source=(ROOT/'orm/functions.tf').read_text()
        block=source.split('resource "oci_identity_dynamic_group" "function" {',1)[1].split('\n}',1)[0]
        rule=re.search(r'matching_rule\s*=\s*"([^\n]+)"',block).group(1)
        self.assertEqual(rule,"ALL {resource.type = 'fnfunc', resource.id = '${oci_functions_function.refresh[0].id}'}")
        self.assertNotIn('resource.compartment.id',rule)
        for kind in ('oci_identity_dynamic_group','oci_identity_policy'):
            boundary=source.split(f'resource "{kind}" "function" {{',1)[1].split('\n}',1)[0]
            self.assertRegex(boundary,r'count\s*=\s*local.enable_function && var.function_image != "" \? 1 : 0')
