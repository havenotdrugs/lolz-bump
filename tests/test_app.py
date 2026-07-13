import pytest

from lolz_bump.app import parse_admin_ids
from lolz_bump.cli import main


def test_parse_admin_ids_accepts_comma_separated_positive_ids() -> None:
    assert parse_admin_ids("1, 2,1") == {1, 2}


@pytest.mark.parametrize("value", [None, "", "0", "abc", "1,-2"])
def test_parse_admin_ids_rejects_invalid_values(value: str | None) -> None:
    with pytest.raises(RuntimeError):
        parse_admin_ids(value)


def test_cli_exits_without_traceback_for_missing_runtime_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lolz_bump.app.main", lambda: (_ for _ in ()).throw(RuntimeError("missing token")))

    with pytest.raises(SystemExit, match="1"):
        main()
