import unittest

from oci_zpr_visibility.security_attributes import (
    attribute_matches_reference,
    extract_attribute_value,
    flatten_security_attributes,
    render_attribute,
    render_attributes,
)


class ExtractValueTests(unittest.TestCase):
    def test_dict_with_value(self):
        self.assertEqual(extract_attribute_value({"value": "prod", "mode": "enforce"}), "prod")

    def test_dict_with_values(self):
        self.assertEqual(extract_attribute_value({"values": ["a", "b"]}), ["a", "b"])

    def test_plain_passthrough(self):
        self.assertEqual(extract_attribute_value("web"), "web")


class FlattenTests(unittest.TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(flatten_security_attributes(None), {})

    def test_nested_namespace_attribute(self):
        raw = {"apps": {"role": {"value": "web", "mode": "enforce"}}}
        self.assertEqual(flatten_security_attributes(raw), {"apps.role": "web"})

    def test_non_dict_attribute_value(self):
        self.assertEqual(flatten_security_attributes({"apps": "web"}), {"apps": "web"})


class RenderTests(unittest.TestCase):
    def test_render_attribute(self):
        self.assertEqual(render_attribute("apps.role", "web"), "apps.role=web")

    def test_render_attributes_sorted(self):
        self.assertEqual(
            render_attributes({"b.k": "2", "a.k": "1"}),
            ["a.k=1", "b.k=2"],
        )


class MatchReferenceTests(unittest.TestCase):
    def setUp(self):
        self.attrs = {"apps.role": "web", "tier": "prod"}

    def test_empty_reference(self):
        self.assertFalse(attribute_matches_reference(self.attrs, "  "))

    def test_equals_form(self):
        self.assertTrue(attribute_matches_reference(self.attrs, "apps.role=web"))
        self.assertFalse(attribute_matches_reference(self.attrs, "apps.role=db"))

    def test_colon_exact_key(self):
        self.assertTrue(attribute_matches_reference(self.attrs, "tier:prod"))

    def test_colon_namespace_prefix(self):
        self.assertTrue(attribute_matches_reference(self.attrs, "apps:web"))
        self.assertFalse(attribute_matches_reference(self.attrs, "apps:db"))

    def test_colon_matches_namespace_qualified_key(self):
        # Real resource attrs are keyed 'oracle-zpr.app'; the policy reference
        # 'app:web' omits the namespace and must still match on the local key.
        attrs = {"oracle-zpr.app": "web"}
        self.assertTrue(attribute_matches_reference(attrs, "app:web"))
        self.assertFalse(attribute_matches_reference(attrs, "app:db"))
        self.assertTrue(attribute_matches_reference(attrs, "oracle-zpr.app:web"))

    def test_bare_membership(self):
        self.assertTrue(attribute_matches_reference(self.attrs, "apps.role"))
        self.assertTrue(attribute_matches_reference(self.attrs, "web"))
        self.assertFalse(attribute_matches_reference(self.attrs, "absent"))


if __name__ == "__main__":
    unittest.main()
