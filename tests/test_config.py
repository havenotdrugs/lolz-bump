from pathlib import Path

import pytest

from lolz_bump.config import ConfigError, load_config


def test_load_config_success(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
window_limit: 5
timezone: Europe/Moscow
schedule_times:
  - "06:00"
  - "18:00"
important_threads: [1, 2, 3]
regular_threads: [10, 11]
""".strip()
    )

    config = load_config(config_path)

    assert config.window_limit == 5
    assert config.api_timeout_seconds == 30.0
    assert config.schedule_times == ["06:00", "18:00"]
    assert config.all_schedule_times() == ["06:00", "18:00"]


def test_load_config_custom_api_timeout(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
window_limit: 5
api_timeout_seconds: 12.5
timezone: Europe/Moscow
schedule_times:
  - "06:00"
important_threads: []
regular_threads: []
""".strip()
    )

    config = load_config(config_path)
    assert config.api_timeout_seconds == 12.5


def test_load_config_rejects_too_many_important(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
window_limit: 2
timezone: Europe/Moscow
schedule_times:
  - "06:00"
important_threads: [1, 2, 3]
regular_threads: []
""".strip()
    )

    with pytest.raises(ConfigError):
        load_config(config_path)


def test_load_config_rejects_invalid_time(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
window_limit: 5
timezone: Europe/Moscow
schedule_times:
  - "25:00"
important_threads: []
regular_threads: [10]
""".strip()
    )

    with pytest.raises(ConfigError):
        load_config(config_path)


def test_load_config_rejects_non_positive_api_timeout(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
window_limit: 5
api_timeout_seconds: 0
timezone: Europe/Moscow
schedule_times:
  - "06:00"
important_threads: []
regular_threads: []
""".strip()
    )

    with pytest.raises(ConfigError):
        load_config(config_path)


def test_load_config_allows_null_thread_lists(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
window_limit: 5
timezone: Europe/Moscow
schedule_times:
  - "06:00"
important_threads:
regular_threads:
""".strip()
    )

    config = load_config(config_path)
    assert config.important_threads == []
    assert config.regular_threads == []


def test_load_config_accepts_thread_schedule_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
window_limit: 2
timezone: Europe/Moscow
schedule_times:
  - "06:00"
important_threads: [1]
regular_threads: [10, 11]
thread_schedule_overrides:
  10:
    - "12:00"
  11:
    - "06:00"
    - "18:00"
""".strip()
    )

    config = load_config(config_path)

    assert config.schedule_times_for_thread(1) == ["06:00"]
    assert config.schedule_times_for_thread(10) == ["12:00"]
    assert config.schedule_times_for_thread(11) == ["06:00", "18:00"]
    assert config.all_schedule_times() == ["06:00", "12:00", "18:00"]


def test_load_config_rejects_unknown_thread_schedule_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
window_limit: 2
timezone: Europe/Moscow
schedule_times:
  - "06:00"
important_threads: [1]
regular_threads: [10]
thread_schedule_overrides:
  99:
    - "12:00"
""".strip()
    )

    with pytest.raises(ConfigError):
        load_config(config_path)


def test_load_config_rejects_too_many_important_for_same_schedule(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
window_limit: 1
timezone: Europe/Moscow
schedule_times:
  - "06:00"
important_threads: [1, 2]
regular_threads: []
thread_schedule_overrides:
  1:
    - "06:00"
  2:
    - "06:00"
""".strip()
    )

    with pytest.raises(ConfigError):
        load_config(config_path)
