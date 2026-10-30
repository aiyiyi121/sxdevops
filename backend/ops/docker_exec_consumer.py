import codecs
import json
import shlex
import threading
import time
import uuid
from urllib.parse import parse_qs

from channels.generic.websocket import WebsocketConsumer
from django.db import close_old_connections
from rest_framework.authtoken.models import Token

from eventwall.services import record_event
from rbac.services import user_has_permissions
from .docker_views import (
    _find_demo_container, _get_demo_state, _get_docker_host,
    _get_ssh_client_from_docker_host, _is_demo_docker_host, _run_docker,
)
from .k8s_shell import interactive_shell_command


class DockerExecConsumer(WebsocketConsumer):
    channel_layer_alias = None

    def connect(self):
        self.client = self.channel = None
        self.running = False
        self.demo_buffer = ''
        self.last_activity = time.monotonic()
        query = parse_qs(self.scope.get('query_string', b'').decode('utf-8', errors='replace'))
        token = Token.objects.filter(key=query.get('token', [''])[0]).select_related('user').first()
        if not token or not token.user.is_active:
            return self.close(code=4401)
        self.user = token.user
        if not user_has_permissions(self.user, ['ops.docker.view', 'ops.docker.exec']):
            return self.close(code=4403)
        self.container_id = query.get('container_id', [''])[0]
        self.shell = query.get('shell', ['auto'])[0]
        if self.shell not in {'auto', '/bin/bash', '/bin/sh', '/bin/ash'} or not self.container_id or len(self.container_id) > 128 or not all(char.isalnum() or char in '_.-' for char in self.container_id) or self.container_id.startswith('-'):
            return self.close(code=4400)
        self.host = _get_docker_host(self.scope['url_route']['kwargs']['host_id'])
        if self.host is None:
            return self.close(code=4404)
        self.demo = _is_demo_docker_host(self.host)
        self.accept()
        try:
            if self.demo:
                container = _find_demo_container(_get_demo_state(self.host), self.container_id)
                if not container or container['state'] != 'running':
                    raise RuntimeError('容器不存在或未运行')
                self._audit()
                self._send('connected')
                self._send('output', data='Docker 演示容器终端\r\n/app $ ')
                return
            code, output, error = _run_docker(self.host, f'docker container inspect --format "{{{{.State.Running}}}}" {shlex.quote(self.container_id)}', timeout=10)
            if code or output.strip() != 'true':
                raise RuntimeError('容器未运行，请先检查容器状态')
            self.client = _get_ssh_client_from_docker_host(self.host)
            self.channel = self.client.get_transport().open_session(timeout=10)
            self.channel.get_pty(term='xterm-256color', width=120, height=36)
            self.channel.settimeout(1)
            self.marker = f'SXDEVOPS_READY_{uuid.uuid4().hex}'
            shell_command = shlex.join(interactive_shell_command(self.shell))
            required_shell = '/bin/sh' if self.shell == 'auto' else self.shell
            startup = f'test -x {shlex.quote(required_shell)} || exit 127; printf "%s\\n" {shlex.quote(self.marker)}; exec {shell_command}'
            self.channel.exec_command(f'docker exec -it {shlex.quote(self.container_id)} /bin/sh -c {shlex.quote(startup)}')
            self.running = True
            threading.Thread(target=self._read_output, daemon=True).start()
        except Exception as exc:
            self._send('error', message=f'容器终端连接失败: {exc}')
            self._cleanup()
            self.close()

    def _send(self, message_type, **payload):
        self.send(text_data=json.dumps({'type': message_type, **payload}))

    def _audit(self):
        record_event(module='ops', category='operation', action='docker_exec', title='进入 Docker 容器终端',
                     actor_username=self.user.username, resource_type='docker_container',
                     resource_id=self.container_id, resource_name=self.host.name,
                     metadata={'host_id': self.host.pk}, is_demo=self.demo)

    def _cleanup(self):
        self.running = False
        channel, client = self.channel, self.client
        self.channel = self.client = None
        if channel is not None:
            channel.close()
        if client is not None:
            client.close()

    def disconnect(self, close_code):
        self._cleanup()

    def receive(self, text_data=None, bytes_data=None):
        if not text_data or len(text_data) > 65536:
            return
        try:
            payload = json.loads(text_data)
            if not isinstance(payload, dict):
                return
            if payload.get('type') == 'input':
                incoming = payload.get('data', '')
                if not isinstance(incoming, str):
                    return
                self.last_activity = time.monotonic()
                if self.demo:
                    self._demo_input(incoming)
                elif self.channel is not None:
                    self.channel.sendall(incoming)
            elif payload.get('type') == 'resize' and self.channel is not None:
                self.channel.resize_pty(width=max(20, min(500, int(payload.get('cols', 120)))),
                                        height=max(5, min(300, int(payload.get('rows', 36)))))
        except (ValueError, TypeError, OSError):
            return

    def _read_output(self):
        channel = self.channel
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        started = time.monotonic()
        pending = ''
        ready = False
        try:
            while self.running:
                elapsed = time.monotonic() - started
                if elapsed > 1800 or time.monotonic() - self.last_activity > 900:
                    self._send('error', message='终端会话已到期，请重新连接')
                    break
                if not ready and elapsed > 20:
                    raise TimeoutError('等待容器 Shell 超时')
                if channel.recv_ready():
                    output = decoder.decode(channel.recv(65536))
                    if ready:
                        self._send('output', data=output)
                    else:
                        pending += output
                        if self.marker in pending:
                            self._audit()
                            ready = True
                            self._send('connected')
                            self._send('output', data=pending.split(self.marker, 1)[1].lstrip('\r\n'))
                            pending = ''
                        elif len(pending) > 65536:
                            raise RuntimeError('容器 Shell 启动异常')
                elif channel.exit_status_ready():
                    if not ready or channel.recv_exit_status():
                        self._send('error', message='容器 Shell 已退出，请检查 Shell 是否可用')
                    break
                else:
                    time.sleep(0.02)
        except Exception as exc:
            if self.running:
                self._send('error', message=f'终端连接中断: {exc}')
        finally:
            self._cleanup()
            close_old_connections()
            self.close()

    def _demo_input(self, incoming):
        for char in incoming:
            if char in '\r\n':
                command = self.demo_buffer.strip()
                self.demo_buffer = ''
                if command == 'exit':
                    self.close()
                    return
                output = {'pwd': '/app', 'ls': 'app  config  logs  tmp', 'whoami': 'app', '': ''}.get(command, f'sh: {command}: command not found')
                self._send('output', data=f'\r\n{output}\r\n/app $ ')
            elif char == '\x7f':
                if self.demo_buffer:
                    self.demo_buffer = self.demo_buffer[:-1]
                    self._send('output', data='\b \b')
            elif char.isprintable() and len(self.demo_buffer) < 4096:
                self.demo_buffer += char
                self._send('output', data=char)
