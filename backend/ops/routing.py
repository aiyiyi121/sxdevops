from django.urls import re_path
from . import ssh_consumer
from . import k8s_exec_consumer
from . import k8s_terminal_consumer
from . import docker_exec_consumer

websocket_urlpatterns = [
    re_path(r'ws/docker/exec/(?P<host_id>\d+)/$', docker_exec_consumer.DockerExecConsumer.as_asgi()),
    re_path(r'ws/ssh/(?P<host_id>\d+)/$', ssh_consumer.SSHConsumer.as_asgi()),
    re_path(r'ws/k8s/exec/(?P<cluster_id>\d+)/$', k8s_exec_consumer.K8sExecConsumer.as_asgi()),
    re_path(r'ws/k8s/terminal/(?P<cluster_id>\d+)/$', k8s_terminal_consumer.K8sClusterTerminalConsumer.as_asgi()),
]
