from django.test import TestCase

from .models import SystemModuleSetting
from .services import ensure_system_module_settings, get_system_module_settings


class ObservabilityMenuSplitTests(TestCase):
    def test_split_preserves_existing_visibility_and_custom_order(self):
        SystemModuleSetting.objects.all().delete()
        SystemModuleSetting.objects.create(
            code='observability.boards', enabled=False, sort_order=10, is_default=True,
        )

        items = get_system_module_settings()
        by_code = {item['code']: item for item in items}
        posture = by_code['observability.system-posture']
        boards = by_code['observability.boards']

        self.assertFalse(posture['enabled'])
        self.assertFalse(boards['enabled'])
        self.assertEqual(posture['sort_order'], 10)
        self.assertEqual(posture['path'], '/observability/system-posture')
        self.assertEqual(boards['path'], '/observability/grafana')
        self.assertTrue(boards['is_default'])
        self.assertLess(items.index(posture), items.index(boards))

        SystemModuleSetting.objects.filter(code=posture['code']).update(enabled=True, sort_order=5)
        ensure_system_module_settings()
        setting = SystemModuleSetting.objects.get(code=posture['code'])
        self.assertTrue(setting.enabled)
        self.assertEqual(setting.sort_order, 5)

    def test_new_install_orders_posture_before_dashboards(self):
        SystemModuleSetting.objects.all().delete()
        items = get_system_module_settings()
        codes = [item['code'] for item in items]
        self.assertLess(codes.index('observability.system-posture'), codes.index('observability.boards'))
        by_code = {item['code']: item for item in items}
        self.assertEqual(by_code['observability.system-posture']['title'], '系统态势')
        self.assertEqual(by_code['observability.boards']['title'], '仪表盘')
