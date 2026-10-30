from hashlib import sha256
from io import BytesIO

from django.db import transaction
from django.http import Http404, HttpResponse
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from eventwall.models import EventRecord
from eventwall.services import record_event

from .models import SiteSetting
from .permissions import build_rbac_permission


class SiteSettingSerializer(serializers.Serializer):
    site_name = serializers.CharField(max_length=10)
    icon = serializers.FileField(required=False, write_only=True)
    reset_icon = serializers.BooleanField(required=False, default=False)

    def validate_icon(self, upload):
        if upload.size > 1024 * 1024:
            raise serializers.ValidationError('图标大小不能超过 1 MB。')
        content = upload.read()
        try:
            with Image.open(BytesIO(content)) as image:
                if image.format not in {'PNG', 'JPEG', 'WEBP', 'ICO'}:
                    raise serializers.ValidationError('请选择 PNG、JPG、WebP 或 ICO 图标。')
                if image.width > 2048 or image.height > 2048:
                    raise serializers.ValidationError('图标尺寸不能超过 2048 × 2048 像素。')
                image.verify()
            with Image.open(BytesIO(content)) as image:
                normalized = image.convert('RGBA')
                normalized.thumbnail((256, 256), Image.Resampling.LANCZOS)
                output = BytesIO()
                normalized.save(output, format='PNG')
                return output.getvalue()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise serializers.ValidationError('图标文件损坏或不是有效图片。') from exc

    def validate(self, attrs):
        if attrs.get('reset_icon') and attrs.get('icon'):
            raise serializers.ValidationError('上传图标和恢复默认图标不能同时操作。')
        return attrs


def site_setting_data(setting):
    digest = sha256(bytes(setting.icon_data)).hexdigest() if setting.icon_data else ''
    return {
        'site_name': setting.site_name,
        'icon_url': f'/api/site-settings/icon/?v={digest}' if digest else '',
    }


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def public_site_settings(request):
    setting = SiteSetting.objects.filter(pk=1).first() or SiteSetting()
    response = Response(site_setting_data(setting))
    response['Cache-Control'] = 'no-cache'
    return response


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def site_icon(request):
    setting = SiteSetting.objects.filter(pk=1).first()
    if not setting or not setting.icon_data:
        raise Http404
    content = bytes(setting.icon_data)
    response = HttpResponse(content, content_type='image/png')
    response['Cache-Control'] = 'public, max-age=300, must-revalidate'
    response['ETag'] = f'"{sha256(content).hexdigest()}"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@api_view(['PUT'])
@permission_classes([build_rbac_permission('rbac.module.manage')])
@transaction.atomic
def update_site_settings(request):
    serializer = SiteSettingSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    setting, _ = SiteSetting.objects.get_or_create(pk=1)
    setting.site_name = data['site_name']
    if data['reset_icon']:
        setting.icon_data = b''
    elif 'icon' in data:
        setting.icon_data = data['icon']
    setting.updated_by = request.user.username
    setting.save()
    record_event(
        request=request,
        module='rbac',
        category='system',
        action='update_site_settings',
        title='更新网站基础配置',
        summary=f'网站名称已设置为 {setting.site_name}',
        resource_type='rbac_site_setting',
        resource_id='site-settings',
        resource_name=setting.site_name,
        severity=EventRecord.SEVERITY_INFO,
        correlation_id='rbac-site-settings',
        metadata={'site_name': setting.site_name, 'icon_updated': 'icon' in data, 'icon_reset': data['reset_icon']},
    )
    return Response(site_setting_data(setting))
