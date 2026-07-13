from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class SecretStore:
    def __init__(self, key_path: str | Path) -> None:
        self._key_path = Path(key_path)
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        self._key_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._key_path.parent.chmod(0o700)
        try:
            descriptor = os.open(self._key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            key = self._key_path.read_bytes()
            self._key_path.chmod(0o600)
            return key
        with os.fdopen(descriptor, "wb") as file:
            key = Fernet.generate_key()
            file.write(key)
        return key

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("stored token cannot be decrypted") from exc
