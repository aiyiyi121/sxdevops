from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from .frontend_views import frontend_index


class FrontendSecurityHeadersTests(SimpleTestCase):
    def test_every_spa_entry_receives_script_and_form_restrictions(self):
        with TemporaryDirectory() as directory:
            dist = Path(directory)
            (dist / 'index.html').write_text('<html>test</html>', encoding='utf-8')
            with patch('sxdevops.frontend_views.FRONTEND_DIST_DIR', dist):
                for path in ('/', '/login?redirect=/dashboard', '/observability/grafana', '/about'):
                    with self.subTest(path=path):
                        response = frontend_index(RequestFactory().get(path))
                        self.addCleanup(response.close)
                        policy = response['Content-Security-Policy']
                        self.assertIn("script-src 'self'", policy)
                        self.assertIn("form-action 'self'", policy)
                        self.assertIn("object-src 'none'", policy)
                        self.assertNotIn('unsafe-inline', policy)
                        self.assertIn('no-store', response['Cache-Control'])
                        self.assertEqual(response['Referrer-Policy'], 'strict-origin-when-cross-origin')
                        response.close()
