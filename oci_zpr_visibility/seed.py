#!/usr/bin/env python3
"""Seed a demonstration target with a ZPR rule and security attributes.

Creates security attributes in the default `oracle-zpr` namespace and a ZPR
policy so `collect` returns real policy/finding inventory. Idempotent.

Usage: .venv/bin/python scripts/seed_demo.py --profile <PROFILE> --region <REGION>
"""
from __future__ import annotations

import argparse
import sys
import time

import oci

# Security attribute KEY (oracle-zpr namespace). Values (web/db/ops/fin-network)
# are free-form and referenced in statements as app:<value>.
ATTRIBUTES = ["app"]
POLICY_NAME = "zpr-visibility-demo"
STATEMENTS = [
    "in app:fin-network VCN allow app:web endpoints to connect to app:db endpoints",
    # Broad-CIDR exception (triggers the broad_cidr_exception finding):
    "in app:fin-network VCN allow app:ops endpoints to connect to '10.0.0.0/8'",
]


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", default="DEFAULT")
    p.add_argument("--region", default=None)
    args = p.parse_args(argv)

    cfg = oci.config.from_file(profile_name=args.profile)
    if args.region:
        # Without --region the profile's own region stands; overwriting it with
        # None would fail validate_config, which requires `region`.
        cfg["region"] = args.region
    oci.config.validate_config(cfg)
    tid = cfg["tenancy"]
    sa = oci.security_attribute.SecurityAttributeClient(cfg)
    zpr = oci.zpr.ZprClient(cfg)
    m_sa = oci.security_attribute.models
    m_zpr = oci.zpr.models

    # 1. oracle-zpr namespace
    ns = next(
        n for n in oci.pagination.list_call_get_all_results(
            sa.list_security_attribute_namespaces, compartment_id=tid, compartment_id_in_subtree=True
        ).data if n.name == "oracle-zpr"
    )
    print(f"namespace: {ns.name} ({ns.id[-12:]})")

    # 2. attributes (idempotent)
    existing = {
        a.name for a in oci.pagination.list_call_get_all_results(
            sa.list_security_attributes, security_attribute_namespace_id=ns.id
        ).data
    }
    for attr in ATTRIBUTES:
        if attr in existing:
            print(f"  attribute exists: {attr}")
            continue
        sa.create_security_attribute(
            security_attribute_namespace_id=ns.id,
            create_security_attribute_details=m_sa.CreateSecurityAttributeDetails(
                name=attr, description=f"ZPR visibility demo attribute: {attr}"
            ),
        )
        print(f"  attribute created: {attr}")
    # wait until all visible
    for _ in range(30):
        names = {
            a.name for a in oci.pagination.list_call_get_all_results(
                sa.list_security_attributes, security_attribute_namespace_id=ns.id
            ).data
        }
        if set(ATTRIBUTES) <= names:
            break
        time.sleep(5)

    # 3. ZPR policy (idempotent on name)
    policies = oci.pagination.list_call_get_all_results(
        zpr.list_zpr_policies, compartment_id=tid
    ).data
    if any(getattr(pol, "name", None) == POLICY_NAME for pol in policies):
        print(f"policy exists: {POLICY_NAME}")
        return 0
    resp = zpr.create_zpr_policy(
        create_zpr_policy_details=m_zpr.CreateZprPolicyDetails(
            compartment_id=tid, name=POLICY_NAME,
            description="ZPR visibility demo policy (web->db + broad-CIDR exception).",
            statements=STATEMENTS,
        )
    )
    print(f"policy create accepted: {POLICY_NAME} (opc-work-request: "
          f"{resp.headers.get('opc-work-request-id', 'n/a')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
