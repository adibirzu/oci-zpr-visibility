from pathlib import Path


TEMPLATE = Path(__file__).parents[1] / "orm" / "cloudinit" / "controller.sh.tftpl"


def test_controller_bootstrap_fails_closed_and_installs_supervised_refresh():
    content = TEMPLATE.read_text()

    assert "set -euo pipefail" in content
    assert "--flow-log-id ${flow_log_id} || true" not in content
    assert "zpr-refresh.service" in content
    assert "zpr-refresh.timer" in content
    assert "/usr/bin/flock -n /run/zpr-visibility-refresh.lock" in content
    assert "systemctl enable --now zpr-refresh.timer" in content
    assert "initial-refresh-succeeded" in content
    assert content.index("umask 077") < content.index("exec > /var/log/zpr-controller.log")
    assert "chmod 0600 /var/log/zpr-controller.log" in content
    assert "requirements-build.lock" in content


def test_dashboard_and_refresh_share_deployment_scope_and_durable_assets():
    content = TEMPLATE.read_text()
    assert "controller_runtime bootstrap" in content
    assert "${runtime_config}" in content
    assert "/tmp/pkg/" not in content
    assert "OCI_ZPR_DASHBOARD_PATH=/opt/zpr-visibility/package/" in content
    assert "Restart=on-failure" in content
    assert content.index("cat >/usr/local/sbin/zpr-bootstrap") < content.index("dnf install")
    assert "--require-hashes --only-binary=:all:" in content
    assert "package checksum mismatch" in content
    assert "supervision installed; readiness remains pending" in content


def test_changed_package_requires_controller_first_boot_again():
    controller = TEMPLATE.parent.parent / "controller.tf"
    assert "replace_triggered_by = [oci_objectstorage_object.pkg[0]]" in controller.read_text()
