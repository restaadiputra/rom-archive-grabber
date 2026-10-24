from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from textual.command import DiscoveryHit, Hit, Hits, Provider


@dataclass(frozen=True, slots=True)
class AppCommand:
    """A palette entry that runs an app action, such as `refresh_all`."""

    title: str
    help: str
    action: str


# Add a command here and an `action_<name>` method on the app to offer it.
COMMANDS = (
    AppCommand("Add source", "Add an archive or list to browse", "add_source"),
    AppCommand("Refresh all sources", "List every source again", "refresh_all"),
    AppCommand("Download marked", "Queue the marked files, or the one selected", "download_marked"),
    AppCommand("Pause all", "Pause every queued and running download", "pause_all"),
    AppCommand("Resume all", "Resume every paused download", "resume_all"),
    AppCommand("Open download folder", "Show the download folder", "open_download_folder"),
    AppCommand("Switch tab", "Move between Browse and Downloads", "switch_tab"),
)


class AppCommands(Provider):
    """The app's own commands in the ctrl+p palette."""

    async def discover(self) -> Hits:
        for command in COMMANDS:
            yield DiscoveryHit(command.title, self._runner(command), help=command.help)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for command in COMMANDS:
            score = matcher.match(command.title)
            if score > 0:
                runner = self._runner(command)
                yield Hit(score, matcher.highlight(command.title), runner, help=command.help)

    def _runner(self, command: AppCommand) -> Callable[[], object]:
        return partial(self.app.run_action, command.action)
