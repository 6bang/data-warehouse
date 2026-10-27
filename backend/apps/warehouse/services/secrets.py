from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    key = settings.INTEGRATION_ENCRYPTION_KEY
    if not key:
        raise ValueError("请先配置 INTEGRATION_ENCRYPTION_KEY，再保存连接凭据（使用 Fernet.generate_key() 生成并安全备份）")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("INTEGRATION_ENCRYPTION_KEY 必须是 URL-safe Base64 编码的 32 字节 Fernet 密钥") from exc


def encrypt_secret(value):
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value):
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("密钥无法解密，请由管理员重新保存") from exc
