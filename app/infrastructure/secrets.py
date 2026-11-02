from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time

try:
    from cryptography.fernet import Fernet
except ImportError:  # Windows应用控制策略可能拦截cryptography的原生扩展。
    import pyaes

    class Fernet:  # type: ignore[no-redef]
        """与Fernet令牌格式兼容的纯Python后备实现，仅在原生扩展不可用时启用。"""

        def __init__(self, key: bytes) -> None:
            raw = base64.urlsafe_b64decode(key)
            if len(raw) != 32:
                raise ValueError("Fernet key must decode to 32 bytes")
            self.signing_key, self.encryption_key = raw[:16], raw[16:]

        def encrypt(self, data: bytes) -> bytes:
            iv = os.urandom(16)
            encryptor = pyaes.Encrypter(
                pyaes.AESModeOfOperationCBC(self.encryption_key, iv=iv)
            )
            ciphertext = encryptor.feed(data) + encryptor.feed()
            payload = b"\x80" + struct.pack(">Q", int(time.time())) + iv + ciphertext
            signature = hmac.new(self.signing_key, payload, hashlib.sha256).digest()
            return base64.urlsafe_b64encode(payload + signature)

        def decrypt(self, token: bytes) -> bytes:
            raw = base64.urlsafe_b64decode(token)
            if len(raw) < 73 or raw[0] != 0x80:
                raise ValueError("Invalid Fernet token")
            payload, signature = raw[:-32], raw[-32:]
            expected = hmac.new(self.signing_key, payload, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("Invalid Fernet token signature")
            iv, ciphertext = raw[9:25], raw[25:-32]
            decryptor = pyaes.Decrypter(
                pyaes.AESModeOfOperationCBC(self.encryption_key, iv=iv)
            )
            return decryptor.feed(ciphertext) + decryptor.feed()


def _fernet(secret_key: str) -> Fernet:
    if not secret_key:
        raise ValueError("SQLPILOT_SECRET_KEY未配置，无法安全保存数据源密码")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode("utf-8")).digest())
    return Fernet(key)


def protect_secret(value: str, secret_key: str) -> str:
    return "" if not value else _fernet(secret_key).encrypt(value.encode("utf-8")).decode("ascii")


def unprotect_secret(value: str, secret_key: str) -> str:
    return "" if not value else _fernet(secret_key).decrypt(value.encode("ascii")).decode("utf-8")
