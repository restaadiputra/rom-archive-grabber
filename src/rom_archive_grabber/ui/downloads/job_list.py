from textual.widgets import ListView

from rom_archive_grabber.domain.models import DownloadJob
from rom_archive_grabber.ui.downloads.job_row import JobRow


class JobList(ListView):
    """A list of job rows kept in step with a list of jobs.

    Rows are updated in place and only added, removed or moved when the jobs
    themselves change, so progress ticks neither flicker nor lose the highlight.
    """

    def rows(self) -> list[JobRow]:
        return [child for child in self.children if isinstance(child, JobRow)]

    def highlighted_row(self) -> JobRow | None:
        child = self.highlighted_child
        return child if isinstance(child, JobRow) else None

    async def sync(self, jobs: list[DownloadJob]) -> None:
        kept = self.highlighted_row()
        wanted = {job.id for job in jobs}
        gone = [index for index, row in enumerate(self.rows()) if row.job.id not in wanted]
        if gone:
            await self.remove_items(gone)
        existing = {row.job.id: row for row in self.rows()}
        for index, job in enumerate(jobs):
            row = existing.get(job.id)
            if row is None:
                await self.insert(index, [JobRow(job)])
            else:
                row.show(job)
                # Rows before `index` are already in place, so this row is at or after it.
                if self.rows()[index] is not row:
                    self.move_child(row, before=index)
        self._restore_highlight(kept)

    def _restore_highlight(self, kept: JobRow | None) -> None:
        rows = self.rows()
        if not rows:
            return
        # When the highlighted job left the list, the row now at its place takes over.
        target = kept if kept in rows else rows[min(self.index or 0, len(rows) - 1)]
        # Moved rows carry their old highlight; only the target keeps one.
        for row in rows:
            row.highlighted = row is target
        self.index = rows.index(target)
