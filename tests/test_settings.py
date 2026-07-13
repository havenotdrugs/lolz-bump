import pytest

from lolz_bump.settings import PostingTemplate, SchedulingSettings


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


def test_posting_templates_validate_and_sort_schedule_times() -> None:
    settings = SchedulingSettings(
        posting_templates=[
            PostingTemplate(id=1, name="Рабочий день", schedule_times=["17:00", "06:00", "17:00"])
        ]
    )

    assert settings.posting_templates[0].schedule_times == ["06:00", "17:00"]


def test_settings_rejects_duplicate_posting_template_names_and_ids() -> None:
    with pytest.raises(ValueError, match="posting template names"):
        SchedulingSettings(
            posting_templates=[
                PostingTemplate(id=1, name="Рабочий", schedule_times=["06:00"]),
                PostingTemplate(id=2, name="Рабочий", schedule_times=["12:00"]),
            ]
        )

    with pytest.raises(ValueError, match="posting template ids"):
        SchedulingSettings(
            posting_templates=[
                PostingTemplate(id=1, name="Первый", schedule_times=["06:00"]),
                PostingTemplate(id=1, name="Второй", schedule_times=["12:00"]),
            ]
        )
