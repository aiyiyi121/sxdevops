from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from cmdb.builtins import ensure_builtin_cmdb


class Command(BaseCommand):
    help = '初始化或刷新 CMDB 内置模型、字段、关系规则、阈值和同步模板'

    def handle(self, *args, **options):
        table_names = set(connection.introspection.table_names())
        if 'cmdb_cimodelgroup' not in table_names:
            raise CommandError('CMDB 0005 迁移尚未应用，请先执行 python manage.py migrate。')

        summary = ensure_builtin_cmdb()
        self.stdout.write(
            self.style.SUCCESS(
                'CMDB builtins ensured: '
                f"{summary['groups']} groups, {summary['types']} types, "
                f"{summary['fields']} fields, {summary['relation_rules']} relation rules, "
                f"{summary['threshold_policies']} threshold policies, "
                f"{summary['sync_jobs']} sync templates."
            )
        )
