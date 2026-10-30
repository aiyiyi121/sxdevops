import os
from unittest.mock import patch

from django.test import SimpleTestCase

from sxdevops import settings as app_settings


class DatabaseConfigurationTests(SimpleTestCase):
    def config(self, section=None, **environment):
        with patch.object(app_settings, 'APP_CONFIG', {'database': section or {}}), patch.dict(os.environ, environment, clear=True):
            return app_settings._build_database_config()['default']

    def test_unconfigured_new_install_defaults_to_postgresql(self):
        config = self.config()
        self.assertEqual(config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual((config['NAME'], config['USER'], config['PORT']), ('sxdevops', 'sxdevops', '5432'))

    def test_postgresql_environment_and_ssl_options(self):
        config = self.config(DATABASE_ENGINE='postgresql', POSTGRES_HOST='db.internal.test',
                             POSTGRES_PORT='6432', POSTGRES_DB='platform', POSTGRES_USER='platform_user',
                             POSTGRES_PASSWORD='test-password', POSTGRES_SSLMODE='verify-full')
        self.assertEqual((config['HOST'], config['PORT'], config['NAME']), ('db.internal.test', '6432', 'platform'))
        self.assertEqual(config['PASSWORD'], 'test-password')
        self.assertEqual(config['OPTIONS']['sslmode'], 'verify-full')
        self.assertNotIn('charset', config['OPTIONS'])

    def test_json_keeps_priority_over_environment(self):
        config = self.config({'type': 'postgresql', 'database_name': 'json_db', 'port': 5433,
                              'options': {'sslrootcert': '/certs/test-ca.pem'}, 'test': {'NAME': 'isolated_test'}},
                             POSTGRES_DB='env_db', POSTGRES_PORT='5432')
        self.assertEqual((config['NAME'], config['PORT']), ('json_db', '5433'))
        self.assertEqual(config['OPTIONS']['sslrootcert'], '/certs/test-ca.pem')
        self.assertEqual(config['TEST'], {'NAME': 'isolated_test'})

    def test_mysql_stays_available(self):
        config = self.config(DATABASE_ENGINE='mysql', MYSQL_DATABASE='existing', MYSQL_HOST='old-db', MYSQL_PORT='3307')
        self.assertEqual(config['ENGINE'], 'django.db.backends.mysql')
        self.assertEqual((config['NAME'], config['HOST'], config['PORT']), ('existing', 'old-db', '3307'))

    def test_explicit_sqlite_keeps_local_file(self):
        config = self.config(DATABASE_ENGINE='sqlite', SQLITE_PATH='local-test.sqlite3')
        self.assertEqual(config['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(config['NAME'], app_settings.BASE_DIR / 'local-test.sqlite3')
