# author:
# created at:
# company/institute:

import csv
from PySide2 import QtWidgets, QtGui, QtCore

import time

from pysweepme import FolderManager
FolderManager.addFolderToPATH()

import wgfmu

from pulse_builder import (
    Widget,
    SequenceTabWidget,
    TableWidget,
    PlotWidget,
    WaveformTableWidget,
    CSV_DEFAULT_DIR,
    _color_icon,
    _sequence_color,
)
from pysweepme.ErrorMessage import error


# ---------------------------------------------------------------------------
# WGFMU table widget — extends TableWidget with measure events table
# ---------------------------------------------------------------------------

class WGFMUTableWidget(TableWidget):
    """Two-section table widget for WGFMU sequences.

    Upper section: inherited time-increment / voltage table.
    Lower section: measure events table (start time, points, interval).
    Load/Save CSV handles both sections in a single file.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Rename time column to reflect that values are increments, not absolute timestamps
        self.table.setHorizontalHeaderLabels(["Time increment in s", "Voltage in V"])

        # Reconnect CSV buttons to combined handlers.
        # (Python MRO already routes self._on_load/save_csv to our overrides, but
        # the explicit disconnect+reconnect makes the intent unambiguous.)
        self.btn_load_csv.clicked.disconnect()
        self.btn_save_csv.clicked.disconnect()
        self.btn_load_csv.clicked.connect(self._on_load_csv)
        self.btn_save_csv.clicked.connect(self._on_save_csv)

        # Extend the layout with the measure events section
        layout = self.layout()

        me_label = QtWidgets.QLabel("Measurement Events")
        me_label.setStyleSheet("font-weight: bold; padding: 2px 0px;")
        layout.addWidget(me_label)

        self._me_table = QtWidgets.QTableWidget(0, 3, self)
        self._me_table.setHorizontalHeaderLabels(["Start time in s", "Points", "Interval in s"])
        self._me_table.horizontalHeader().setStretchLastSection(True)
        self._me_table.verticalHeader().setVisible(False)
        self._me_table.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)
        self._me_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self._me_table)

        me_btn_bar = QtWidgets.QHBoxLayout()
        self._me_btn_insert = QtWidgets.QPushButton("Insert Above")
        self._me_btn_delete = QtWidgets.QPushButton("Delete Row")
        self._me_btn_clear  = QtWidgets.QPushButton("Clear All")
        me_btn_bar.addWidget(self._me_btn_insert)
        me_btn_bar.addWidget(self._me_btn_delete)
        me_btn_bar.addWidget(self._me_btn_clear)
        layout.addLayout(me_btn_bar)

        self._me_block = False
        self._me_table.cellChanged.connect(self._on_me_cell_changed)
        self._me_btn_insert.clicked.connect(self._me_on_insert_above)
        self._me_btn_delete.clicked.connect(self._me_on_delete_rows)
        self._me_btn_clear.clicked.connect(self._me_clear)

        self._me_add_empty_rows(5)
        self.csv_path: str = ""

    # ------------------------------------------------------------------
    # Override: first row's time increment must be 0 (WGFMU constraint)
    # ------------------------------------------------------------------

    def _on_cell_changed(self, row, column):
        super()._on_cell_changed(row, column)
        if row == 0 and column == 0:
            item = self.table.item(row, column)
            if item is not None:
                text = item.text().strip()
                if text and text != '0':
                    item.setBackground(self._COLOR_INVALID)

    # ------------------------------------------------------------------
    # Override: return cumulative timestamps for plotting
    # ------------------------------------------------------------------

    def get_pulse_data(self):
        """Return (cumulative_timestamps, voltages) for plotting."""
        increments, voltages = self.get_incremental_data()
        t = 0.0
        cumulative = []
        for dt in increments:
            t += dt
            cumulative.append(t)
        return cumulative, voltages

    def get_incremental_data(self):
        """Return raw (time_increments, voltages) from the table."""
        xs, ys = [], []
        for r in range(self.table.rowCount()):
            try:
                t = self.table.item(r, 0)
                v = self.table.item(r, 1)
                x = float(t.text().strip())
                y = float(v.text().strip())
            except Exception:
                continue
            xs.append(x)
            ys.append(y)
        return xs, ys

    # ------------------------------------------------------------------
    # Measure events table — row management
    # ------------------------------------------------------------------

    def _me_add_empty_rows(self, n=5):
        self._me_block = True
        for _ in range(n):
            r = self._me_table.rowCount()
            self._me_table.insertRow(r)
            self._me_table.setItem(r, 0, QtWidgets.QTableWidgetItem(''))
            self._me_table.setItem(r, 1, QtWidgets.QTableWidgetItem(''))
            self._me_table.setItem(r, 2, QtWidgets.QTableWidgetItem(''))
        self._me_block = False

    def _me_row_is_empty(self, r):
        it0 = self._me_table.item(r, 0)
        it1 = self._me_table.item(r, 1)
        it2 = self._me_table.item(r, 2)
        return (
            (it0 is None or it0.text().strip() == '') and
            (it1 is None or it1.text().strip() == '') and
            (it2 is None or it2.text().strip() == '')
        )

    def _me_ensure_trailing_empty_row(self):
        rows = self._me_table.rowCount()
        if rows == 0 or not self._me_row_is_empty(rows - 1):
            self._me_block = True
            self._me_table.insertRow(rows)
            self._me_table.setItem(rows, 0, QtWidgets.QTableWidgetItem(''))
            self._me_table.setItem(rows, 1, QtWidgets.QTableWidgetItem(''))
            self._me_table.setItem(rows, 2, QtWidgets.QTableWidgetItem(''))
            self._me_block = False

    def _me_on_insert_above(self):
        indexes = self._me_table.selectedIndexes()
        row = self._me_table.currentRow() if indexes else max(0, self._me_table.rowCount() - 1)
        self._me_block = True
        self._me_table.insertRow(row)
        self._me_table.setItem(row, 0, QtWidgets.QTableWidgetItem(''))
        self._me_table.setItem(row, 1, QtWidgets.QTableWidgetItem(''))
        self._me_table.setItem(row, 2, QtWidgets.QTableWidgetItem(''))
        self._me_block = False

    def _me_on_delete_rows(self):
        rows = sorted(
            {idx.row() for idx in self._me_table.selectedIndexes()},
            reverse=True
        )
        if not rows:
            return
        self._me_block = True
        for r in rows:
            self._me_table.removeRow(r)
        self._me_block = False
        self._me_ensure_trailing_empty_row()

    def _me_clear(self):
        self._me_table.setRowCount(0)
        self._me_add_empty_rows(5)

    # ------------------------------------------------------------------
    # Measure events table — cell validation
    # ------------------------------------------------------------------

    def _on_me_cell_changed(self, row, column):
        if self._me_block:
            return

        self._me_block = True
        item = self._me_table.item(row, column)
        if item is not None:
            text = item.text().strip()
            if text:
                try:
                    if column == 0:    # start time: float >= 0
                        val = float(text)
                        if val >= 0:
                            item.setText("%1.6g" % val)
                            item.setBackground(QtGui.QBrush())
                        else:
                            item.setBackground(self._COLOR_INVALID)
                    elif column == 1:  # points: int >= 1
                        val = int(text)
                        if val >= 1:
                            item.setText("%d" % val)
                            item.setBackground(QtGui.QBrush())
                        else:
                            item.setBackground(self._COLOR_INVALID)
                    else:              # interval: float >= 10 ns
                        val = float(text)
                        if val >= 1e-8:
                            item.setText("%1.6g" % val)
                            item.setBackground(QtGui.QBrush())
                        else:
                            item.setBackground(self._COLOR_INVALID)
                except ValueError:
                    item.setBackground(self._COLOR_INVALID)
            else:
                item.setBackground(QtGui.QBrush())
        self._me_block = False

        self._me_ensure_trailing_empty_row()

    # ------------------------------------------------------------------
    # Measure events — public API
    # ------------------------------------------------------------------

    def get_measure_events(self):
        """Return list of (start_time: float, points: int, interval: float) for valid rows."""
        events = []
        for r in range(self._me_table.rowCount()):
            try:
                it0 = self._me_table.item(r, 0)
                it1 = self._me_table.item(r, 1)
                it2 = self._me_table.item(r, 2)
                if it0 is None or it1 is None or it2 is None:
                    continue
                t0, t1, t2 = it0.text().strip(), it1.text().strip(), it2.text().strip()
                if not t0 or not t1 or not t2:
                    continue
                start    = float(t0)
                points   = int(t1)
                interval = float(t2)
                if start < 0 or points < 1 or interval < 1e-8:
                    continue
            except Exception:
                continue
            events.append((start, points, interval))
        return events

    # ------------------------------------------------------------------
    # Combined CSV — save
    # ------------------------------------------------------------------

    def _on_save_csv(self):
        """Save measure events section then waveform section to one CSV file."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Sequence to CSV", CSV_DEFAULT_DIR,
            "CSV files (*.csv);;All files (*.*)"
        )
        if not path:
            return
        try:
            events               = self.get_measure_events()
            increments, voltages = self.get_incremental_data()
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["measure_start", "points", "interval in s"])
                for start, pts, ivl in events:
                    writer.writerow(["%1.6g" % start, "%d" % pts, "%1.6g" % ivl])
                writer.writerow(["time in s", "voltage in V"])
                for x, y in zip(increments, voltages):
                    writer.writerow(["%1.6g" % x, "%1.6g" % y])
        except Exception:
            error()

    # ------------------------------------------------------------------
    # Combined CSV — load
    # ------------------------------------------------------------------

    def _on_load_csv(self):
        """Load measure events and waveform data from a combined CSV file.

        File format:
            measure_start,points,interval in s   ← section header (skipped)
            0.001,10,0.00001                     ← measure event rows
            time in s,voltage in V               ← section boundary / header
            0,0                                  ← waveform rows
            0.001,1
        """
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Sequence from CSV", CSV_DEFAULT_DIR,
            "CSV files (*.csv);;All files (*.*)"
        )
        if not path:
            return
        self.load_csv(path)

    def load_csv(self, path) -> None:
        """Load measure events and waveform data from a combined CSV file."""
        try:
            me_rows     = []
            wf_rows     = []
            in_waveform = False

            with open(path, newline='') as f:
                for row in csv.reader(f):
                    if not row:
                        continue
                    first = row[0].strip().lower()
                    if first == "time in s":
                        in_waveform = True
                        continue
                    if first == "measure_start":
                        continue  # skip header row
                    if in_waveform:
                        if len(row) < 2:
                            continue
                        try:
                            wf_rows.append((float(row[0].strip()), float(row[1].strip())))
                        except ValueError:
                            continue
                    else:
                        if len(row) < 3:
                            continue
                        try:
                            start = float(row[0].strip())
                            pts   = int(row[1].strip())
                            ivl   = float(row[2].strip())
                            if start >= 0 and pts >= 1 and ivl >= 1e-8:
                                me_rows.append((start, pts, ivl))
                        except ValueError:
                            continue

            # Repopulate measure events table
            self._me_table.setRowCount(0)
            self._me_block = True
            for start, pts, ivl in me_rows:
                r = self._me_table.rowCount()
                self._me_table.insertRow(r)
                self._me_table.setItem(r, 0, QtWidgets.QTableWidgetItem("%1.6g" % start))
                self._me_table.setItem(r, 1, QtWidgets.QTableWidgetItem("%d" % pts))
                self._me_table.setItem(r, 2, QtWidgets.QTableWidgetItem("%1.6g" % ivl))
            self._me_block = False
            self._me_ensure_trailing_empty_row()

            # Repopulate waveform table
            if wf_rows:
                self.table.setRowCount(0)
                self._block_cell_signals = True
                for x, y in wf_rows:
                    r = self.table.rowCount()
                    self.table.insertRow(r)
                    self.table.setItem(r, 0, QtWidgets.QTableWidgetItem("%1.6g" % x))
                    self.table.setItem(r, 1, QtWidgets.QTableWidgetItem("%1.6g" % y))
                self._block_cell_signals = False
                self._ensure_trailing_empty_row()
                self._emit_data_changed()

        except Exception:
            error()
        else:
            self.csv_path = path


# ---------------------------------------------------------------------------
# WGFMU sequence tab widget — creates WGFMUTableWidget tabs
# ---------------------------------------------------------------------------

class WGFMUSequenceTabWidget(SequenceTabWidget):
    """SequenceTabWidget that instantiates WGFMUTableWidget instead of TableWidget."""

    def add_sequence_tab(self):
        seq_idx = self.sequence_count()
        table   = WGFMUTableWidget()
        table.data_changed.connect(self._on_any_data_changed)

        insert_pos = self.count() - 1 if self._plus_tab_added else self.count()

        self.blockSignals(True)
        self.insertTab(insert_pos, table, "Sequence %d" % (seq_idx + 1))
        self.setTabIcon(insert_pos, _color_icon(_sequence_color(seq_idx)))
        self.setCurrentIndex(insert_pos)
        self.blockSignals(False)

        self._hide_plus_close_button()


# ---------------------------------------------------------------------------
# WGFMU top-level widget — uses WGFMUSequenceTabWidget
# ---------------------------------------------------------------------------

class WGFMUWidget(Widget):
    """Top-level widget variant that uses WGFMU-specific sequence tabs."""

    def _create_layout(self):
        self.plot_widget    = PlotWidget()
        self.sequence_tabs  = WGFMUSequenceTabWidget(self)
        self.waveform_table = WaveformTableWidget(self)

        top_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        top_splitter.addWidget(self.plot_widget.seq_canvas)
        top_splitter.addWidget(self.sequence_tabs)
        top_splitter.setSizes([500, 300])

        bot_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        bot_splitter.addWidget(self.plot_widget.wf_canvas)
        bot_splitter.addWidget(self.waveform_table)
        bot_splitter.setSizes([500, 300])

        v_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        v_splitter.addWidget(top_splitter)
        v_splitter.addWidget(bot_splitter)

        grid = QtWidgets.QGridLayout()
        grid.addWidget(v_splitter, 0, 0)
        return grid

    def get_setting(self) -> list[str]:
        """Return a string representation of the current pulse definition csv file paths."""
        csv_paths = []
        for i in range(self.sequence_tabs.count()):
            widget = self.sequence_tabs.widget(i)
            if isinstance(widget, WGFMUTableWidget):
                csv_paths.append(f"sequence_{i+1}: {widget.csv_path}")  # use 1-based indexing for user-readable format

        # add the waveform table csv path if it exists
        if self.waveform_table and hasattr(self.waveform_table, 'csv_path'):
            csv_paths.append(f"waveform_table: {self.waveform_table.csv_path}")
        return csv_paths

    def set_setting(self, setting: list[str]) -> None:
        """Parse the setting string to extract csv file paths and load them into the respective tables."""
        for line in setting:
            if line.startswith("sequence_"):
                try:
                    key, path = line.split(":", 1)
                    idx = int(key.split("_")[1])
                    path = path.strip()
                    if path:
                        # if the tab does not exist yet, add it
                        while idx > self.sequence_tabs.sequence_count():
                            self.sequence_tabs.add_sequence_tab()

                        widget = self.sequence_tabs.widget(idx - 1)  # convert to 0-based index
                        if isinstance(widget, WGFMUTableWidget):
                            widget.load_csv(path)
                except (IndexError, ValueError):
                    continue
            elif line.startswith("waveform_table:"):
                try:
                    _, path = line.split(":", 1)
                    path = path.strip()
                    if path:
                        self.waveform_table.load_csv(path)
                except ValueError:
                    continue

# ---------------------------------------------------------------------------
# SweepMe! CustomFunction entry point
# ---------------------------------------------------------------------------

class Main():

    variables = ["Timestamp", "Measured value"]
    units     = ["s", ""]   # second unit set dynamically in initialize()

    arguments = {
        "Address":                    "GPIB0::16::INSTR",
        "Slot":                       1,
        "Channel":                    1,
        "Measure mode":               ["Voltage", "Current"],
        "Measure event average in s": 0.0,
    }
    execution = "process"

    def renew_widget(self, widget=None):
        """Gets the widget from the module and returns the same or creates a new one.
        Called in the main GUI thread."""

        if widget is None:
            self.widget = WGFMUWidget()
        else:
            self.widget = widget

        return self.widget

    def get_setting(self) -> list[str]:
        """Return the csv save paths as list[str], if they exist."""
        return self.widget.get_setting()

    def set_setting(self, setting: list[str]) -> None:
        """Receive the csv save paths as strings and load them into the respective tables."""
        self.widget.set_setting(setting)

    def initialize(self):
        """Load the DLL, open a session, and connect to the channel.

        self.main_arguments is available here before the first main() call.
        Widget data is intentionally not cleared so the user's pulse definition
        is preserved across measurement runs.
        """
        address              = self.main_arguments["Address"]
        slot                 = int(self.main_arguments["Slot"])
        channel              = int(self.main_arguments["Channel"])
        self.measure_mode    = self.main_arguments["Measure mode"]
        self.measure_average = float(self.main_arguments["Measure event average in s"])
        self.channel_id      = wgfmu.create_channel_id(slot, channel)

        # Reflect measurement type in the output unit column
        self.units = ["s", "V" if "voltage" in self.measure_mode.lower() else "A"]

        wgfmu.load_dll()
        wgfmu.open_session(address)
        wgfmu.initialize()
        wgfmu.clear()  # clear any previous state (patterns, sequences, etc.)
        wgfmu.connect(self.channel_id)

    def deinitialize(self):
        """Disconnect the channel and close the WGFMU session."""
        wgfmu.disconnect(self.channel_id)
        wgfmu.close_session()

    def configure(self):
        """Upload patterns and sequences from the widget to the hardware.

        Called every time the module enters an active sequencer branch.
        Reads sequence tabs (time increments, voltages, measure events) and
        the waveform table (playback order + repetitions).
        """
        wgfmu.clear()

        n_seqs = self.widget.sequence_tabs.sequence_count()
        self.measure_events = []
        for i in range(n_seqs):
            tab = self.widget.sequence_tabs.widget(i)
            increments, voltages = tab.get_incremental_data()
            if not increments:
                continue

            if increments[0] != 0.0:
                raise ValueError(
                    f"Sequence {i + 1}: first time increment must be 0.0 s "
                    f"(got {increments[0]})."
                )

            pattern_name = f"pattern_{i}"
            wgfmu.create_pattern(pattern_name, voltages[0])
            if len(increments) > 1:
                wgfmu.add_vector_array(pattern_name, increments[1:], voltages[1:])

            for j, (start, points, interval) in enumerate(tab.get_measure_events()):
                self.measure_events.append((start, points, interval))
                wgfmu.set_measure_event(
                    pattern_name,
                    event=f"event_{i}_{j}",
                    start_time=start,
                    points=points,
                    interval=interval,
                    average=self.measure_average,
                    mode="average",
                )

        for seq_id, reps in self.widget.waveform_table.get_waveform_data():
            wgfmu.add_sequence(self.channel_id, f"pattern_{seq_id - 1}", reps)

        wgfmu.set_operation_mode(self.channel_id, wgfmu.OperationMode.FASTIV)
        measure_mode = "Voltage" if "voltage" in self.measure_mode.lower() else "Current"
        wgfmu.set_measure_mode(self.channel_id, measure_mode)

    def measure(self) -> None:
        """Perform the measurement."""
        wgfmu.execute()
        time.sleep(1)
        # TODO: wait for the status to be RUNNING

    def request_result(self) -> None:
        """Each channel waits until its status is not 'RUNNING'."""
        while True:
            if self.is_run_stopped():
                break

            status, elapsed_time, estimated_total_time = wgfmu.get_channel_status(self.channel_id)
            if status != wgfmu.ChannelStatus.RUNNING:
                break

            if elapsed_time > 2 * estimated_total_time:
                msg = f"Measurement is taking much longer than estimated (elapsed: {elapsed_time:.2f}s, estimated total: {estimated_total_time:.2f}s). Stopping measurement."
                raise RuntimeError(msg)

            time.sleep(0.5)

    def read_result(self) -> None:
        """Read the results."""
        if not self.measure_events:
            # No measurement events defined, so no results to read
            return

        completed_points, total_points = wgfmu.get_measure_value_size(self.channel_id)
        if completed_points < 1:
            msg = "No measurement points completed. Cannot read results."
            raise RuntimeError(msg)
        self.measured_timestamps, self.measured_voltages = wgfmu.get_measure_values(self.channel_id, 0, completed_points)

    def main(self, **kwargs):
        """Execute the waveform, wait for completion, and return measured data."""
        # wgfmu.execute()
        #
        # while True:
        #     status, elapsed, estimated = wgfmu.get_channel_status(self.channel_id)
        #     if status != wgfmu.ChannelStatus.RUNNING:
        #         break
        #     if estimated > 0 and elapsed > 2 * estimated:
        #         raise RuntimeError(
        #             f"Measurement timeout "
        #             f"(elapsed {elapsed:.2f} s, estimated {estimated:.2f} s)."
        #         )
        #     time.sleep(0.05)
        #
        # completed, _total = wgfmu.get_measure_value_size(self.channel_id)
        # if completed < 1:
        #     return [], []

        # timestamps, values = wgfmu.get_measure_values(self.channel_id, 0, completed)

        # TODO: add execution = 'call'
        return self.measured_timestamps, self.measured_voltages
