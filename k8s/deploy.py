#!/usr/bin/env python3
"""Deploy SXDevOps using kubectl and the Python standard library."""
import argparse
import base64
import copy
import json
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import sys


APPLICATIONS = ('sxdevops', 'cmdb-sync-scheduler', 'aiops-chat-worker')
SECRET_KEYS = ('POSTGRES_PASSWORD', 'SECRET_KEY', 'CMDB_PASSWORD_ENCRYPTION_KEY')
TEMPLATE = Path(__file__).with_name('sxdevops.yaml')
INITIALIZED = 'sxdevops.io/templates-initialized'


class DeploymentError(Exception):
    pass


def kubectl_command(options, *args, namespaced=True):
    command = ['kubectl']
    if options.kubeconfig:
        command += ['--kubeconfig', options.kubeconfig]
    if options.context:
        command += ['--context', options.context]
    if namespaced:
        command += ['-n', options.namespace]
    return [*command, *args]


def command_text(command):
    if sys.platform == 'win32':
        return subprocess.list2cmdline(command)
    return ' '.join(shlex.quote(argument) for argument in command)


def decode_resources(output):
    """kubectl versions may print either a List or consecutive JSON objects."""
    decoder = json.JSONDecoder()
    resources = []
    remaining = output.strip()
    while remaining:
        resource, end = decoder.raw_decode(remaining)
        resources.extend(resource['items'] if resource.get('kind') == 'List' else [resource])
        remaining = remaining[end:].lstrip()
    return resources


def database_secret_keys(database='postgresql', include_root=True):
    keys = ['POSTGRES_PASSWORD'] if database == 'postgresql' else ['MYSQL_PASSWORD']
    if database == 'mysql' and include_root:
        keys.append('MYSQL_ROOT_PASSWORD')
    return (*keys, 'SECRET_KEY', 'CMDB_PASSWORD_ENCRYPTION_KEY')


def make_secret(namespace, database='postgresql'):
    return {
        'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque',
        'metadata': {'name': 'sxdevops-secrets', 'namespace': namespace},
        'stringData': {
            **{key: secrets.token_hex(32) for key in database_secret_keys(database) if key.endswith('PASSWORD')},
            'SECRET_KEY': secrets.token_hex(48),
            'CMDB_PASSWORD_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii'),
        },
    }


def validate_secret(secret, database='postgresql'):
    data = secret.get('data', {})
    if any(not data.get(key) for key in database_secret_keys(database)):
        raise DeploymentError('Existing sxdevops-secrets is incomplete. Restore the original secret; it will not be replaced.')
    try:
        key = base64.b64decode(data['CMDB_PASSWORD_ENCRYPTION_KEY'], validate=True)
        if len(base64.b64decode(key, altchars=b'-_', validate=True)) != 32:
            raise ValueError('Invalid Fernet key length')
    except (ValueError, TypeError) as exc:
        raise DeploymentError('Existing CMDB encryption key is invalid. Restore the original key before continuing.') from exc


def render_resources(resources, options, existing_config=None, existing_pvcs=None, existing_deployments=None):
    rendered = []
    existing_pvcs = existing_pvcs or {}
    existing_deployments = existing_deployments or {}
    for original in resources:
        resource = copy.deepcopy(original)
        kind = resource['kind']
        metadata = resource['metadata']
        name = metadata['name']
        if kind in ('Namespace', 'Secret'):
            continue
        metadata['namespace'] = options.namespace
        if kind == 'ConfigMap' and name == 'sxdevops-config' and existing_config:
            resource['data'].update(existing_config.get('data', {}))
            metadata['annotations'] = existing_config.get('metadata', {}).get('annotations', {}).copy()
            metadata['annotations'].pop('kubectl.kubernetes.io/last-applied-configuration', None)
        if kind == 'PersistentVolumeClaim':
            existing = existing_pvcs.get(name)
            if existing:
                if options.storage_class and existing['spec'].get('storageClassName') != options.storage_class:
                    raise DeploymentError(f'{name} already exists with another StorageClass; its storage will not be replaced.')
                # Do not shrink, rebind or change an existing claim.
                resource['spec'] = copy.deepcopy(existing['spec'])
            elif options.storage_class:
                resource['spec']['storageClassName'] = options.storage_class
        if kind == 'Deployment' and name in APPLICATIONS:
            resource['spec']['replicas'] = 0
            pod = resource['spec']['template']['spec']
            if options.image_pull_secret:
                pod['imagePullSecrets'] = [{'name': options.image_pull_secret}]
            elif existing_deployments.get(name):
                previous = existing_deployments[name]['spec']['template']['spec']
                if previous.get('imagePullSecrets'):
                    pod['imagePullSecrets'] = copy.deepcopy(previous['imagePullSecrets'])
            for container in pod.get('containers', []) + pod.get('initContainers', []):
                if container['image'].startswith('registry.example.com/sxdevops/sxdevops:'):
                    container['image'] = options.image
            for container in pod['containers']:
                environment = {item['name']: item for item in container.get('env', [])}
                for key in ('SXDEVOPS_MIGRATE', 'SXDEVOPS_SEED_DATA', 'SXDEVOPS_SEED_TEMPLATES'):
                    environment[key] = {'name': key, 'value': '0'}
                container['env'] = list(environment.values())
        rendered.append(resource)
    return rendered


def migration_job(options, seed_templates, pull_secrets=None):
    commands = ['python manage.py migrate --noinput']
    if seed_templates:
        commands.append('python manage.py seed_templates')
    pod = {
        'restartPolicy': 'Never',
        'containers': [{
            'name': 'migrate', 'image': options.image, 'imagePullPolicy': 'Always',
            'command': ['/bin/sh', '-ec', '\n'.join(commands)],
            'envFrom': [{'configMapRef': {'name': 'sxdevops-config'}}],
            'env': [
                {'name': key, 'valueFrom': {'secretKeyRef': {'name': 'sxdevops-secrets', 'key': key}}}
                for key in database_secret_keys(options.database or 'postgresql', include_root=False)
            ],
        }],
    }
    if options.image_pull_secret:
        pod['imagePullSecrets'] = [{'name': options.image_pull_secret}]
    elif pull_secrets:
        pod['imagePullSecrets'] = copy.deepcopy(pull_secrets)
    return {
        'apiVersion': 'batch/v1', 'kind': 'Job',
        'metadata': {'name': 'sxdevops-migrate', 'namespace': options.namespace},
        'spec': {
            'backoffLimit': 0, 'activeDeadlineSeconds': 600, 'ttlSecondsAfterFinished': 86400,
            'template': {'spec': pod},
        },
    }


class Kubectl:
    def __init__(self, namespace, kubeconfig=None, context=None):
        self.namespace = namespace
        self.kubeconfig = kubeconfig
        self.context = context

    def run(self, *args, payload=None, capture=False, namespaced=True):
        command = kubectl_command(self, *args, namespaced=namespaced)
        result = subprocess.run(
            command,
            input=json.dumps(payload) if payload is not None else None,
            text=True, encoding='utf-8', stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
        if result.returncode:
            detail = result.stderr.strip() if capture else 'See the kubectl error above.'
            raise DeploymentError(f'{command_text(command)} failed. {detail}')
        return result.stdout.strip() if capture else ''

    def get(self, kind, name):
        output = self.run('get', kind, name, '--ignore-not-found', '-o', 'json', capture=True)
        return json.loads(output) if output else None


class Installer:
    def __init__(self, options, client=None):
        self.options = options
        self.client = client or Kubectl(options.namespace, options.kubeconfig, options.context)

    def finish(self):
        client = self.client
        for name in APPLICATIONS:
            client.run('rollout', 'status', f'deployment/{name}', '--timeout=600s')
        if not self.options.skip_admin:
            flags = ['-it'] if sys.stdin.isatty() else []
            client.run('exec', *flags, 'deployment/sxdevops', '--', 'python', 'manage.py', 'quickstart_admin')
        if self.options.no_port_forward:
            forward = kubectl_command(self.options, 'port-forward', 'service/sxdevops', f'{self.options.port}:8000')
            print(f'Deployment ready. To open a local tunnel: {command_text(forward)}', flush=True)
            return
        print(f'Open http://127.0.0.1:{self.options.port}/login after port forwarding starts.', flush=True)
        print('Keep this terminal open. Ctrl+C stops only the local tunnel.', flush=True)
        client.run('port-forward', '--address=127.0.0.1', 'service/sxdevops', f'{self.options.port}:8000')

    def deploy(self):
        client = self.client
        options = self.options
        context = options.context or client.run('config', 'current-context', capture=True)
        print(f'Cluster context: {context}; namespace: {options.namespace}', flush=True)
        pvcs = {name: client.get('pvc', name) for name in ('postgres-data', 'mysql-data', 'redis-data')}
        existing = {name: client.get('deployment', name) for name in APPLICATIONS}
        databases = {name: client.get('deployment', name) for name in ('postgres', 'mysql')}
        config = client.get('configmap', 'sxdevops-config')
        configured_engine = (config or {}).get('data', {}).get('DATABASE_ENGINE', '')
        if not configured_engine and config:
            configured_engine = 'mysql' if config.get('data', {}).get('MYSQL_HOST') else ''
        configured_engine = {'postgres': 'postgresql', 'pg': 'postgresql'}.get(configured_engine, configured_engine)
        if configured_engine and configured_engine not in ('postgresql', 'mysql'):
            raise DeploymentError(f'Existing database engine {configured_engine} is not supported by this installer.')
        if options.database and configured_engine and options.database != configured_engine:
            raise DeploymentError('Changing database engines does not migrate data. Keep the existing database or use a new namespace for a fresh installation.')
        options.database = options.database or configured_engine or 'postgresql'
        database_name = 'postgres' if options.database == 'postgresql' else 'mysql'
        other_database = 'mysql' if database_name == 'postgres' else 'postgres'
        if pvcs[f'{other_database}-data'] or databases[other_database]:
            raise DeploymentError(f'Existing {other_database} data found. Restore its original ConfigMap and use the matching database option; automatic database conversion is not supported.')
        database = databases[database_name]
        database_pvc = pvcs[f'{database_name}-data']
        secret = client.get('secret', 'sxdevops-secrets')
        if not secret and (database_pvc or any(existing.values()) or database):
            raise DeploymentError('Existing installation has no sxdevops-secrets. Restore the original secret; new keys would break saved credentials.')
        if secret:
            validate_secret(secret, options.database)
        if options.image_pull_secret and not client.get('secret', options.image_pull_secret):
            raise DeploymentError('The image pull Secret does not exist in the target namespace. Create it before deploying.')

        template = TEMPLATE if options.database == 'postgresql' else TEMPLATE.with_name('sxdevops-mysql.yaml')
        source = decode_resources(client.run('create', '--dry-run=client', '--validate=false', '-f', str(template), '-o', 'json', capture=True, namespaced=False))
        if not client.get('namespace', options.namespace):
            client.run('create', 'namespace', options.namespace)
        resources = render_resources(source, options, config, pvcs, existing)
        initialized = (config or {}).get('metadata', {}).get('annotations', {}).get(INITIALIZED)
        seed_templates = initialized == 'false' or (initialized is None and not database_pvc and not any(existing.values()) and not database)
        if seed_templates:
            for resource in resources:
                if resource['kind'] == 'ConfigMap' and resource['metadata']['name'] == 'sxdevops-config':
                    resource['metadata'].setdefault('annotations', {})[INITIALIZED] = 'false'
        previous_job = client.get('job', 'sxdevops-migrate')
        terminal_job = previous_job and any(
            condition.get('type') in ('Complete', 'Failed') and condition.get('status') == 'True'
            for condition in previous_job.get('status', {}).get('conditions', [])
        )
        if previous_job and not terminal_job:
            job_image = previous_job['spec']['template']['spec']['containers'][0]['image']
            if job_image != options.image:
                raise DeploymentError('A migration for another image is still running. Wait for it to finish before changing versions.')
        changed_image = any(
            container['image'] != options.image
            for deployment in existing.values() if deployment
            for container in (
                deployment['spec']['template']['spec']['containers']
                + [item for item in deployment['spec']['template']['spec'].get('initContainers', []) if item['name'] == 'wait-for-schema']
            )
        )
        if changed_image and not options.upgrade:
            raise DeploymentError('Another application image is installed. Back up data and drain tasks, then repeat with --upgrade for the maintenance update.')
        if all(existing.values()) and not options.upgrade:
            if options.image_pull_secret:
                for deployment in existing.values():
                    pulls = deployment['spec']['template']['spec'].get('imagePullSecrets', [])
                    if {'name': options.image_pull_secret} not in pulls:
                        raise DeploymentError('Changing image pull configuration requires a maintenance update with --upgrade.')
            if all(item['spec'].get('replicas', 1) > 0 for item in existing.values()):
                print('Existing deployment retained. Waiting for services without changing configuration.', flush=True)
                self.finish()
                return

        # Stop old writers before changing configuration or running migrations.
        targets = [f'deployment/{name}' for name, value in existing.items() if value]
        if targets:
            client.run('scale', *targets, '--replicas=0')
            selector = 'app.kubernetes.io/part-of=sxdevops,app.kubernetes.io/name in (' + ','.join(APPLICATIONS) + ')'
            pods = client.run('get', 'pods', '-l', selector, '-o', 'name', capture=True)
            if pods:
                client.run('wait', '--for=delete', *pods.split(), '--timeout=300s')

        if not secret:
            client.run('create', '-f', '-', payload=make_secret(options.namespace, options.database))
            print('Created random database passwords and application keys in sxdevops-secrets.', flush=True)
        else:
            print('Keeping the existing sxdevops-secrets unchanged.', flush=True)
        client.run('apply', '-f', '-', payload={'apiVersion': 'v1', 'kind': 'List', 'items': resources})
        client.run('wait', '--for=jsonpath={.status.phase}=Bound', f'pvc/{database_name}-data', 'pvc/redis-data', '--timeout=300s')
        for name in (database_name, 'redis'):
            client.run('rollout', 'status', f'deployment/{name}', '--timeout=600s')

        if terminal_job:
            client.run('delete', 'job/sxdevops-migrate', '--wait=true')
            previous_job = None
        if not previous_job:
            previous_pod = (existing.get('sxdevops') or {}).get('spec', {}).get('template', {}).get('spec', {})
            client.run('create', '-f', '-', '-o', 'json', payload=migration_job(options, seed_templates, previous_pod.get('imagePullSecrets')), capture=True)
        job_name = 'sxdevops-migrate'
        try:
            client.run('wait', '--for=condition=complete', f'job/{job_name}', '--timeout=620s')
        except DeploymentError:
            logs = kubectl_command(options, 'logs', f'job/{job_name}')
            print(f'Migration did not complete. Applications remain stopped. Inspect: {command_text(logs)}', file=sys.stderr)
            raise
        if seed_templates:
            client.run('annotate', 'configmap/sxdevops-config', f'{INITIALIZED}=true', '--overwrite')
        client.run('scale', *(f'deployment/{name}' for name in APPLICATIONS), '--replicas=1')
        self.finish()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Deploy SXDevOps; generate secrets, migrate, initialize admin and open a local tunnel.')
    parser.add_argument('image', help='An existing application image with a fixed tag or digest, accessible by all cluster nodes.')
    parser.add_argument('--kubeconfig', help='Path to the target cluster kubeconfig. Default: kubectl KUBECONFIG / ~/.kube/config resolution.')
    parser.add_argument('--context', help='Use this kubeconfig context without changing its saved current-context.')
    parser.add_argument('--namespace', default='sxdevops')
    parser.add_argument('--database', choices=('postgresql', 'mysql'),
                        help='New installs default to PostgreSQL. Existing installs retain their configured engine; this does not migrate data.')
    parser.add_argument('--storage-class', help='Use this StorageClass for new PVCs; default: the cluster default.')
    parser.add_argument('--image-pull-secret', help='An existing registry authentication Secret in the target namespace.')
    parser.add_argument('--upgrade', action='store_true', help='Maintenance update: stop old application writers and run migrations before restarting.')
    parser.add_argument('--no-port-forward', action='store_true')
    parser.add_argument('--skip-admin', action='store_true', help='Skip interactive account setup, for automated deployments.')
    parser.add_argument('--port', type=int, default=8000)
    options = parser.parse_args(argv)
    if options.kubeconfig:
        path = Path(options.kubeconfig).expanduser().resolve()
        if not path.is_file():
            parser.error(f'kubeconfig file does not exist: {path}')
        options.kubeconfig = str(path)
    elif options.kubeconfig == '':
        parser.error('kubeconfig path must not be empty')
    if options.context == '':
        parser.error('context must not be empty')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', options.namespace):
        parser.error('namespace must be a valid Kubernetes namespace name')
    if not 1 <= options.port <= 65535:
        parser.error('port must be between 1 and 65535')
    tail = options.image.rsplit('/', 1)[-1]
    if (':' not in tail and '@sha256:' not in options.image) or tail.endswith(':latest') or 'registry.example.com/' in options.image:
        parser.error('provide your real application image using a fixed tag or sha256 digest; the example image and latest are not releases')
    return options


def main():
    options = parse_args()
    if not shutil.which('kubectl'):
        raise DeploymentError('Install kubectl and configure access to your cluster first.')
    Installer(options).deploy()


if __name__ == '__main__':
    try:
        main()
    except DeploymentError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nStopped the local command. Cluster resources and data have been retained.')
        sys.exit(130)
