"""Normalization helpers for OCI ZPR security attributes."""

from __future__ import annotations

from typing import Any


def extract_attribute_value(value: Any) -> Any:
    if isinstance(value, dict):
        if "value" in value:
            return value["value"]
        if "values" in value:
            return value["values"]
    return value


def flatten_security_attributes(security_attributes: dict[str, Any] | None) -> dict[str, str]:
    """Flatten OCI's nested securityAttributes shape into canonical strings.

    OCI resources commonly expose security attributes as:
    {"namespace": {"attribute": {"value": "prod", "mode": "enforce"}}}

    The returned keys are "namespace.attribute" and values are strings.
    """
    if not security_attributes:
        return {}

    flattened: dict[str, str] = {}
    for namespace, attributes in security_attributes.items():
        if not isinstance(attributes, dict):
            flattened[str(namespace)] = str(extract_attribute_value(attributes))
            continue
        for key, raw_value in attributes.items():
            value = extract_attribute_value(raw_value)
            flattened[f"{namespace}.{key}"] = str(value)
    return flattened


def render_attribute(namespace_key: str, value: str) -> str:
    return f"{namespace_key}={value}"


def render_attributes(attributes: dict[str, str]) -> list[str]:
    return [render_attribute(key, value) for key, value in sorted(attributes.items())]


def attribute_matches_reference(attributes: dict[str, str], reference: str) -> bool:
    """Match policy references such as apps:web, apps.role=web, or apps.role:web."""
    normalized = reference.strip()
    if not normalized:
        return False

    if "=" in normalized:
        key, value = normalized.split("=", 1)
        return attributes.get(key) == value

    if ":" in normalized:
        left, value = normalized.rsplit(":", 1)
        if attributes.get(left) == value:
            return True
        # Match when the reference omits the namespace (e.g. policy "app:web")
        # but the resource attribute key is namespace-qualified ("oracle-zpr.app"):
        # compare the local key segment, or the leading namespace segment.
        return any(
            (k == left or k.rsplit(".", 1)[-1] == left or k.split(".", 1)[0] == left) and v == value
            for k, v in attributes.items()
        )

    return normalized in attributes or normalized in attributes.values()
