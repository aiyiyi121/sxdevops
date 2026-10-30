import io
import time

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from rbac.permissions import build_rbac_permission
from .docker_views import (
    _demo_logs_for_container, _find_demo_container, _get_demo_state,
    _get_docker_host, _get_ssh_client_from_docker_host, _is_demo_docker_host,
    _quote_arg, _validate_identifier,
)
from .k8s_logs import LogSnapshotError, pod_log_page


class DockerLogStream:
    def __init__(self, host, container_id, tail):
        self.client = _get_ssh_client_from_docker_host(host)
        self.channel = None
        try:
            self.channel = self.client.get_transport().open_session(timeout=10)
            self.channel.set_combine_stderr(True)
            self.channel.settimeout(10)
            tail_flag = f' --tail={int(tail)}' if tail is not None else ''
            self.channel.exec_command(f'docker logs{tail_flag} {_quote_arg(container_id)}')
        except Exception:
            self.close()
            raise

    def stream(self, amt=65536):
        deadline = time.monotonic() + 55
        while True:
            if time.monotonic() > deadline:
                raise LogSnapshotError('日志采集超时，请稍后重试。')
            if self.channel.recv_ready():
                yield self.channel.recv(amt)
            elif self.channel.exit_status_ready():
                if self.channel.recv_exit_status():
                    raise LogSnapshotError('Docker 日志读取失败，请检查容器及日志驱动。')
                break
            else:
                time.sleep(0.01)

    def close(self):
        if self.channel is not None:
            self.channel.close()
        self.client.close()

    def release_conn(self):
        pass


class DemoLogStream:
    def __init__(self, container, tail):
        lines = [f'[INFO] container={container["name"]} demo request={index:04d}\n' for index in range(1, 2401)]
        lines.extend(_demo_logs_for_container(container).splitlines(keepends=True))
        self.content = io.BytesIO(''.join(lines[-tail:] if tail else lines).encode('utf-8'))

    def stream(self, amt=65536):
        while chunk := self.content.read(amt):
            yield chunk

    def close(self):
        self.content.close()

    def release_conn(self):
        pass


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('ops.docker.view')])
def container_log_page(request, container_id):
    _validate_identifier(container_id)
    host = _get_docker_host(request.query_params.get('host_id'))
    if host is None:
        return Response({'detail': 'Docker 环境不存在'}, status=404)
    if _is_demo_docker_host(host):
        container = _find_demo_container(_get_demo_state(host), container_id)
        if container is None:
            return Response({'detail': '容器不存在'}, status=404)
        loader = lambda tail: DemoLogStream(container, tail)
    else:
        loader = lambda tail: DockerLogStream(host, container_id, tail)
    scope = {'source': 'docker', 'user': request.user.pk, 'host': host.pk, 'container': container_id}
    try:
        return Response(pod_log_page(request.query_params, scope, loader))
    except APIException:
        raise
    except Exception as exc:
        raise LogSnapshotError(f'读取容器日志失败: {exc}')
