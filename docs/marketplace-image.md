# Compute image delivery

This is an independent accelerator. Local packaging is not Oracle Marketplace
acceptance. The image pipeline is a candidate, not a submitted or launch-tested image.

## Local packaging

Use Python 3.11, the hash-pinned `requirements-build.lock`, and Packer 1.16.1
with Oracle plugin 1.1.2. Download x86_64/manylinux2014 wheels matching
`requirements-runtime.lock` into a private wheelhouse, then build a new
(nonexistent) output directory. For a restricted workstation with an unwritable
pip cache, set `PIP_NO_CACHE_DIR=1`; a cache warning alone is not a download
failure.

```bash
PIP_NO_CACHE_DIR=1 python3.11 -m pip download --require-hashes --only-binary=:all: \
  --implementation cp --python-version 311 --abi cp311 \
  --platform manylinux2014_x86_64 --dest <PRIVATE_WHEELHOUSE> \
  -r requirements-runtime.lock
PIP_NO_CACHE_DIR=1 python3.11 scripts/build_image_bundle.py --wheelhouse <PRIVATE_WHEELHOUSE> --output <NEW_BUNDLE_DIRECTORY>
PACKER_PLUGIN_PATH=<WRITABLE_PLUGIN_DIRECTORY> packer init image/zpr.pkr.hcl
PACKER_PLUGIN_PATH=<WRITABLE_PLUGIN_DIRECTORY> packer validate -var-file=<PRIVATE_BUILD_INPUTS> image/zpr.pkr.hcl
```

The builder rejects missing, extra, wrong-version or hash-mismatched runtime
wheels and components without license metadata. The payload includes the
Apache-2.0 application wheel, SHA-256 requirement lock, checksums, CycloneDX
dependency SBOM, bundled license texts, dashboard assets, and runtime. Build
tools are separately pinned and are not shipped in the runtime image.
The fixed `SOURCE_DATE_EPOCH` default makes wheel timestamps repeatable; set an
immutable release timestamp when producing release artifacts. Compare hashes
from two builds before labeling a release reproducible.

The image installs dependencies offline and runs `pip check`. Only build-time
OS packages use Oracle Linux repositories. Marketplace first boot must not
download the application or dependencies. Customer cloud-init writes only
`/etc/zpr-visibility/config.json` (mode 0600) with exactly these string keys:
`region`, `compartment_id`, `installation_id`, `state_bucket`, `log_group_name`,
`flow_log_group_id`, `flow_log_id`. It uses the same tested bootstrap/readiness
implementation as the Resource Manager controller. There are no API keys in
that configuration; instance principals supply identity.

Marketplace launch user data must materialize that file before starting the
service. Replace each placeholder with a customer-selected value:

```yaml
#cloud-config
write_files:
  - path: /etc/zpr-visibility/config.json
    owner: root:root
    permissions: "0600"
    content: |
      {"region":"<REGION>","compartment_id":"<COMPARTMENT_OCID>","installation_id":"<INSTALLATION_ID>","state_bucket":"<OWNED_STATE_BUCKET>","log_group_name":"<OWNED_LOG_GROUP>","flow_log_group_id":"<FLOW_LOG_GROUP_OCID>","flow_log_id":"<FLOW_LOG_OCID>"}
runcmd:
  - [systemctl, daemon-reload]
  - [systemctl, start, zpr-bootstrap.service]
```

The image build disables root/password SSH, validates the effective sshd
settings, removes build-time host keys and machine-id, and enables a
first-boot unit to generate unique machine identity and SSH host keys before
sshd starts. These controls still need validation on the actual built image.
Bootstrap provisions LA content and dashboards in the configured compartment,
then requires a successful initial refresh. A bounded systemd retry timer
recovers failed initial provisioning; a separate systemd timer refreshes every
15 minutes with overlap protection. Indexed freshness still needs a separate
scoped `validate-dashboards --expected-run-id` acceptance check.

## Live build gate

The Packer template defaults to the named OCI config profile and also supports
instance-principal authentication when Packer itself runs on OCI Compute. CI
uses a generated, disposable signing key and synthetic profile for offline
template validation; it does not authenticate to OCI or launch a builder.

The Packer builder is private, x86_64, and disables IMDSv1. The operator must
provide an approved private SSH route to the configured subnet, validated
shape/image capacity, exact build inputs, reviewed resource costs, and cleanup
authority for Packer's temporary instance/boot volume. Do not add public SSH
ingress to make a build work. No builder was launched during local validation.

Use the Packer archive matching the validation host's operating system and
architecture, and verify it against HashiCorp's published checksum file. CI
uses the Linux AMD64 archive; it cannot run on macOS. Use a platform-specific
`PACKER_PLUGIN_PATH` when initializing plugins. A `cannot execute binary file`
error from the wrong archive is a host/tool mismatch, not a Packer-template
failure.

The offline image payload was built and hash-checked locally on October 1,
2026 (24 runtime/application components; no missing license metadata). Packer
1.16.1 and Oracle plugin 1.1.2 were checksum-verified in a private temporary
directory, and `packer validate` passed. No OCI builder was launched, so no
image has been built or launched. CI builds/uploads the payload and validates
the Packer template; it does not submit an image to Marketplace.

## Release gates still required

- Source ownership confirmation and legal review of Apache-2.0/dependency
  redistribution terms.
- Dependency/OS vulnerability scan and review of the actual built image.
- Verified image sanitation, unique SSH host keys on first launch, disabled
  password/root SSH login, no build credentials/logs, and cloud-init customer keys.
- Launch smoke test with IMDSv2, instance principal, fresh collection, indexing,
  dashboard queries, scheduled refresh and restart recovery.
- Immutable image checksums/version manifest and approved-image/subscription
  bindings in a separate Marketplace stack entrypoint.
- Publisher eligibility, submission materials, and Oracle review/acceptance.

Official requirements: [Compute images](https://docs.oracle.com/en-us/iaas/Content/Marketplace/app-publisher-guidelines-images.htm)
and [Marketplace stacks](https://docs.oracle.com/en-us/iaas/Content/Marketplace/app-publisher-guidelines-stacks.htm).
