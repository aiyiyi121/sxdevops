import threading

from django.utils.text import slugify
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from eventwall.mixins import EventWallModelViewSetMixin
from eventwall.models import EventRecord
from eventwall.services import build_resource, record_event
from rbac.permissions import RBACPermissionMixin, build_rbac_permission

from . import deployer
from .models import ServiceDeployment, ServiceTemplate
from .serializers import (
    DeployRequestSerializer,
    ServiceDeploymentSerializer,
    ServiceTemplateSerializer,
)


def _default_release_name(template):
    return slugify(template.name) or f'service-{template.pk}'


class ServiceTemplateViewSet(RBACPermissionMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ServiceTemplate.objects.filter(is_active=True)
    serializer_class = ServiceTemplateSerializer
    pagination_class = None
    rbac_permissions = {
        'list': ['marketplace.template.view'],
        'retrieve': ['marketplace.template.view'],
    }


class ServiceDeploymentViewSet(EventWallModelViewSetMixin, RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = ServiceDeployment.objects.select_related('template', 'host', 'cluster')
    serializer_class = ServiceDeploymentSerializer
    event_module = 'marketplace'
    event_resource_type = 'service_deployment'
    event_resource_label = '服务部署实例'
    event_resource_name_fields = ('release_name',)
    rbac_permissions = {
        'list': ['marketplace.deployment.view'],
        'retrieve': ['marketplace.deployment.view'],
        'create': ['marketplace.deployment.manage'],
        'update': ['marketplace.deployment.manage'],
        'partial_update': ['marketplace.deployment.manage'],
        'destroy': ['marketplace.deployment.manage'],
        'stop': ['marketplace.deployment.manage'],
        'start': ['marketplace.deployment.manage'],
        'remove': ['marketplace.deployment.manage'],
        'logs': ['marketplace.deployment.view'],
    }

    def eventwall_should_record(self, action, instance=None):
        return False

    def eventwall_related_resources(self, instance):
        related = [build_resource('marketplace', 'service_template', instance.template_id, instance.template.name)]
        if instance.host_id:
            related.append(build_resource('ops', 'host', instance.host_id, instance.host.hostname))
        if instance.cluster_id:
            related.append(build_resource('ops', 'k8s_cluster', instance.cluster_id, instance.cluster.name))
        return related

    def eventwall_metadata(self, instance, action, before=None, after=None):
        return {
            'deploy_mode': instance.deploy_mode,
            'status': instance.status,
            'target': instance.target_display,
            'version': instance.version,
        }

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        deployment = self.get_object()
        deployer.stop_service(deployment)
        deployment.refresh_from_db()
        record_event(
            request=request,
            module='marketplace',
            category='execution',
            action='stop_service',
            title='停止市场服务实例',
            summary=f'服务 {deployment.template.name} 已执行停止操作',
            result=EventRecord.RESULT_SUCCESS if deployment.status == 'stopped' else EventRecord.RESULT_FAILED,
            severity=EventRecord.SEVERITY_WARNING,
            resource_type='service_deployment',
            resource_id=deployment.id,
            resource_name=deployment.template.name,
            application=deployment.template.name,
            correlation_id=f'marketplace-deployment:{deployment.id}',
            related_resources=self.eventwall_related_resources(deployment),
            metadata=self.eventwall_metadata(deployment, 'stop'),
        )
        return Response(ServiceDeploymentSerializer(deployment).data)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        deployment = self.get_object()
        deployer.start_service(deployment)
        deployment.refresh_from_db()
        record_event(
            request=request,
            module='marketplace',
            category='execution',
            action='start_service',
            title='启动市场服务实例',
            summary=f'服务 {deployment.template.name} 已执行启动操作',
            result=EventRecord.RESULT_SUCCESS if deployment.status == 'running' else EventRecord.RESULT_FAILED,
            severity=EventRecord.SEVERITY_WARNING,
            resource_type='service_deployment',
            resource_id=deployment.id,
            resource_name=deployment.template.name,
            application=deployment.template.name,
            correlation_id=f'marketplace-deployment:{deployment.id}',
            related_resources=self.eventwall_related_resources(deployment),
            metadata=self.eventwall_metadata(deployment, 'start'),
        )
        return Response(ServiceDeploymentSerializer(deployment).data)

    @action(detail=True, methods=['post'])
    def remove(self, request, pk=None):
        deployment = self.get_object()
        deployment_id = deployment.id
        deployment_name = deployment.template.name
        related_resources = self.eventwall_related_resources(deployment)
        metadata = self.eventwall_metadata(deployment, 'remove')
        result = deployer.remove_service(deployment)
        record_event(
            request=request,
            module='marketplace',
            category='execution',
            action='remove_service',
            title='下线市场服务实例',
            summary=f'服务 {deployment_name} 已执行下线操作',
            result=EventRecord.RESULT_SUCCESS if result is None else EventRecord.RESULT_FAILED,
            severity=EventRecord.SEVERITY_WARNING,
            resource_type='service_deployment',
            resource_id=deployment_id,
            resource_name=deployment_name,
            application=deployment_name,
            correlation_id=f'marketplace-deployment:{deployment_id}',
            related_resources=related_resources,
            metadata=metadata,
        )
        if result is None:
            return Response({'detail': '服务已卸载'}, status=status.HTTP_204_NO_CONTENT)
        return Response(ServiceDeploymentSerializer(result).data)

    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        deployment = self.get_object()
        tail = int(request.query_params.get('tail', 100))
        return Response({'logs': deployer.get_service_logs(deployment, tail=tail)})


@api_view(['POST'])
@permission_classes([IsAuthenticated, build_rbac_permission('marketplace.deployment.manage')])
def deploy_service_view(request):
    serializer = DeployRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        template = ServiceTemplate.objects.get(pk=data['template_id'])
    except ServiceTemplate.DoesNotExist:
        return Response({'detail': '模板不存在'}, status=status.HTTP_404_NOT_FOUND)

    deploy_mode = data['deploy_mode']
    if not template.supports_deploy_mode(deploy_mode):
        return Response({'detail': '当前模板暂不支持所选部署模式'}, status=status.HTTP_400_BAD_REQUEST)

    deployment_kwargs = {
        'template': template,
        'deploy_mode': deploy_mode,
        'version': data['version'],
        'env_config': data.get('env_config', {}),
        'deployer': request.user.username,
        'replicas': data.get('replicas', 1),
    }

    if deploy_mode == 'docker_compose':
        from ops.models import Host

        try:
            host = Host.objects.get(pk=data['host_id'])
        except Host.DoesNotExist:
            return Response({'detail': '目标主机不存在'}, status=status.HTTP_404_NOT_FOUND)

        if ServiceDeployment.objects.filter(
            template=template,
            host=host,
            deploy_mode='docker_compose',
        ).exists():
            return Response(
                {'detail': f'{template.name} 已在 {host.hostname} 上部署'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deployment_kwargs['host'] = host
    else:
        from ops.models import K8sCluster

        try:
            cluster = K8sCluster.objects.get(pk=data['cluster_id'])
        except K8sCluster.DoesNotExist:
            return Response({'detail': '目标集群不存在'}, status=status.HTTP_404_NOT_FOUND)

        namespace = data.get('namespace') or 'default'
        if ServiceDeployment.objects.filter(
            template=template,
            cluster=cluster,
            namespace=namespace,
            deploy_mode='k8s',
        ).exists():
            return Response(
                {'detail': f'{template.name} 已在 {cluster.name} 的 {namespace} 命名空间部署'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deployment_kwargs.update({
            'cluster': cluster,
            'namespace': namespace,
            'release_name': data.get('release_name') or _default_release_name(template),
        })

    deployment = ServiceDeployment.objects.create(**deployment_kwargs)
    thread = threading.Thread(target=deployer.deploy_service, args=(deployment.id,), daemon=True)
    thread.start()

    return Response(ServiceDeploymentSerializer(deployment).data, status=status.HTTP_201_CREATED)
