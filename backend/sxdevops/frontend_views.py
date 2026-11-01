import mimetypes
from pathlib import Path

from django.http import FileResponse, Http404


FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent.parent / 'frontend' / 'dist'


def _serve_file(file_path, cache_control=None):
    if not file_path.exists() or not file_path.is_file():
        raise Http404('Frontend asset not found')
    content_type, _ = mimetypes.guess_type(file_path.name)
    response = FileResponse(open(file_path, 'rb'), content_type=content_type)
    if cache_control:
        response['Cache-Control'] = cache_control
    return response


def frontend_index(request):
    response = _serve_file(FRONTEND_DIST_DIR / 'index.html', cache_control='no-cache, no-store, must-revalidate')
    response['Content-Security-Policy'] = (
        "script-src 'self'; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'self'"
    )
    response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    return response


def frontend_asset(request, path):
    safe_path = (FRONTEND_DIST_DIR / path).resolve()
    if FRONTEND_DIST_DIR.resolve() not in safe_path.parents and safe_path != FRONTEND_DIST_DIR.resolve():
        raise Http404('Invalid asset path')
    cache_control = 'no-cache' if path == 'assets/theme-init.js' else 'public, max-age=31536000, immutable'
    return _serve_file(safe_path, cache_control=cache_control)
