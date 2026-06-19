# author: Franz Hempel
# created at: 01.04.2026
# company/institute: SweepMe!

from pysweepme import FolderManager
FolderManager.addFolderToPATH()

# The reusable pulse-builder GUI lives in libs/pulse_builder.py so that
# hardware-specific variants (e.g. Pulse_Builder_WGFMU) can subclass the same
# widgets. This base CFS simply embeds the unmodified Widget.
from pulse_builder import Widget


class Main():

    variables = []
    units = []

    def __init__(self):
        self.widget = None

    def renew_widget(self, widget=None):
        """Gets the widget from the module and returns the same or creates a new one.
        Called in the main GUI thread."""

        if widget is None:
            self.widget = Widget()
        else:
            self.widget = widget

        return self.widget

    def get_setting(self) -> list[str]:
        """Return the CSV save paths as list[str], if they exist."""
        return self.widget.get_setting()

    def set_setting(self, setting: list[str]) -> None:
        """Receive the CSV save paths and load them into the respective tables."""
        self.widget.set_setting(setting)

    def initialize(self):
        # Preserve the user-defined pulse form across runs — do not clear the table.
        pass

    def main(self):
        return
