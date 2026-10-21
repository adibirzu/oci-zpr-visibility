"""Render the actual Terraform template and execute only its Python argv wrapper."""
import base64
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('terraform'), 'Terraform needed for template render contract')
class ControllerRenderTests(unittest.TestCase):
    def test_inventory_only_scope_survives_template_without_shell_execution(self):
        scope = "scope'with-text"
        config = {'region': 'test-region', 'state_bucket': 'state', 'log_group_name': 'group',
                  'log_group_compartment_id': 'log-group-compartment', 'compartment_ids': [scope],
                  'flow_compartment_id': 'compartment', 'flow_log_group_id': '',
                  'flow_log_id': '', 'flow_vcn_id': 'vcn'}
        params = dict(region='test-region', state_bucket='state', log_group_name='group',
                      pkg_bucket='package', pkg_object='package.tar',
                      pkg_sha256='0'*64, bootstrap_requirements='example==1 --hash=sha256:'+'0'*64,
                      flow_compartment_id='compartment',
                      log_group_compartment_id='log-group-compartment',
                      dashboard_compartment_id='dashboard-compartment',
                      refresh_config_b64=base64.b64encode(json.dumps(config).encode()).decode())
        expression = 'templatefile(' + json.dumps(str(ROOT/'orm/cloudinit/controller.sh.tftpl')) + ', ' + json.dumps(params) + ')'
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(['terraform', f'-chdir={directory}', 'console', '-no-color'],
                                    input=expression+'\n', text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Console emits a heredoc for multiline strings.
        lines = result.stdout.splitlines()
        rendered = '\n'.join(lines[1:-1])
        wrapper = rendered.split("<<'WRAPPER'\n", 1)[1].split('\nWRAPPER', 1)[0]
        refresh = types.SimpleNamespace(main=mock.Mock(return_value=0))
        with mock.patch.dict('sys.modules', {'oci_zpr_visibility': types.SimpleNamespace(refresh=refresh)}):
            with self.assertRaises(SystemExit):
                exec(compile(wrapper, '<rendered wrapper>', 'exec'), {})
        argv = refresh.main.call_args.args[0]
        self.assertIn(scope, argv)
        self.assertIn('--log-group-name', argv)
        self.assertIn('log-group-compartment', argv)
        self.assertNotIn('--flow-log-id', argv)
        self.assertIn('--log-group-compartment-id', argv)


def test_recovery_schedule_is_installed_before_initial_provider_calls():
    template = (ROOT/'orm/cloudinit/controller.sh.tftpl').read_text()
    assert template.index('cat >/etc/cron.d/zpr-refresh') < template.index('$BIN provision-la')
    assert 'systemctl enable --now crond' in template
    assert 'flock -n' in template


def test_controller_wrapper_rejects_missing_empty_and_blank_scope_before_refresh():
    template = (ROOT/'orm/cloudinit/controller.sh.tftpl').read_text()
    wrapper = template.split("<<'WRAPPER'\n", 1)[1].split('\nWRAPPER', 1)[0]
    for scopes in (None, [], [''], ['  '], ['valid', None], 'valid'):
        encoded = base64.b64encode(json.dumps({'compartment_ids': scopes}).encode()).decode()
        rendered = wrapper.replace('${refresh_config_b64}', encoded)
        refresh = types.SimpleNamespace(main=mock.Mock())
        with mock.patch.dict('sys.modules', {'oci_zpr_visibility': types.SimpleNamespace(refresh=refresh)}):
            with __import__('pytest').raises(SystemExit, match='explicit collection scope'):
                exec(compile(rendered, '<controller wrapper>', 'exec'), {})
        refresh.main.assert_not_called()


def test_archive_digest_failure_prevents_writing_or_extracting_package(tmp_path):
    template = (ROOT/'orm/cloudinit/controller.sh.tftpl').read_text()
    block = template.split("/opt/zpr/venv/bin/python - <<'PY'\n", 1)[1].split('\nPY', 1)[0]
    payload = b'expected collector archive'
    target = tmp_path/'package.tgz'
    block = block.replace('${pkg_sha256}', hashlib.sha256(payload).hexdigest()).replace('/tmp/pkg.tgz', str(target))
    client = types.SimpleNamespace(get_namespace=lambda: types.SimpleNamespace(data='namespace'),
                                   get_object=lambda *a: types.SimpleNamespace(data=types.SimpleNamespace(content=b'tampered')))
    fake_oci = types.SimpleNamespace(auth=types.SimpleNamespace(signers=types.SimpleNamespace(InstancePrincipalsSecurityTokenSigner=lambda: object())),
                                    object_storage=types.SimpleNamespace(ObjectStorageClient=lambda *a, **k: client))
    with mock.patch.dict('sys.modules', {'oci': fake_oci}):
        with __import__('pytest').raises(SystemExit, match='digest mismatch'):
            exec(compile(block, '<download verification>', 'exec'), {})
    assert not target.exists()


def test_bootstrap_uses_hashed_dependencies_and_offline_collector_install():
    template = (ROOT/'orm/cloudinit/controller.sh.tftpl').read_text()
    assert '--require-hashes' in template
    assert '--no-index --no-deps' in template
    assert 'install --upgrade' not in template
    lock = (ROOT/'orm/bootstrap-requirements.txt').read_text()
    assert all('==' in row and '--hash=sha256:' in row for row in lock.splitlines() if row and not row.startswith('#'))
