#!/bin/bash
set -euo pipefail
test "$(uname -m)" = x86_64
dnf install -y python3.11 python3.11-pip
cd /tmp/zpr-bundle
sha256sum --check SHA256SUMS
install -d -m 0755 /opt/zpr-visibility
python3.11 -m venv /opt/zpr-visibility/venv
/opt/zpr-visibility/venv/bin/pip install --no-index --find-links wheels --require-hashes -r requirements.lock
/opt/zpr-visibility/venv/bin/pip check
cp -a log_analytics /opt/zpr-visibility/
cp requirements.lock dependency-inventory.json sbom.cdx.json THIRD_PARTY_NOTICES.txt SHA256SUMS /opt/zpr-visibility/
install -m 0755 runtime/runtime.py /opt/zpr-visibility/runtime.py
install -m 0644 runtime/zpr-*.service runtime/zpr-*.timer /etc/systemd/system/
install -d -m 0750 /etc/zpr-visibility
systemctl enable zpr-bootstrap.service zpr-bootstrap.timer zpr-refresh.timer
/opt/zpr-visibility/venv/bin/oci-zpr-visibility --help >/dev/null
# Mandatory Oracle image sanitation must be provided by the selected base image.
command -v oci-image-cleanup >/dev/null
# The image must not carry host credentials or a machine ID into customer VMs.
install -d -m 0755 /etc/ssh/sshd_config.d
cat >/etc/ssh/sshd_config.d/60-zpr-visibility.conf <<'SSH'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
SSH
sshd -t
test "$(sshd -T | awk '$1 == "permitrootlogin" {print $2}')" = no
test "$(sshd -T | awk '$1 == "passwordauthentication" {print $2}')" = no
test "$(sshd -T | awk '$1 == "kbdinteractiveauthentication" {print $2}')" = no
rm -f /etc/ssh/ssh_host_*
: >/etc/machine-id
systemctl enable zpr-firstboot.service
# Remove only this build's uploaded payload, never operator home directories.
cd /opt/zpr-visibility
rm -rf /tmp/zpr-bundle
oci-image-cleanup -f
