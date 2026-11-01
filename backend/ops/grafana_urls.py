"""Validate browser-facing Grafana links before storing configuration."""
import re
from urllib.parse import unquote, urlsplit


def validate_grafana_url(value, *, path_only=False):
    if not isinstance(value, str):
        raise ValueError('Grafana 地址必须为字符串')
    value = value.strip()
    if not value:
        return value
    if re.search(r'[\\\x00-\x20\x7f]', value):
        raise ValueError('Grafana 地址不能包含空白、控制字符或反斜杠')
    try:
        parsed = urlsplit(value)
        if value.startswith('/'):
            decoded_path = unquote(parsed.path, errors='strict')
            if parsed.netloc or decoded_path.startswith('//') or re.search(r'[\\\x00-\x20\x7f]', decoded_path):
                raise ValueError('Grafana 路径必须是本站内的绝对路径')
        elif path_only or parsed.scheme.lower() not in {'http', 'https'} or not value.lower().startswith(('http://', 'https://')) or not parsed.hostname:
            raise ValueError('Grafana 地址仅支持 HTTP、HTTPS 或本站内的绝对路径')
        if parsed.username is not None or parsed.password is not None:
            raise ValueError('Grafana 地址不能包含用户名或密码')
        # Accessing port also validates malformed authorities such as :invalid.
        parsed.port
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f'无效的 Grafana 地址：{exc}') from exc
    return value
