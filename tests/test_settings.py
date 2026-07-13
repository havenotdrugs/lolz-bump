import pytest

from lolz_bump.settings import SchedulingSettings


def test_empty_settings_are_valid_until_an_admin_configures_the_bot() -> None:
    settings = SchedulingSettings()

    assert settings.window_limit == 1
    assert settings.all_schedule_times() == []
    assert settings.important_threads == []
    assert settings.regular_threads == []


def test_settings_rejects_too_many_important_threads_for_one_window() -> None:
    with pytest.raises(ValueError, match="important_threads"):
        SchedulingSettings(
            window_limit=1,
            schedule_times=["06:00"],
            important_threads=[1, 2],
        )


def test_settings_adds_default_domain_for_existing_threads() -> None:
    settings = SchedulingSettings.model_validate(
        {
            "important_threads": [1],
            "regular_threads": [2],
            "thread_domains": {"1": "zelenka.guru", "2": ""},
        }
    )

    assert settings.thread_domains == {1: "zelenka.guru", 2: "lolz.live"}
