from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Priority(str, Enum):
    IMPORTANT = "important"
    REGULAR = "regular"


@dataclass(frozen=True)
class PlannedBump:
    thread_id: int
    priority: Priority


def select_threads_for_window(
    important_threads: list[int],
    regular_threads: list[int],
    active_thread_ids: set[int],
    window_limit: int,
    regular_index: int,
) -> tuple[list[PlannedBump], int]:
    selected: list[PlannedBump] = [
        PlannedBump(thread_id=thread_id, priority=Priority.IMPORTANT)
        for thread_id in important_threads
        if thread_id in active_thread_ids
    ]

    remaining_slots = max(0, window_limit - len(selected))
    if not regular_threads or remaining_slots == 0:
        return selected, 0 if not regular_threads else regular_index % len(regular_threads)

    current_idx = regular_index % len(regular_threads)
    inspected_count = 0
    selected_regular_count = 0
    while inspected_count < len(regular_threads) and selected_regular_count < remaining_slots:
        thread_id = regular_threads[current_idx]
        if thread_id in active_thread_ids:
            selected.append(PlannedBump(thread_id=thread_id, priority=Priority.REGULAR))
            selected_regular_count += 1
        current_idx = (current_idx + 1) % len(regular_threads)
        inspected_count += 1

    return selected, current_idx
