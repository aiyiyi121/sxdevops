from django.core.exceptions import PermissionDenied
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from rbac.permissions import build_rbac_permission
from rbac.services import user_has_permissions

from .models import AIOpsKnowledgeEnvironment, AIOpsPendingAction, AIOpsRemediationVerification
from .remediation import configure_verification, verification_details


class VerificationInputSerializer(serializers.Serializer):
    environment_id = serializers.IntegerField(min_value=1)
    alert_id = serializers.IntegerField(min_value=1)
    observation_seconds = serializers.IntegerField(min_value=0, max_value=600, default=60)


@api_view(['GET', 'POST'])
@permission_classes([build_rbac_permission('aiops.chat.analyze', 'ops.alert.view')])
def action_verification(request, pk):
    action = AIOpsPendingAction.objects.select_related('session').filter(
        pk=pk, mirror_source__isnull=True, session__mirror_source__isnull=True,
    ).first()
    if not action or (action.session.user_id != request.user.id
                      and not user_has_permissions(request.user, ['aiops.audit.view'])):
        return Response({'detail': '动作不存在'}, status=404)
    if request.method == 'POST':
        serializer = VerificationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            configure_verification(action, request.user, **serializer.validated_data)
        except PermissionDenied as exc:
            return Response({'detail': str(exc)}, status=403)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
    verification = AIOpsRemediationVerification.objects.select_related('environment', 'action__session__user').filter(action=action).first()
    can_configure = (
        verification is None and action.session.user_id == request.user.id
        and action.action_type == AIOpsPendingAction.ACTION_EXECUTE_HOST_TASK
        and action.status in (AIOpsPendingAction.STATUS_PENDING, AIOpsPendingAction.STATUS_EXECUTED)
        and not (action.result_payload or {}).get('materialized_in_task_center')
    )
    return Response({
        'verification': verification_details(verification, request.user) if verification else None,
        'can_configure': can_configure,
        'environments': list(AIOpsKnowledgeEnvironment.objects.filter(is_enabled=True).exclude(
            alert_environments=[],
        ).values('id', 'name')) if can_configure else [],
    })
