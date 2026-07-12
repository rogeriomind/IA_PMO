from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretEncryptionError(RuntimeError):
    pass


class SecretEncryptionService:
    version = "aesgcm.v1"

    def __init__(self, master_key: str | None):
        self._raw_master_key = (master_key or "").strip()
        self._key = self._normalize_key(self._raw_master_key) if self._raw_master_key else None

    @property
    def configured(self) -> bool:
        return self._key is not None

    def encrypt(self, value: str) -> str:
        if not self._key:
            raise SecretEncryptionError("ENCRYPTION_KEY is required to store tenant secrets")
        nonce = os.urandom(12)
        encrypted = AESGCM(self._key).encrypt(nonce, value.encode("utf-8"), None)
        payload = base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")
        return f"{self.version}:{payload}"

    def decrypt(self, encrypted_value: str) -> str:
        if not self._key:
            raise SecretEncryptionError("ENCRYPTION_KEY is required to read tenant secrets")
        try:
            version, payload = encrypted_value.split(":", 1)
        except ValueError as exc:
            raise SecretEncryptionError("Invalid encrypted secret format") from exc
        if version != self.version:
            raise SecretEncryptionError(f"Unsupported encryption version: {version}")
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        nonce, encrypted = raw[:12], raw[12:]
        return AESGCM(self._key).decrypt(nonce, encrypted, None).decode("utf-8")

    def mask(self, encrypted_value: str) -> str:
        value = self.decrypt(encrypted_value)
        suffix = value[-4:] if len(value) >= 4 else value
        return f"********{suffix}"

    @staticmethod
    def _normalize_key(raw_key: str) -> bytes:
        try:
            decoded = base64.urlsafe_b64decode(raw_key.encode("ascii"))
            if len(decoded) in {16, 24, 32}:
                return decoded
        except Exception:
            pass
        try:
            decoded = bytes.fromhex(raw_key)
            if len(decoded) in {16, 24, 32}:
                return decoded
        except ValueError:
            pass
        return hashlib.sha256(raw_key.encode("utf-8")).digest()
