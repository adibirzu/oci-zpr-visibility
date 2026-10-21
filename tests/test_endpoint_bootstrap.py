from pathlib import Path


def test_endpoint_bootstrap_content_changes_are_visible_as_replacements():
    terraform = (Path(__file__).parents[1] / "orm" / "compute.tf").read_text()
    assert 'resource "terraform_data" "endpoint_bootstrap"' in terraform
    assert "sha256(local.endpoint_bootstrap_scripts[each.key])" in terraform
    assert "replace_triggered_by = [terraform_data.endpoint_bootstrap[each.key].input]" in terraform


def test_endpoint_bootstrap_keeps_allowed_and_blocked_application_paths():
    terraform = (Path(__file__).parents[1] / "orm" / "compute.tf").read_text()
    assert "python3 -m http.server" in terraform
    assert 'http://${endpoint.peer}:${endpoint.port}/' in terraform
    assert "intentional blocked-path canary" in terraform
    assert "Flow-log" in terraform and "action is observed independently" in terraform
