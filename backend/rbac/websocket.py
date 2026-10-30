"""Revalidate live terminal sessions, including idle connections and bulk DB changes."""
import asyncio
import logging
import re
from contextlib import suppress
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.exceptions import StopConsumer
from django.conf import settings
from rest_framework.authtoken.models import Token

from .k8s_access import can_access_k8s
from .services import user_has_permissions

logger = logging.getLogger(__name__)
TERMINAL_PATH = re.compile(r'^/ws/(ssh|docker/exec|k8s/exec|k8s/terminal)/(\d+)/$')
PERMISSIONS = {
    'ssh': ['ops.host.terminal'],
    'docker/exec': ['ops.docker.view', 'ops.docker.exec'],
    'k8s/exec': ['ops.k8s.exec'],
    'k8s/terminal': ['ops.k8s.terminal'],
}


@database_sync_to_async
def terminal_access_code(token_key, kind, resource_id, namespace):
    token = Token.objects.select_related('user').filter(key=token_key).first()
    if not token or not token.user.is_active:
        return 4401
    if not user_has_permissions(token.user, PERMISSIONS[kind]):
        return 4403
    if kind.startswith('k8s/'):
        from ops.models import K8sCluster
        if not K8sCluster.objects.filter(pk=resource_id).exists():
            return 4404
        if not can_access_k8s(token.user, resource_id, namespace,
                              execute=kind == 'k8s/exec', shell=kind == 'k8s/terminal'):
            return 4403
    return None


class TerminalRevocationMiddleware:
    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        match = TERMINAL_PATH.fullmatch(scope.get('path', ''))
        if not match:
            return await self.application(scope, receive, send)
        kind, resource_id = match.groups()
        query = parse_qs(scope.get('query_string', b'').decode('utf-8', errors='replace'))
        token_key = query.get('token', [''])[0]
        namespace = query.get('namespace', ['default'])[0] or 'default'
        queue = asyncio.Queue()
        accepted = asyncio.Event()
        revoked = False

        async def check():
            try:
                return await terminal_access_code(token_key, kind, resource_id, namespace)
            except Exception:
                logger.exception('Live terminal authorization check failed')
                return 4403

        async def revoke(code):
            nonlocal revoked
            if revoked:
                return
            revoked = True
            await send({'type': 'websocket.close', 'code': code})
            # Trigger consumer cleanup immediately, even without a client disconnect.
            await queue.put({'type': 'websocket.disconnect', 'code': code})

        async def guarded_send(message):
            if revoked:
                if message['type'] == 'websocket.accept':
                    raise StopConsumer()
                return
            if message['type'] == 'websocket.accept':
                code = await check()
                if code:
                    await revoke(code)
                    raise StopConsumer()
                accepted.set()
            await send(message)

        async def forward_input():
            while True:
                message = await receive()
                if message['type'] == 'websocket.receive':
                    code = await check()
                    if code:
                        await revoke(code)
                        return
                await queue.put(message)
                if message['type'] == 'websocket.disconnect':
                    return

        async def watch():
            await accepted.wait()
            interval = max(0.01, min(float(settings.WEBSOCKET_AUTH_RECHECK_SECONDS), 30))
            while not revoked:
                await asyncio.sleep(interval)
                code = await check()
                if code:
                    await revoke(code)

        tasks = [asyncio.create_task(forward_input()), asyncio.create_task(watch())]
        try:
            await self.application(scope, queue.get, guarded_send)
        except StopConsumer:
            pass
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError):
                    await task
