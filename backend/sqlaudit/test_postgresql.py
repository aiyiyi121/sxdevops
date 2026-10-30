import importlib
from unittest import skipUnless
from unittest.mock import patch

import psycopg
from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase

from . import db_executor, sql_checker
from .models import DataSource
from .serializers import DataSourceSerializer


class PostgreSQLValidationTests(SimpleTestCase):
    def setUp(self):
        self.source = DataSource(db_type='postgresql', host='db.test', port=5432, user='auditor',
                                 password='test-only', charset='UTF8', database='maintenance')

    def test_native_connection_uses_maintenance_or_selected_database(self):
        self.assertEqual(db_executor._postgresql_connect_kwargs(self.source)['dbname'], 'maintenance')
        config = db_executor._postgresql_connect_kwargs(self.source, 'orders')
        self.assertEqual(config['dbname'], 'orders')
        self.assertEqual(config['port'], 5432)
        self.assertNotIn('charset', config)

    def test_postgresql_read_validation_handles_ctes_and_rejects_writes(self):
        for query in ('SELECT 1', 'WITH t AS (SELECT 1 AS id) SELECT id FROM t', 'SHOW server_version'):
            self.assertIsNone(db_executor.validate_query_content(self.source, query))
        for query in ('SELECT 1; DELETE FROM orders', 'WITH t AS (DELETE FROM orders RETURNING *) SELECT * FROM t',
                      'SELECT * INTO copied FROM orders', 'DESC orders', 'UPDATE orders SET id = 1'):
            self.assertTrue(db_executor.validate_query_content(self.source, query), query)

    def test_dollar_quoted_function_is_one_statement_and_mysql_syntax_is_rejected(self):
        sql = "CREATE FUNCTION f() RETURNS text LANGUAGE plpgsql AS $$ BEGIN RETURN 'a;b'; END; $$; SELECT 1;"
        self.assertEqual(len(sql_checker._split_statements(sql)), 2)
        self.assertTrue(any(item.rule_name == 'POSTGRESQL_DIALECT' for item in
                            sql_checker.check_sql('CREATE TABLE t (id INT AUTO_INCREMENT)', 'DDL', 'postgresql')))
        self.assertFalse(any(item.level == 'error' for item in sql_checker.check_sql(sql, 'DDL', 'postgresql')))

    def test_transaction_control_cannot_bypass_order_atomicity(self):
        with patch('sqlaudit.db_executor.psycopg.connect') as connect:
            for content in ('UPDATE t SET id=1 WHERE id=2; COMMIT;', '-- comment\nROLLBACK;', 'BEGIN; SELECT 1; END;'):
                self.assertFalse(db_executor.execute_sql(self.source, 'orders', content)[0])
            connect.assert_not_called()

    def test_datasource_serializer_defaults_pg_port_and_encoding_and_rejects_old_type(self):
        serializer = DataSourceSerializer()
        validated = serializer.validate({'db_type': 'postgresql'})
        self.assertEqual((validated['port'], validated['charset']), (5432, 'UTF8'))
        choices = serializer.fields['db_type'].choices
        self.assertIn('postgresql', choices)
        self.assertNotIn('polardb', choices)


class DataSourceCorrectionTests(TransactionTestCase):
    def test_pg_datasource_create_uses_pg_defaults_when_port_and_charset_are_omitted(self):
        serializer = DataSourceSerializer(data={'name': 'pg-defaults', 'db_type': 'postgresql',
                                                'host': 'db.test', 'user': 'auditor', 'password': 'test-only'})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        source = serializer.save()
        self.assertEqual((source.port, source.charset), (5432, 'UTF8'))

    def test_correction_preserves_custom_connections_and_other_engines(self):
        common = dict(host='db.test', user='auditor', password='test-only')
        standard = DataSource.objects.create(name='old-standard', db_type='polardb', port=3306, **common)
        custom = DataSource.objects.create(name='old-custom', db_type='polardb', port=6432, **common)
        mysql = DataSource.objects.create(name='existing-mysql', db_type='mysql', port=3306, **common)
        migration = importlib.import_module('sqlaudit.migrations.0003_postgresql_datasource')
        from django.apps import apps
        with connection.schema_editor() as editor:
            migration.correct_datasources(apps, editor)
        for source in (standard, custom, mysql):
            source.refresh_from_db()
        self.assertEqual((standard.db_type, standard.port, standard.charset), ('postgresql', 5432, 'UTF8'))
        self.assertEqual((custom.db_type, custom.port, custom.host), ('postgresql', 6432, 'db.test'))
        self.assertEqual((mysql.db_type, mysql.port), ('mysql', 3306))


@skipUnless(connection.vendor == 'postgresql', 'Requires an isolated PostgreSQL test database')
class PostgreSQLExecutionTests(TransactionTestCase):
    def setUp(self):
        database = settings.DATABASES['default']
        self.source = DataSource(db_type='postgresql', host=database['HOST'], port=int(database['PORT']),
                                 user=database['USER'], password=database['PASSWORD'], database=database['NAME'])
        self.database = database['NAME']
        self.assertTrue(db_executor.execute_sql(self.source, self.database,
                        'CREATE TABLE sqlaudit_pg_validation (id integer PRIMARY KEY, value text);')[0])

    def tearDown(self):
        db_executor.execute_sql(self.source, self.database, 'DROP TABLE IF EXISTS sqlaudit_pg_validation;')
        db_executor.execute_sql(self.source, self.database, 'DROP FUNCTION IF EXISTS sqlaudit_pg_function();')

    def query(self, sql, limit=200):
        return db_executor.execute_query(self.source, self.database, sql, limit)

    def test_connection_discovery_write_and_bounded_query(self):
        self.assertTrue(db_executor.test_connection(self.source)[0])
        self.assertIn(self.database, db_executor.get_databases(self.source))
        result = db_executor.execute_sql(self.source, self.database,
                 "INSERT INTO sqlaudit_pg_validation VALUES (1, '中文;值'), (2, 'second');")
        self.assertEqual(result[:2], (True, 2))
        success, columns, rows, count, _, error = self.query('SELECT * FROM sqlaudit_pg_validation ORDER BY id', 1)
        self.assertTrue(success, error)
        self.assertEqual((columns, rows, count), (['id', 'value'], [{'id': 1, 'value': '中文;值'}], 1))
        self.assertTrue(self.query('SHOW server_version')[0])
        self.assertTrue(self.query('WITH t AS (SELECT 42 AS id) SELECT id FROM t')[0])

    def test_failed_second_statement_rolls_back_first(self):
        result = db_executor.execute_sql(self.source, self.database,
                 "INSERT INTO sqlaudit_pg_validation VALUES (1, 'first'); INSERT INTO nonexistent_table VALUES (1);")
        self.assertFalse(result[0])
        self.assertEqual(self.query('SELECT count(*) AS total FROM sqlaudit_pg_validation')[2], [{'total': 0}])

    def test_readonly_transaction_blocks_write_in_function(self):
        content = """CREATE FUNCTION sqlaudit_pg_function() RETURNS integer LANGUAGE plpgsql AS $$
        BEGIN INSERT INTO sqlaudit_pg_validation VALUES (99, 'blocked'); RETURN 99; END; $$;"""
        self.assertTrue(db_executor.execute_sql(self.source, self.database, content)[0])
        self.assertFalse(self.query('SELECT sqlaudit_pg_function()')[0])
        self.assertEqual(self.query('SELECT count(*) AS total FROM sqlaudit_pg_validation')[2], [{'total': 0}])

    def test_transactional_ddl_and_dollar_quotes_execute_as_a_unit(self):
        content = """CREATE FUNCTION sqlaudit_pg_function() RETURNS text LANGUAGE plpgsql AS $$
        BEGIN RETURN 'hello;世界'; END; $$;"""
        result = db_executor.execute_sql(self.source, self.database, content)
        self.assertTrue(result[0], result[3])
        result = self.query('SELECT sqlaudit_pg_function() AS greeting')
        self.assertTrue(result[0], result[-1])
        self.assertEqual(result[2], [{'greeting': 'hello;世界'}])

    def test_datasource_order_approval_execution_and_query_api(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_superuser('pg-audit-test', password='test-only-password')
        self.client.force_login(user)
        response = self.client.post('/api/sqlaudit/datasources/', {
            'name': 'postgres-integration', 'db_type': 'postgresql', 'host': self.source.host,
            'port': self.source.port, 'user': self.source.user, 'password': 'test-only', 'database': self.database,
        })
        self.assertEqual(response.status_code, 201, response.content)
        datasource = response.json()
        self.assertEqual(datasource['charset'], 'UTF8')
        self.assertNotIn('password', datasource)
        source_id = datasource['id']
        response = self.client.post(f'/api/sqlaudit/datasources/{source_id}/test_connection/')
        self.assertTrue(response.json()['success'], response.content)
        response = self.client.get(f'/api/sqlaudit/datasources/{source_id}/databases/')
        self.assertIn(self.database, response.json()['databases'])
        response = self.client.post('/api/sqlaudit/orders/', {
            'title': 'PostgreSQL native change', 'datasource': source_id, 'database': self.database,
            'sql_type': 'DML', 'sql_content': "INSERT INTO sqlaudit_pg_validation VALUES (7, '工单写入');",
        })
        self.assertEqual(response.status_code, 201, response.content)
        order_id = response.json()['id']
        self.assertEqual(self.client.post(f'/api/sqlaudit/orders/{order_id}/approve/').status_code, 200)
        response = self.client.post(f'/api/sqlaudit/orders/{order_id}/execute/')
        self.assertEqual(response.json()['status'], 'executed', response.content)
        response = self.client.post('/api/sqlaudit/queries/', {
            'datasource': source_id, 'database': self.database,
            'sql_content': 'SELECT value FROM sqlaudit_pg_validation WHERE id = 7',
        })
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['rows'], [{'value': '工单写入'}])
