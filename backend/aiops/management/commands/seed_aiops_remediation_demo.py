import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from aiops.remediation_demo import evaluate_remediation_demo, seed_remediation_demo


class Command(BaseCommand):
    help = '补充并评测六组处置验证演示数据，不连接主机或执行真实任务'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='admin')

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options['username'], is_active=True, is_superuser=True).first()
        if not user:
            raise CommandError('未找到指定的有效管理员；命令不会创建或修改账号。')
        seed_remediation_demo(user)
        result = evaluate_remediation_demo(user)
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        if result['matched'] != result['total']:
            raise CommandError('部分演示评测未达到预期，请检查验证节点审计。')
