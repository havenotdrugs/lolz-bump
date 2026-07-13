import stat
from pathlib import Path

from lolz_bump.secrets import SecretStore


def test_secret_store_creates_private_stable_key_and_encrypts_token(tmp_path: Path) -> None:
    key_path = tmp_path / "secrets" / "app.key"

    store = SecretStore(key_path)
    encrypted = store.encrypt("lolz-token")

    assert key_path.exists()
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    assert "lolz-token" not in encrypted
    assert store.decrypt(encrypted) == "lolz-token"
    assert SecretStore(key_path).decrypt(encrypted) == "lolz-token"
