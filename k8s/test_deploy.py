import base64
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('sxdevops_k8s_deploy', Path(__file__).with_name('deploy.py'))
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def options(**overrides):
    values = dict(image='registry.test/ops/sxdevops:v2.0.0', namespace='sxdevops', storage_class=None,
                  image_pull_secret=None, upgrade=False, skip_admin=False, no_port_forward=True, port=8000,
                  kubeconfig=None, context=None, database=None)
    values.update(overrides)
    return SimpleNamespace(**values)


def resource(kind, name, **fields):
    return {'apiVersion': 'apps/v1' if kind == 'Deployment' else 'v1', 'kind': kind,
            'metadata': {'name': name, 'namespace': 'sxdevops'}, **fields}


def template(database='postgresql'):
    database_name = 'mysql' if database == 'mysql' else 'postgres'
    host_key = 'MYSQL_HOST' if database == 'mysql' else 'POSTGRES_HOST'
    resources = [resource('Namespace', 'sxdevops'), resource('ConfigMap', 'sxdevops-config',
                 data={'DATABASE_ENGINE': database, host_key: database_name})]
    resources += [resource('PersistentVolumeClaim', name, spec={'resources': {'requests': {'storage': '10Gi'}}})
                  for name in (f'{database_name}-data', 'redis-data')]
    for name in (database_name, 'redis', *deploy.APPLICATIONS):
        image = 'registry.example.com/sxdevops/sxdevops:latest' if name in deploy.APPLICATIONS else f'{name}:test'
        pod = {'containers': [{'name': name, 'image': image}]}
        if name in ('cmdb-sync-scheduler', 'aiops-chat-worker'):
            pod['initContainers'] = [{'name': 'wait-for-dependencies', 'image': 'busybox:1.36.1'},
                                     {'name': 'wait-for-schema', 'image': image}]
        resources.append(resource('Deployment', name, spec={'replicas': 1, 'template': {'spec': pod}}))
    return resources


class FakeKubectl:
    def __init__(self):
        self.objects = {('namespace', 'sxdevops'): resource('Namespace', 'sxdevops')}
        self.calls = []
        self.fail_migration = False

    def get(self, kind, name):
        return copy.deepcopy(self.objects.get((kind, name)))

    def run(self, *args, payload=None, capture=False, namespaced=True):
        self.calls.append((args, copy.deepcopy(payload)))
        if args[:2] == ('config', 'current-context'):
            return 'isolated-test-cluster'
        if args[:2] == ('create', '--dry-run=client'):
            return json.dumps({'kind': 'List', 'items': template('mysql' if any('sxdevops-mysql.yaml' in arg for arg in args) else 'postgresql')})
        if args[:2] == ('create', 'namespace'):
            self.objects[('namespace', args[2])] = resource('Namespace', args[2])
        if args[:2] == ('create', '-f'):
            if payload['kind'] == 'Secret':
                secret = copy.deepcopy(payload)
                secret['data'] = {key: base64.b64encode(value.encode()).decode() for key, value in secret.pop('stringData').items()}
                self.objects[('secret', 'sxdevops-secrets')] = secret
            else:
                self.objects[('job', 'sxdevops-migrate')] = copy.deepcopy(payload)
                return json.dumps(payload)
        if args[0] == 'apply':
            for item in payload['items']:
                kind = 'pvc' if item['kind'] == 'PersistentVolumeClaim' else item['kind'].lower()
                self.objects[(kind, item['metadata']['name'])] = copy.deepcopy(item)
        if args[0] == 'scale':
            for target in args[1:-1]:
                self.objects[('deployment', target.split('/')[1])]['spec']['replicas'] = int(args[-1].split('=')[1])
        if args[:2] == ('wait', '--for=condition=complete'):
            if self.fail_migration:
                raise deploy.DeploymentError('simulated migration failure')
            self.objects[('job', 'sxdevops-migrate')]['status'] = {'conditions': [{'type': 'Complete', 'status': 'True'}]}
        if args[0] == 'annotate':
            key, value = args[2].split('=', 1)
            self.objects[('configmap', 'sxdevops-config')]['metadata'].setdefault('annotations', {})[key] = value
        if args[0] == 'delete':
            self.objects.pop(('job', 'sxdevops-migrate'), None)
        return ''


class KubernetesInstallerTests(unittest.TestCase):
    @patch('builtins.print')
    def test_default_install_uses_pg_and_mysql_option_keeps_mysql(self, output):
        for selected, expected in [(None, 'postgresql'), ('mysql', 'mysql')]:
            client = FakeKubectl()
            deploy.Installer(options(database=selected), client).deploy()
            self.assertEqual(client.get('configmap', 'sxdevops-config')['data']['DATABASE_ENGINE'], expected)
            password = 'POSTGRES_PASSWORD' if expected == 'postgresql' else 'MYSQL_PASSWORD'
            self.assertIn(password, client.get('secret', 'sxdevops-secrets')['data'])
            job_env = client.get('job', 'sxdevops-migrate')['spec']['template']['spec']['containers'][0]['env']
            self.assertIn(password, [item['name'] for item in job_env])
            self.assertNotIn('MYSQL_ROOT_PASSWORD', [item['name'] for item in job_env])

    @patch('builtins.print')
    def test_existing_mysql_is_retained_and_cross_engine_changes_fail_before_mutations(self, output):
        client = FakeKubectl()
        deploy.Installer(options(database='mysql'), client).deploy()
        client.calls.clear()
        deploy.Installer(options(), client).deploy()
        self.assertEqual(client.get('configmap', 'sxdevops-config')['data']['DATABASE_ENGINE'], 'mysql')
        client.calls.clear()
        with self.assertRaisesRegex(deploy.DeploymentError, 'Changing database engines'):
            deploy.Installer(options(database='postgresql', upgrade=True), client).deploy()
        self.assertFalse(any(args[0] in ('apply', 'create', 'scale', 'delete') for args, _ in client.calls))

    @patch.object(deploy.subprocess, 'run')
    def test_explicit_cluster_is_used_for_every_kubectl_operation(self, run):
        run.return_value = SimpleNamespace(returncode=0, stdout='{}', stderr='')
        path = str(Path('config files/remote cluster.yaml').resolve())
        client = deploy.Kubectl('remote-namespace', path, 'remote-prod')
        operations = [
            ('get', 'namespace', 'remote-namespace'),
            ('create', '-f', '-'),
            ('apply', '-f', '-'),
            ('wait', '--for=condition=complete', 'job/sxdevops-migrate'),
            ('rollout', 'status', 'deployment/sxdevops'),
            ('exec', 'deployment/sxdevops', '--', 'python', 'manage.py', 'quickstart_admin'),
            ('port-forward', 'service/sxdevops', '8000:8000'),
        ]
        for operation in operations:
            client.run(*operation)
        client.run('create', '--dry-run=client', '-f', 'template.yaml', namespaced=False)

        for call in run.call_args_list:
            command = call.args[0]
            self.assertEqual(command[command.index('--kubeconfig') + 1], path)
            self.assertEqual(command[command.index('--context') + 1], 'remote-prod')
            self.assertNotIn('use-context', command)
        self.assertNotIn('-n', run.call_args_list[-1].args[0])

    @patch('builtins.print')
    def test_explicit_context_is_displayed_and_kept_in_followup_commands(self, output):
        client = FakeKubectl()
        configured = options(kubeconfig='remote-config.yaml', context='remote-prod')
        deploy.Installer(configured, client).deploy()
        self.assertFalse(any(args[:2] == ('config', 'current-context') for args, _ in client.calls))
        messages = '\n'.join(str(call.args[0]) for call in output.call_args_list)
        self.assertIn('Cluster context: remote-prod', messages)
        self.assertIn('--kubeconfig remote-config.yaml --context remote-prod', messages)

    def test_missing_kubeconfig_is_rejected_instead_of_using_default_cluster(self):
        with TemporaryDirectory() as folder:
            with patch('sys.stderr'), self.assertRaises(SystemExit) as error:
                deploy.parse_args([options().image, '--kubeconfig', str(Path(folder) / 'missing.yaml')])
        self.assertEqual(error.exception.code, 2)

    def test_kubeconfig_path_with_spaces_is_resolved_and_context_remains_optional(self):
        with TemporaryDirectory(prefix='sxdevops cluster ') as folder:
            config = Path(folder) / 'remote config.yaml'
            config.write_text('', encoding='utf-8')
            parsed = deploy.parse_args([options().image, '--kubeconfig', str(config)])
            self.assertEqual(parsed.kubeconfig, str(config.resolve()))
            self.assertIsNone(parsed.context)

    def test_accepts_kubectl_list_and_consecutive_json_output(self):
        source = template()
        self.assertEqual(deploy.decode_resources(json.dumps({'kind': 'List', 'items': source})), source)
        self.assertEqual(deploy.decode_resources('\n'.join(json.dumps(item) for item in source)), source)

    def test_new_secrets_are_unique_and_contain_valid_fernet_keys(self):
        first = deploy.make_secret('sxdevops')['stringData']
        second = deploy.make_secret('sxdevops')['stringData']
        self.assertTrue(all(first[key] != second[key] for key in deploy.SECRET_KEYS))
        self.assertEqual(len(base64.urlsafe_b64decode(first['CMDB_PASSWORD_ENCRYPTION_KEY'])), 32)

    def test_render_updates_all_five_app_images_and_preserves_storage_and_config(self):
        claim = resource('PersistentVolumeClaim', 'postgres-data', spec={'storageClassName': 'existing', 'volumeName': 'original-pv',
                                                                   'resources': {'requests': {'storage': '80Gi'}}})
        config = resource('ConfigMap', 'sxdevops-config', data={'POSTGRES_HOST': 'external-db', 'ALLOWED_HOSTS': 'portal.test'})
        rendered = deploy.render_resources(template(), options(namespace='another'), config, {'postgres-data': claim})
        images = [container['image'] for item in rendered if item['kind'] == 'Deployment'
                  for container in item['spec']['template']['spec']['containers'] + item['spec']['template']['spec'].get('initContainers', [])]
        self.assertEqual(images.count(options().image), 5)
        self.assertIn('busybox:1.36.1', images)
        self.assertTrue(all(item['metadata']['namespace'] == 'another' for item in rendered))
        self.assertEqual(next(item for item in rendered if item['metadata']['name'] == 'postgres-data')['spec'], claim['spec'])
        self.assertEqual(next(item for item in rendered if item['kind'] == 'ConfigMap')['data']['POSTGRES_HOST'], 'external-db')
        with self.assertRaises(deploy.DeploymentError):
            deploy.render_resources(template(), options(storage_class='replacement'), existing_pvcs={'postgres-data': claim})

    @patch('builtins.print')
    def test_first_install_migrates_before_starting_apps_and_excludes_root_password(self, output):
        client = FakeKubectl()
        deploy.Installer(options(), client).deploy()
        calls = client.calls
        migration_index = next(i for i, (args, _) in enumerate(calls) if args[:2] == ('wait', '--for=condition=complete'))
        start_index = next(i for i, (args, _) in enumerate(calls) if args[0] == 'scale' and args[-1] == '--replicas=1')
        self.assertLess(migration_index, start_index)
        job = client.get('job', 'sxdevops-migrate')
        container = job['spec']['template']['spec']['containers'][0]
        self.assertNotIn('MYSQL_ROOT_PASSWORD', [item['name'] for item in container['env']])
        self.assertIn('seed_templates', container['command'][-1])
        self.assertEqual(client.get('configmap', 'sxdevops-config')['metadata']['annotations'][deploy.INITIALIZED], 'true')

    @patch('builtins.print')
    def test_rerun_keeps_secrets_config_and_running_services(self, output):
        client = FakeKubectl()
        installer = deploy.Installer(options(), client)
        installer.deploy()
        original = copy.deepcopy(client.objects)
        client.calls.clear()
        installer.deploy()
        self.assertEqual(client.objects, original)
        self.assertFalse(any(args[0] in ('apply', 'scale', 'delete') for args, _ in client.calls))
        self.assertFalse(any(payload and payload.get('kind') == 'Secret' for _, payload in client.calls))

    @patch('builtins.print')
    def test_missing_secret_with_existing_data_stops_without_creating_new_keys(self, output):
        client = FakeKubectl()
        client.objects[('pvc', 'postgres-data')] = resource('PersistentVolumeClaim', 'postgres-data', spec={})
        with self.assertRaisesRegex(deploy.DeploymentError, 'Restore the original secret'):
            deploy.Installer(options(), client).deploy()
        self.assertFalse(any(payload for _, payload in client.calls))

    @patch('builtins.print')
    def test_version_update_requires_upgrade_and_stops_old_writers_before_migration(self, output):
        client = FakeKubectl()
        deploy.Installer(options(), client).deploy()
        original_secret = client.get('secret', 'sxdevops-secrets')
        changed = options(image='registry.test/ops/sxdevops:v2.0.1')
        client.calls.clear()
        with self.assertRaisesRegex(deploy.DeploymentError, '--upgrade'):
            deploy.Installer(changed, client).deploy()
        self.assertFalse(any(args[0] == 'scale' for args, _ in client.calls))
        changed.upgrade = True
        deploy.Installer(changed, client).deploy()
        stop = next(i for i, (args, _) in enumerate(client.calls) if args[0] == 'scale' and args[-1] == '--replicas=0')
        apply = next(i for i, (args, _) in enumerate(client.calls) if args[0] == 'apply')
        self.assertLess(stop, apply)
        self.assertEqual(client.get('secret', 'sxdevops-secrets'), original_secret)

    @patch('builtins.print')
    def test_failed_migration_keeps_application_writers_stopped(self, output):
        client = FakeKubectl()
        client.fail_migration = True
        with self.assertRaises(deploy.DeploymentError):
            deploy.Installer(options(), client).deploy()
        self.assertTrue(all(client.get('deployment', name)['spec']['replicas'] == 0 for name in deploy.APPLICATIONS))
        self.assertFalse(any(args[0] == 'exec' for args, _ in client.calls))

    @patch('builtins.print')
    def test_interrupted_install_reuses_running_migration_and_initializes_templates(self, output):
        client = FakeKubectl()
        client.fail_migration = True
        with self.assertRaises(deploy.DeploymentError):
            deploy.Installer(options(), client).deploy()
        client.fail_migration = False
        client.calls.clear()
        deploy.Installer(options(), client).deploy()
        self.assertFalse(any(payload and payload.get('kind') == 'Job' for _, payload in client.calls))
        self.assertEqual(client.get('configmap', 'sxdevops-config')['metadata']['annotations'][deploy.INITIALIZED], 'true')

    def test_registry_credentials_are_shared_with_migration_and_schema_containers(self):
        configured = options(image_pull_secret='private-registry')
        rendered = deploy.render_resources(template(), configured)
        for item in rendered:
            if item['kind'] == 'Deployment' and item['metadata']['name'] in deploy.APPLICATIONS:
                self.assertEqual(item['spec']['template']['spec']['imagePullSecrets'], [{'name': 'private-registry'}])
        job = deploy.migration_job(configured, False)
        self.assertEqual(job['spec']['template']['spec']['imagePullSecrets'], [{'name': 'private-registry'}])


if __name__ == '__main__':
    unittest.main()
