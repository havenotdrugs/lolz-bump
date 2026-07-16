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
) -> list[PlannedBump]:
    selected: list[PlannedBump] = [
        PlannedBump(thread_id=thread_id, priority=Priority.IMPORTANT)
        for thread_id in important_threads
        if thread_id in active_thread_ids
    ]
    selected.extend(
        PlannedBump(thread_id=thread_id, priority=Priority.REGULAR)
        for thread_id in regular_threads
        if thread_id in active_thread_ids
    )
    return selected
