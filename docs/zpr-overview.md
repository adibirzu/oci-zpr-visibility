# Zero Trust Packet Routing (ZPR) — What It Is and Why It Matters

## The problem with topology-based network security

Traditional OCI network controls — security lists, network security groups (NSGs),
route tables — are **topology-based**. Access is decided by where a workload sits
(subnet, VCN, IP/CIDR). That model is brittle and hard to reason about:

- An IP or subnet change silently breaks or widens a rule.
- Intent ("web may talk to db") is buried in scattered CIDRs and port ranges.
- A single misconfigured security list or over-broad `0.0.0.0/0` rule can open a
  path for lateral movement.
- Auditing "who is actually allowed to reach this database?" means reverse-
  engineering the whole network layout.

## What ZPR does

**Zero Trust Packet Routing** decouples network security policy from network
topology. Instead of IPs and subnets, you:

1. **Tag resources with security attributes** (key:value labels in the
   `oracle-zpr` namespace), e.g. `app:web`, `app:db`, `app:fin-network`.
2. **Write intent in human-readable policy**, e.g.
   `in app:fin-network VCN allow app:web endpoints to connect to app:db endpoints`.
3. ZPR **enforces that intent at the packet level**, independently of security
   lists, NSGs, or routes.

Key properties:

- **Deny by default.** Only explicitly allowed attribute-to-attribute paths pass.
- **Policy follows the resource, not its IP.** Re-IP a host, move a subnet — the
  attribute-based rule still holds.
- **Network misconfig cannot override intent.** Even an accidental allow-all
  security list won't grant a path ZPR policy forbids.
- **Auditable, centralized, human-readable** policy expressing security intent.
- **Defense in depth.** ZPR complements (does not replace) NSGs/security lists.

## Why this project exists — the visibility gap

ZPR *enforces* well, but day-to-day it gives limited **visibility** into:

- What policies/attributes/protected resources exist right now.
- Which real connections are being allowed vs blocked, and whether that matches
  the *intended* policy.
- Posture risks: protected resources with no matching policy, broad-CIDR
  exceptions that undo the zero-trust model, policy drift over time.

This tool closes that gap. It collects ZPR configuration, policies, security
attributes and protected resources via the OCI SDK, correlates **VCN Flow Logs**
against ZPR intent, emits normalized JSON records to **OCI Log Analytics**, and
visualizes posture, traffic, and detections on a dashboard. See
[architecture.md](architecture.md) for the end-to-end design,
[log-format.md](log-format.md) for the record schema, and
[detections.md](detections.md) for the detection rules.
