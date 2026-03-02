from lolz_bump.domain import Priority, select_threads_for_window


def test_select_threads_with_rotation() -> None:
    selected, next_index = select_threads_for_window(
        important_threads=[1, 2, 3],
        regular_threads=[10, 11, 12, 13],
        window_limit=5,
        regular_index=0,
    )

    assert [item.thread_id for item in selected] == [1, 2, 3, 10, 11]
    assert [item.priority for item in selected] == [
        Priority.IMPORTANT,
        Priority.IMPORTANT,
        Priority.IMPORTANT,
        Priority.REGULAR,
        Priority.REGULAR,
    ]
    assert next_index == 2


def test_select_threads_wraps_regular_queue() -> None:
    selected, next_index = select_threads_for_window(
        important_threads=[1],
        regular_threads=[10, 11, 12],
        window_limit=3,
        regular_index=2,
    )

    assert [item.thread_id for item in selected] == [1, 12, 10]
    assert next_index == 1
