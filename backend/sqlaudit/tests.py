from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from rbac.models import PermissionDefinition, Role
from rbac.services import ensure_builtin_rbac
from . import db_executor, sql_checker
from .models import DataSource, QueryOrder, SqlOrder


User = get_user_model()


class SqlAuditSupportTests(TestCase):
    def test_demo_datasource_returns_mock_connection_and_databases(self):
        datasource = DataSource(
            name='commerce-prod-postgresql',
            db_type='postgresql',
            host='postgres.demo.invalid',
            port=5432,
            user='audit_reader',
            password='secret',
            charset='UTF8',
        )

        success, message = db_executor.test_connection(datasource)
        databases = db_executor.get_databases(datasource)

        self.assertTrue(success)
        self.assertIn('模拟', message)
        self.assertEqual(databases, ['order_center', 'payment_center', 'member_center'])

    def test_demo_datasource_query_returns_mock_rows(self):
        datasource = DataSource(
            name='member-staging-mysql',
            db_type='mysql',
            host='10.20.32.18',
            port=3306,
            user='staging_auditor',
            password='secret',
            charset='utf8mb4',
        )

        success, columns, rows, count, duration, error = db_executor.execute_query(
            datasource,
            'member_center',
            'SELECT id, nickname, last_login_at FROM member_profile LIMIT 50',
        )

        self.assertTrue(success)
        self.assertEqual(error, None)
        self.assertGreater(count, 0)
        self.assertIn('id', columns)
        self.assertIn('nickname', columns)
        self.assertGreaterEqual(duration, 60)
        self.assertTrue(rows[0]['nickname'])

    def test_check_sql_accepts_mongodb_dml_command(self):
        results = sql_checker.check_sql(
            'updateMany {"collection":"orders","filter":{"status":"new"},"update":{"$set":{"status":"done"}}}',
            'DML',
            'mongodb',
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].rule_name, 'ALL_PASSED')

    def test_check_sql_rejects_mongodb_update_many_without_filter(self):
        results = sql_checker.check_sql(
            'updateMany {"collection":"orders","filter":{},"update":{"$set":{"status":"done"}}}',
            'DML',
            'mongodb',
        )
        self.assertTrue(any(item.rule_name == 'NO_FILTER_UPDATE' for item in results))

    def test_validate_query_content_supports_mongodb(self):
        datasource = DataSource(db_type='mongodb')
        self.assertIsNone(db_executor.validate_query_content(
            datasource,
            'find {"collection":"orders","filter":{"status":"running"},"limit":20}',
        ))

    def test_validate_query_content_rejects_mysql_write_statement(self):
        datasource = DataSource(db_type='mysql')
        self.assertEqual(
            db_executor.validate_query_content(datasource, 'UPDATE orders SET status = 1'),
            '查询工单只允许 SELECT / SHOW / DESC 语句',
        )

    @patch('sqlaudit.db_executor._test_postgresql_connection')
    def test_postgresql_uses_its_own_driver(self, mock_test_postgresql_connection):
        mock_test_postgresql_connection.return_value = (True, '连接成功')
        datasource = DataSource(db_type='postgresql', host='127.0.0.1', port=5432, user='postgres', password='secret', charset='UTF8')
        success, message = db_executor.test_connection(datasource)
        self.assertTrue(success)
        self.assertEqual(message, '连接成功')
        mock_test_postgresql_connection.assert_called_once()


class SqlAuditRBACTests(TestCase):
    def setUp(self):
        ensure_builtin_rbac()
        self.datasource = DataSource.objects.create(
            name='prod-mysql',
            db_type='mysql',
            host='127.0.0.1',
            port=3306,
            user='root',
            password='secret',
            charset='utf8mb4',
        )

    def create_user_with_permissions(self, username, permission_codes):
        role = Role.objects.create(code=f'{username}-role', name=f'{username}-role')
        role.permissions.set(PermissionDefinition.objects.filter(code__in=permission_codes))
        user = User.objects.create_user(username=username, password='Admin@123456')
        role.users.add(user)
        return user

    @patch('sqlaudit.views.sql_checker.check_sql', return_value=[])
    def test_order_submit_cannot_override_protected_fields(self, _mock_check_sql):
        user = self.create_user_with_permissions('submitter', ['sqlaudit.datasource.view', 'sqlaudit.order.submit'])
        self.client.force_login(user)

        response = self.client.post('/api/sqlaudit/orders/', {
            'title': 'dangerous-order',
            'datasource': self.datasource.id,
            'database': 'app',
            'sql_type': 'DML',
            'sql_content': 'UPDATE demo SET value = 1 WHERE id = 1',
            'status': 'approved',
            'submitter': 'spoof-user',
            'reviewer': 'spoof-reviewer',
            'review_comment': 'spoof-comment',
        })

        self.assertEqual(response.status_code, 201)
        order = SqlOrder.objects.get(title='dangerous-order')
        self.assertEqual(order.status, 'pending')
        self.assertEqual(order.submitter, user.username)
        self.assertEqual(order.reviewer, '')
        self.assertEqual(order.review_comment, '')

    def test_query_execute_requires_datasource_view(self):
        user = self.create_user_with_permissions('query-only', ['sqlaudit.query.execute'])
        self.client.force_login(user)

        response = self.client.post('/api/sqlaudit/queries/', {
            'datasource': self.datasource.id,
            'database': 'app',
            'sql_content': 'SELECT 1',
        })

        self.assertEqual(response.status_code, 403)

    def test_order_patch_is_not_allowed(self):
        user = self.create_user_with_permissions('reviewer', ['sqlaudit.order.view', 'sqlaudit.order.review'])
        order = SqlOrder.objects.create(
            title='review-me',
            datasource=self.datasource,
            database='app',
            sql_type='DML',
            sql_content='UPDATE demo SET value = 1 WHERE id = 1',
            submitter='dev',
        )
        self.client.force_login(user)

        response = self.client.patch(f'/api/sqlaudit/orders/{order.id}/', {'title': 'changed'}, content_type='application/json')
        self.assertEqual(response.status_code, 405)

    def test_order_list_supports_status_filter(self):
        user = self.create_user_with_permissions('auditor', ['sqlaudit.order.view'])
        SqlOrder.objects.create(
            title='pending-order',
            datasource=self.datasource,
            database='app',
            sql_type='DML',
            sql_content='UPDATE demo SET value = 1 WHERE id = 1',
            submitter='dev',
            status='pending',
        )
        SqlOrder.objects.create(
            title='approved-order',
            datasource=self.datasource,
            database='app',
            sql_type='DML',
            sql_content='UPDATE demo SET value = 2 WHERE id = 2',
            submitter='dev',
            status='approved',
        )
        self.client.force_login(user)

        response = self.client.get('/api/sqlaudit/orders/?status=pending')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['title'], 'pending-order')

    @patch('sqlaudit.views.db_executor.execute_query', return_value=(True, ['id'], [{'id': 1}], 1, 8, None))
    def test_query_create_ignores_client_controlled_fields(self, _mock_execute_query):
        user = self.create_user_with_permissions('query-runner', ['sqlaudit.datasource.view', 'sqlaudit.query.execute'])
        self.client.force_login(user)

        response = self.client.post('/api/sqlaudit/queries/', {
            'datasource': self.datasource.id,
            'database': 'app',
            'sql_content': 'SELECT 1',
            'submitter': 'spoof-user',
            'result_count': 999,
            'duration_ms': 999,
        })

        self.assertEqual(response.status_code, 201)
        order = QueryOrder.objects.get(submitter=user.username)
        self.assertEqual(order.submitter, user.username)
        self.assertEqual(order.result_count, 1)
        self.assertEqual(order.duration_ms, 8)
