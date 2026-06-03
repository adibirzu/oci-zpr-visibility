import unittest

from oci_zpr_visibility.policy_parser import parse_statement


class PolicyParserTests(unittest.TestCase):
    def test_parse_attribute_relationship_statement(self):
        parsed = parse_statement("in networks:prod allow apps:web endpoints to connect to apps:db endpoints")

        self.assertEqual(parsed.action, "allow")
        self.assertEqual(parsed.network_scope, "networks:prod")
        self.assertEqual(parsed.source_attribute, "apps:web")
        self.assertEqual(parsed.destination_attribute, "apps:db")
        self.assertEqual(parsed.target_type, "attribute")
        self.assertEqual(parsed.parser_confidence, "high")

    def test_parse_cidr_target_statement(self):
        parsed = parse_statement("allow apps:ops endpoints to connect to 0.0.0.0/0")

        self.assertEqual(parsed.source_attribute, "apps:ops")
        self.assertIsNone(parsed.destination_attribute)
        self.assertEqual(parsed.target_type, "cidr")
        self.assertEqual(parsed.cidrs, ("0.0.0.0/0",))


if __name__ == "__main__":
    unittest.main()
