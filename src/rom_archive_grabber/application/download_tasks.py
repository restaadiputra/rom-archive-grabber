import asyncio
from collections.abc import Callable, Coroutine
from typing import Any


class DownloadTasks:
    """The asyncio tasks of a download queue: one current task per job id,
    plus cancelled tasks that have not finished unwinding yet."""

    def __init__(self) -> None:
        self._current: dict[str, asyncio.Task[None]] = {}
        self._stopping: dict[asyncio.Task[None], str] = {}

    def __len__(self) -> int:
        return len(self._current)

    def start(self, job_id: str, run: Coroutine[Any, Any, None]) -> None:
        self._current[job_id] = asyncio.create_task(run)

    def is_current(self, job_id: str) -> bool:
        """True inside the task that currently runs `job_id`."""
        return self._current.get(job_id) is asyncio.current_task()

    def finish(self, job_id: str) -> None:
        del self._current[job_id]

    def stop(self, job_id: str) -> None:
        task = self._current.pop(job_id, None)
        if task is None:
            return
        task.cancel()
        self._stopping[task] = job_id
        task.add_done_callback(self._forget_stopped)

    def stop_all(self) -> None:
        for job_id in list(self._current):
            self.stop(job_id)

    async def wait_stopped(self) -> None:
        await asyncio.gather(*self._stopping, return_exceptions=True)

    def when_stopped(self, job_id: str, callback: Callable[[], None]) -> None:
        """Call `callback` once no task of `job_id` is still unwinding (now if none is)."""
        pending = [task for task, owner in self._stopping.items() if owner == job_id]
        if not pending:
            callback()
            return

        def after(_: asyncio.Task[None]) -> None:
            # Done callbacks run in the order added, so `_forget_stopped`
            # has already dropped this task.
            if job_id not in self._stopping.values():
                callback()

        for task in pending:
            task.add_done_callback(after)

    def _forget_stopped(self, task: asyncio.Task[None]) -> None:
        self._stopping.pop(task, None)
