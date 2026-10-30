"""
ASGI config for sxdevops project.
Supports both HTTP and WebSocket connections.
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sxdevops.settings')

# Initialize Django ASGI application early to ensure apps are loaded
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from ops.routing import websocket_urlpatterns
from rbac.websocket import TerminalRevocationMiddleware

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': TerminalRevocationMiddleware(URLRouter(websocket_urlpatterns)),
})
