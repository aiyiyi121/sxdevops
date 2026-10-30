import hashlib
import ipaddress
import logging
import time

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle

logger = logging.getLogger(__name__)


def client_ip(request):
    peer = request.META.get('REMOTE_ADDR', '')
    def trusted(value):
        address = ipaddress.ip_address(value)
        return any(address in network for network in networks)

    try:
        networks = [ipaddress.ip_network(value, strict=False) for value in settings.LOGIN_TRUSTED_PROXIES]
        if not trusted(peer):
            return peer
        chain = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')
        for value in reversed(chain):
            value = value.strip()
            if value and not trusted(value):
                return str(ipaddress.ip_address(value))
    except ValueError:
        return peer
    return peer


class AtomicLoginThrottle(SimpleRateThrottle):
    """Fixed-window limits using atomic add/incr on the shared Redis cache."""
    def allow_request(self, request, view):
        if self.rate is None:
            return True
        key = self.get_cache_key(request, view)
        now = time.time()
        bucket = int(now // self.duration)
        self.remaining_wait = max(1, (bucket + 1) * self.duration - now)
        try:
            bucket_key = f'{key}:{bucket}'
            if self.cache.add(bucket_key, 1, timeout=self.duration + 1):
                count = 1
            else:
                count = self.cache.incr(bucket_key)
            return count <= self.num_requests
        except Exception:
            logger.exception('Login rate-limit cache unavailable')
            return False

    def wait(self):
        return self.remaining_wait


class LoginIPThrottle(AtomicLoginThrottle):
    scope = 'rbac_login_ip'
    rate = '30/min'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': client_ip(request)}


class LoginAccountThrottle(AtomicLoginThrottle):
    scope = 'rbac_login_account'
    rate = '10/min'

    def get_cache_key(self, request, view):
        data = request.data if isinstance(request.data, dict) else {}
        username = str(data.get('username', '')).strip().casefold()
        ident = hashlib.sha256(username.encode('utf-8')).hexdigest()
        return self.cache_format % {'scope': self.scope, 'ident': ident}
