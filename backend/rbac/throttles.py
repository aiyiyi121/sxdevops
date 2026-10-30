import hashlib

from rest_framework.throttling import SimpleRateThrottle


class LoginIPThrottle(SimpleRateThrottle):
    scope = 'rbac_login_ip'
    rate = '30/min'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class LoginAccountThrottle(SimpleRateThrottle):
    scope = 'rbac_login_account'
    rate = '10/min'

    def get_cache_key(self, request, view):
        data = request.data if isinstance(request.data, dict) else {}
        username = str(data.get('username', '')).strip().casefold()
        ident = hashlib.sha256(username.encode('utf-8')).hexdigest()
        return self.cache_format % {'scope': self.scope, 'ident': ident}
