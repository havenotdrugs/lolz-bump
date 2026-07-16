from lolz_bump.domain import Priority, select_threads_for_window


def test_selects_all_active_threads_in_priority_order() -> None:
    selected = select_threads_for_window(
        important_threads=[1],
        regular_threads=[10, 11],
        active_thread_ids={1, 10, 11},
    )

    assert [item.thread_id for item in selected] == [1, 10, 11]
    assert [item.priority for item in selected] == [
        Priority.IMPORTANT,
        Priority.REGULAR,
        Priority.REGULAR,
    ]


def test_selects_all_active_threads() -> None:
    selected = select_threads_for_window(
        important_threads=[1, 2, 3],
        regular_threads=[10, 11, 12, 13],
        active_thread_ids={1, 2, 3, 10, 11, 12, 13},
    )

    assert [item.thread_id for item in selected] == [1, 2, 3, 10, 11, 12, 13]
    assert [item.priority for item in selected] == [
        Priority.IMPORTANT,
        Priority.IMPORTANT,
        Priority.IMPORTANT,
        Priority.REGULAR,
        Priority.REGULAR,
        Priority.REGULAR,
        Priority.REGULAR,
    ]


def test_select_threads_skips_inactive_threads() -> None:
    selected = select_threads_for_window(
        important_threads=[1],
        regular_threads=[10, 11, 12, 13],
        active_thread_ids={1, 11, 13},
    )

    assert [item.thread_id for item in selected] == [1, 11, 13]
