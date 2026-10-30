from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class ConfigItemPasswordDecryptionError(Exception):
    pass


def _password_fernet():
    raw_key = getattr(settings, 'CMDB_PASSWORD_ENCRYPTION_KEY', '')
    if isinstance(raw_key, str):
        raw_key = raw_key.strip().encode('utf-8')
    if not raw_key:
        raise ImproperlyConfigured('未配置 CMDB_PASSWORD_ENCRYPTION_KEY，无法保存或查看资产密码。')
    try:
        return Fernet(raw_key)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured('CMDB_PASSWORD_ENCRYPTION_KEY 不是有效的 Fernet 密钥。') from exc


def encrypt_config_item_password(password):
    if password in (None, ''):
        raise ValueError('密码不能为空。')
    return _password_fernet().encrypt(str(password).encode('utf-8')).decode('utf-8')


def decrypt_config_item_password(ciphertext):
    if not ciphertext:
        raise ConfigItemPasswordDecryptionError('资产密码密文为空。')
    try:
        return _password_fernet().decrypt(str(ciphertext).encode('utf-8')).decode('utf-8')
    except InvalidToken as exc:
        raise ConfigItemPasswordDecryptionError('资产密码无法解密，请检查加密密钥是否正确。') from exc
