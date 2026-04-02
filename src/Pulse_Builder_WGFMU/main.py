# author:
# created at:
# company/institute:

import csv
from typing import Any

from PySide2 import QtWidgets, QtGui, QtCore

import time

from pysweepme.EmptyDeviceClass import EmptyDevice
from pysweepme.ErrorMessage import error
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


# ---------------------------------------------------------------------------
# Current range constants
# ---------------------------------------------------------------------------

_CURRENT_RANGE_OPTIONS = ["1 uA", "10 uA", "100 uA", "1 mA", "10 mA"]
_CURRENT_RANGE_MAP = {
    "1 uA":   wgfmu.CurrentMeasurementRange.RANGE_1uA,
    "10 uA":  wgfmu.CurrentMeasurementRange.RANGE_10uA,
    "100 uA": wgfmu.CurrentMeasurementRange.RANGE_100uA,
    "1 mA":   wgfmu.CurrentMeasurementRange.RANGE_1mA,
    "10 mA":  wgfmu.CurrentMeasurementRange.RANGE_10mA,
}


# ---------------------------------------------------------------------------
# WGFMU table widget — extends TableWidget with measure events and range events
# ---------------------------------------------------------------------------

class WGFMUTableWidget(TableWidget):
    """Two-section table widget for WGFMU sequences.

    Upper section: inherited time-increment / voltage table.
    Middle section: measure events table (start time, points, interval, averaging).
    Lower section: range events table (start time, current range dropdown).
    Load/Save CSV handles all sections in a single file.
    """

    events_changed = QtCore.Signal()  # emitted when measure or range events change

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

        # Extend the layout with a tab widget containing measurement events and range events
        layout = self.layout()

        events_tabs = QtWidgets.QTabWidget(self)
        layout.addWidget(events_tabs)

        # --- Tab 1: Measurement Events ---
        me_tab = QtWidgets.QWidget()
        me_layout = QtWidgets.QVBoxLayout(me_tab)
        me_layout.setContentsMargins(0, 4, 0, 0)

        self._me_table = QtWidgets.QTableWidget(0, 4, me_tab)
        self._me_table.setHorizontalHeaderLabels(
            ["Start time in s", "Points", "Interval in s", "Averaging in s"]
        )
        self._me_table.horizontalHeader().setStretchLastSection(True)
        self._me_table.verticalHeader().setVisible(False)
        self._me_table.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)
        self._me_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        me_layout.addWidget(self._me_table)

        me_btn_bar = QtWidgets.QHBoxLayout()
        self._me_btn_insert = QtWidgets.QPushButton("Insert Above")
        self._me_btn_delete = QtWidgets.QPushButton("Delete Row")
        self._me_btn_clear  = QtWidgets.QPushButton("Clear All")
        me_btn_bar.addWidget(self._me_btn_insert)
        me_btn_bar.addWidget(self._me_btn_delete)
        me_btn_bar.addWidget(self._me_btn_clear)
        me_layout.addLayout(me_btn_bar)

        events_tabs.addTab(me_tab, "Measurement Events")

        self._me_block = False
        self._me_table.cellChanged.connect(self._on_me_cell_changed)
        self._me_btn_insert.clicked.connect(self._me_on_insert_above)
        self._me_btn_delete.clicked.connect(self._me_on_delete_rows)
        self._me_btn_clear.clicked.connect(self._me_clear)

        self._me_add_empty_rows(5)

        # --- Tab 2: Range Events (current mode only) ---
        re_tab = QtWidgets.QWidget()
        re_layout = QtWidgets.QVBoxLayout(re_tab)
        re_layout.setContentsMargins(0, 4, 0, 0)

        self._re_table = QtWidgets.QTableWidget(0, 2, re_tab)
        self._re_table.setHorizontalHeaderLabels(["Start time in s", "Current range"])
        self._re_table.horizontalHeader().setStretchLastSection(True)
        self._re_table.verticalHeader().setVisible(False)
        self._re_table.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)
        self._re_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        re_layout.addWidget(self._re_table)

        re_btn_bar = QtWidgets.QHBoxLayout()
        self._re_btn_insert = QtWidgets.QPushButton("Insert Above")
        self._re_btn_delete = QtWidgets.QPushButton("Delete Row")
        self._re_btn_clear  = QtWidgets.QPushButton("Clear All")
        re_btn_bar.addWidget(self._re_btn_insert)
        re_btn_bar.addWidget(self._re_btn_delete)
        re_btn_bar.addWidget(self._re_btn_clear)
        re_layout.addLayout(re_btn_bar)

        events_tabs.addTab(re_tab, "Range Events")

        self._re_block = False
        self._re_table.cellChanged.connect(self._on_re_cell_changed)
        self._re_btn_insert.clicked.connect(self._re_on_insert_above)
        self._re_btn_delete.clicked.connect(self._re_on_delete_rows)
        self._re_btn_clear.clicked.connect(self._re_clear)

        self._re_add_empty_rows(3)
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
            for col in range(4):
                self._me_table.setItem(r, col, QtWidgets.QTableWidgetItem(''))
        self._me_block = False

    def _me_row_is_empty(self, r):
        for col in range(4):
            it = self._me_table.item(r, col)
            if it is not None and it.text().strip():
                return False
        return True

    def _me_ensure_trailing_empty_row(self):
        rows = self._me_table.rowCount()
        if rows == 0 or not self._me_row_is_empty(rows - 1):
            self._me_block = True
            r = self._me_table.rowCount()
            self._me_table.insertRow(r)
            for col in range(4):
                self._me_table.setItem(r, col, QtWidgets.QTableWidgetItem(''))
            self._me_block = False

    def _me_on_insert_above(self):
        indexes = self._me_table.selectedIndexes()
        row = self._me_table.currentRow() if indexes else max(0, self._me_table.rowCount() - 1)
        self._me_block = True
        self._me_table.insertRow(row)
        for col in range(4):
            self._me_table.setItem(row, col, QtWidgets.QTableWidgetItem(''))
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
                    elif column == 2:  # interval: float >= 10 ns
                        val = float(text)
                        if val >= 1e-8:
                            item.setText("%1.6g" % val)
                            item.setBackground(QtGui.QBrush())
                        else:
                            item.setBackground(self._COLOR_INVALID)
                    else:              # column == 3: averaging: 0 <= avg <= ~21 ms
                        val = float(text)
                        max_average = 0.020971512
                        if 0 <= val <= max_average:
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
        self.events_changed.emit()

    # ------------------------------------------------------------------
    # Measure events — public API
    # ------------------------------------------------------------------

    def get_measure_events(self):
        """Return list of (start_time: float, points: int, interval: float, average: float) for valid rows.

        The averaging value defaults to 0.0 (no averaging) if the column is left empty.
        """
        events = []
        for r in range(self._me_table.rowCount()):
            try:
                it0 = self._me_table.item(r, 0)
                it1 = self._me_table.item(r, 1)
                it2 = self._me_table.item(r, 2)
                it3 = self._me_table.item(r, 3)
                if it0 is None or it1 is None or it2 is None:
                    continue
                t0, t1, t2 = it0.text().strip(), it1.text().strip(), it2.text().strip()
                if not t0 or not t1 or not t2:
                    continue
                start    = float(t0)
                points   = int(t1)
                interval = float(t2)
                average  = float(it3.text().strip()) if (it3 and it3.text().strip()) else 0.0
                if start < 0 or points < 1 or interval < 1e-8:
                    continue
            except Exception:
                continue
            events.append((start, points, interval, average))
        return events

    # ------------------------------------------------------------------
    # Range events table — row management
    # ------------------------------------------------------------------

    def _re_make_combo(self, selected: str = "") -> QtWidgets.QComboBox:
        """Create a QComboBox pre-populated with current range options."""
        combo = QtWidgets.QComboBox()
        combo.addItems(_CURRENT_RANGE_OPTIONS)
        if selected and selected in _CURRENT_RANGE_OPTIONS:
            combo.setCurrentText(selected)
        combo.currentIndexChanged.connect(
            lambda _: None if self._re_block else self.events_changed.emit()
        )
        return combo

    def _re_add_empty_rows(self, n=3):
        self._re_block = True
        for _ in range(n):
            r = self._re_table.rowCount()
            self._re_table.insertRow(r)
            self._re_table.setItem(r, 0, QtWidgets.QTableWidgetItem(''))
            self._re_table.setCellWidget(r, 1, self._re_make_combo())
        self._re_block = False

    def _re_row_is_empty(self, r):
        it = self._re_table.item(r, 0)
        return it is None or it.text().strip() == ''

    def _re_ensure_trailing_empty_row(self):
        rows = self._re_table.rowCount()
        if rows == 0 or not self._re_row_is_empty(rows - 1):
            self._re_block = True
            r = self._re_table.rowCount()
            self._re_table.insertRow(r)
            self._re_table.setItem(r, 0, QtWidgets.QTableWidgetItem(''))
            self._re_table.setCellWidget(r, 1, self._re_make_combo())
            self._re_block = False

    def _re_on_insert_above(self):
        indexes = self._re_table.selectedIndexes()
        row = self._re_table.currentRow() if indexes else max(0, self._re_table.rowCount() - 1)
        self._re_block = True
        self._re_table.insertRow(row)
        self._re_table.setItem(row, 0, QtWidgets.QTableWidgetItem(''))
        self._re_table.setCellWidget(row, 1, self._re_make_combo())
        self._re_block = False

    def _re_on_delete_rows(self):
        rows = sorted(
            {idx.row() for idx in self._re_table.selectedIndexes()},
            reverse=True
        )
        if not rows:
            return
        self._re_block = True
        for r in rows:
            self._re_table.removeRow(r)
        self._re_block = False
        self._re_ensure_trailing_empty_row()

    def _re_clear(self):
        self._re_table.setRowCount(0)
        self._re_add_empty_rows(3)

    # ------------------------------------------------------------------
    # Range events table — cell validation
    # ------------------------------------------------------------------

    def _on_re_cell_changed(self, row, column):
        if self._re_block or column != 0:
            return

        self._re_block = True
        item = self._re_table.item(row, column)
        if item is not None:
            text = item.text().strip()
            if text:
                try:
                    val = float(text)
                    if val >= 0:
                        item.setText("%1.6g" % val)
                        item.setBackground(QtGui.QBrush())
                    else:
                        item.setBackground(self._COLOR_INVALID)
                except ValueError:
                    item.setBackground(self._COLOR_INVALID)
            else:
                item.setBackground(QtGui.QBrush())
        self._re_block = False

        self._re_ensure_trailing_empty_row()
        self.events_changed.emit()

    # ------------------------------------------------------------------
    # Range events — public API
    # ------------------------------------------------------------------

    def get_range_events(self):
        """Return list of (start_time: float, CurrentMeasurementRange) for valid rows."""
        events = []
        for r in range(self._re_table.rowCount()):
            try:
                it0 = self._re_table.item(r, 0)
                if it0 is None or not it0.text().strip():
                    continue
                start_time = float(it0.text().strip())
                if start_time < 0:
                    continue
                combo = self._re_table.cellWidget(r, 1)
                if combo is None:
                    continue
                range_str = combo.currentText()
                if range_str not in _CURRENT_RANGE_MAP:
                    continue
                range_enum = _CURRENT_RANGE_MAP[range_str]
            except Exception:
                continue
            events.append((start_time, range_enum))
        return events

    # ------------------------------------------------------------------
    # Combined CSV — save
    # ------------------------------------------------------------------

    def _on_save_csv(self):
        """Save measure events, range events, and waveform sections to one CSV file."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Sequence to CSV", CSV_DEFAULT_DIR,
            "CSV files (*.csv);;All files (*.*)"
        )
        if not path:
            return
        try:
            events               = self.get_measure_events()
            range_events         = self.get_range_events()
            increments, voltages = self.get_incremental_data()
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                # Measurement events section (4-column)
                writer.writerow(["measure_start", "points", "interval in s", "averaging in s"])
                for start, pts, ivl, avg in events:
                    writer.writerow(["%1.6g" % start, "%d" % pts, "%1.6g" % ivl, "%1.6g" % avg])
                # Range events section
                writer.writerow(["range_start", "current_range"])
                for start_time, range_enum in range_events:
                    range_str = next((k for k, v in _CURRENT_RANGE_MAP.items() if v == range_enum), "")
                    writer.writerow(["%1.6g" % start_time, range_str])
                # Waveform section
                writer.writerow(["time in s", "voltage in V"])
                for x, y in zip(increments, voltages):
                    writer.writerow(["%1.6g" % x, "%1.6g" % y])
        except Exception:
            error()

    # ------------------------------------------------------------------
    # Combined CSV — load
    # ------------------------------------------------------------------

    def _on_load_csv(self):
        """Load measure events, range events, and waveform data from a combined CSV file."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Sequence from CSV", CSV_DEFAULT_DIR,
            "CSV files (*.csv);;All files (*.*)"
        )
        if not path:
            return
        self.load_csv(path)

    def load_csv(self, path) -> None:
        """Load measure events, range events, and waveform data from a combined CSV file.

        File format (sections detected by header row; range events section is optional):
            measure_start,points,interval in s[,averaging in s]  <- 3-col also accepted (avg defaults 0.0)
            0.001,10,0.00001[,0.0]
            range_start,current_range                            <- optional
            0.0005,100 uA
            time in s,voltage in V
            0,0
            0.001,1
        """
        try:
            me_rows  = []
            re_rows  = []
            wf_rows  = []
            section  = None  # "measure" | "range" | "waveform"

            with open(path, newline='') as f:
                for row in csv.reader(f):
                    if not row:
                        continue
                    first = row[0].strip().lower()

                    # Section boundary detection
                    if first == "measure_start":
                        section = "measure"
                        continue
                    if first == "range_start":
                        section = "range"
                        continue
                    if first == "time in s":
                        section = "waveform"
                        continue

                    if section == "measure":
                        if len(row) < 3:
                            continue
                        try:
                            start = float(row[0].strip())
                            pts   = int(row[1].strip())
                            ivl   = float(row[2].strip())
                            avg   = float(row[3].strip()) if len(row) >= 4 and row[3].strip() else 0.0
                            if start >= 0 and pts >= 1 and ivl >= 1e-8:
                                me_rows.append((start, pts, ivl, avg))
                        except ValueError:
                            continue

                    elif section == "range":
                        if len(row) < 2:
                            continue
                        try:
                            start_time = float(row[0].strip())
                            range_str  = row[1].strip()
                            if start_time >= 0 and range_str in _CURRENT_RANGE_MAP:
                                re_rows.append((start_time, range_str))
                        except ValueError:
                            continue

                    elif section == "waveform":
                        if len(row) < 2:
                            continue
                        try:
                            wf_rows.append((float(row[0].strip()), float(row[1].strip())))
                        except ValueError:
                            continue

            # Repopulate measure events table
            self._me_table.setRowCount(0)
            self._me_block = True
            for start, pts, ivl, avg in me_rows:
                r = self._me_table.rowCount()
                self._me_table.insertRow(r)
                self._me_table.setItem(r, 0, QtWidgets.QTableWidgetItem("%1.6g" % start))
                self._me_table.setItem(r, 1, QtWidgets.QTableWidgetItem("%d" % pts))
                self._me_table.setItem(r, 2, QtWidgets.QTableWidgetItem("%1.6g" % ivl))
                self._me_table.setItem(r, 3, QtWidgets.QTableWidgetItem("%1.6g" % avg))
            self._me_block = False
            self._me_ensure_trailing_empty_row()

            # Repopulate range events table
            self._re_table.setRowCount(0)
            self._re_block = True
            for start_time, range_str in re_rows:
                r = self._re_table.rowCount()
                self._re_table.insertRow(r)
                self._re_table.setItem(r, 0, QtWidgets.QTableWidgetItem("%1.6g" % start_time))
                self._re_table.setCellWidget(r, 1, self._re_make_combo(range_str))
            self._re_block = False
            self._re_ensure_trailing_empty_row()

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
# WGFMU plot widget — extends PlotWidget with measurement/range event overlays
# ---------------------------------------------------------------------------

class WGFMUPlotWidget(PlotWidget):
    """PlotWidget variant that overlays measurement event spans and range event markers."""

    def __init__(self):
        super().__init__()
        self._me_events_per_seq: list = []  # list[list[(start, points, interval, avg)]]
        self._re_events_per_seq: list = []  # list[list[(start_time, range_enum)]]
        self._event_artists: list = []      # all overlay matplotlib artists

    def set_segments(self, segments):
        """Redraw sequence lines then refresh overlays."""
        super().set_segments(segments)
        self._redraw_event_overlays()

    def set_measure_events(self, events_per_seq: list) -> None:
        """Update the measurement event spans on the sequence plot.

        events_per_seq: list (one entry per sequence tab) of
                        list of (start_time, points, interval, average).
        """
        self._me_events_per_seq = events_per_seq
        self._redraw_event_overlays()

    def set_range_events(self, events_per_seq: list) -> None:
        """Update the range change event markers on the sequence plot.

        events_per_seq: list (one entry per sequence tab) of
                        list of (start_time, CurrentMeasurementRange).
        """
        self._re_events_per_seq = events_per_seq
        self._redraw_event_overlays()

    def _redraw_event_overlays(self) -> None:
        """Remove all event overlay artists and redraw from stored data."""
        ax = self.seq_canvas.axes

        for artist in self._event_artists:
            try:
                artist.remove()
            except Exception:
                pass
        self._event_artists = []

        # Measurement event spans — shaded region per event, color-matched to sequence.
        # interval is the total measurement window; points are distributed within it.
        for i, events in enumerate(self._me_events_per_seq):
            color = _sequence_color(i)
            for start, _points, interval, _avg in events:
                span = ax.axvspan(
                    start, start + interval,
                    alpha=0.15, color=color, linewidth=0,
                )
                self._event_artists.append(span)

        # Range event markers — vertical dashed line + label at top of axes
        for _i, events in enumerate(self._re_events_per_seq):
            for start_time, range_enum in events:
                line = ax.axvline(
                    start_time, color='gray', linestyle='--', linewidth=1, alpha=0.7,
                )
                range_str = next(
                    (k for k, v in _CURRENT_RANGE_MAP.items() if v == range_enum), ""
                )
                text = ax.text(
                    start_time, 1.0, f" {range_str}",
                    fontsize=7, color='gray', rotation=90,
                    va='top', ha='right',
                    transform=ax.get_xaxis_transform(),
                )
                self._event_artists.append(line)
                self._event_artists.append(text)

        try:
            self.seq_canvas.draw()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# WGFMU sequence tab widget — creates WGFMUTableWidget tabs
# ---------------------------------------------------------------------------

class WGFMUSequenceTabWidget(SequenceTabWidget):
    """SequenceTabWidget that instantiates WGFMUTableWidget instead of TableWidget."""

    sequence_events_changed = QtCore.Signal(list, list)  # (me_events_per_seq, re_events_per_seq)

    def add_sequence_tab(self):
        seq_idx = self.sequence_count()
        table   = WGFMUTableWidget()
        table.data_changed.connect(self._on_any_data_changed)
        table.events_changed.connect(self._on_any_events_changed)

        insert_pos = self.count() - 1 if self._plus_tab_added else self.count()

        self.blockSignals(True)
        self.insertTab(insert_pos, table, "Sequence %d" % (seq_idx + 1))
        self.setTabIcon(insert_pos, _color_icon(_sequence_color(seq_idx)))
        self.setCurrentIndex(insert_pos)
        self.blockSignals(False)

        self._hide_plus_close_button()

    def get_all_events(self) -> tuple[list, list]:
        """Return (me_events_per_seq, re_events_per_seq) for all sequence tabs."""
        me_events, re_events = [], []
        for i in range(self.sequence_count()):
            tab = self.widget(i)
            if isinstance(tab, WGFMUTableWidget):
                me_events.append(tab.get_measure_events())
                re_events.append(tab.get_range_events())
            else:
                me_events.append([])
                re_events.append([])
        return me_events, re_events

    def _on_any_events_changed(self):
        me_events, re_events = self.get_all_events()
        self.sequence_events_changed.emit(me_events, re_events)


# ---------------------------------------------------------------------------
# WGFMU top-level widget — uses WGFMUSequenceTabWidget
# ---------------------------------------------------------------------------

class WGFMUWidget(Widget):
    """Top-level widget variant that uses WGFMU-specific sequence tabs."""

    def __init__(self):
        super().__init__()
        # Connect the events signal that WGFMUSequenceTabWidget provides
        self.sequence_tabs.sequence_events_changed.connect(self._on_sequence_events_changed)

    def _on_sequences_changed(self, sequences):
        """Override to also refresh event overlays whenever sequence data changes."""
        super()._on_sequences_changed(sequences)
        me_events, re_events = self.sequence_tabs.get_all_events()
        self.plot_widget.set_measure_events(me_events)
        self.plot_widget.set_range_events(re_events)

    def _on_sequence_events_changed(self, me_events: list, re_events: list) -> None:
        """Update event overlays when measurement or range events change."""
        self.plot_widget.set_measure_events(me_events)
        self.plot_widget.set_range_events(re_events)

    def _create_layout(self):
        self.plot_widget    = WGFMUPlotWidget()
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
    units     = ["s", ""]   # second unit set dynamically in connect()

    arguments = {
        "Address": "GPIB0::16::INSTR",
        "Slot":    1,
        "Channel": 1,
        "Measure mode": ["Voltage", "Current"],
    }
    execution = "process"

    def __init__(self) -> None:
        """Define instance attributes that will be used across the measurement lifecycle."""
        self.widget = None

        self.measure_mode: str = ""
        self.channel: int = -1
        self.device_communication: dict[str, Any] = {}
        self.device_communication_key: str = ""
        self.is_master: bool = False

        self.is_run_stopped = lambda: False  # will be overridden by SweepMe! with a function that returns True when the measurement run is stopped
        self.measured_timestamps: list[float] = []
        self.measured_voltages: list[float] = []

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

    def connect(self):
        """Load the DLL, open a session, and connect to the channel.

        self.main_arguments is available here before the first main() call.
        Widget data is intentionally not cleared so the user's pulse definition
        is preserved across measurement runs.
        """
        address           = self.main_arguments["Address"]
        slot              = int(self.main_arguments["Slot"])
        channel           = int(self.main_arguments["Channel"])
        self.measure_mode = self.main_arguments["Measure mode"]
        self.channel      = wgfmu.create_channel_id(slot, channel)

        # Reflect measurement type in the output unit column
        self.units = ["s", "V" if "voltage" in self.measure_mode.lower() else "A"]

        # If multiple channels are used by instantiating multiple CFS or Signal driver instances, a master channel
        # can be defined by using the device_communication dict of EmptyDeviceClass
        # TODO: after update to pysweepme, use get_device_communication()
        self.device_communication = EmptyDevice._device_communication
        # The key must mirror the definition in Signal-Keysight_B1500-WGFMU
        self.device_communication_key = f"Signal_Keysight_B1500-WGFMU_{address}"

        if self.device_communication_key not in self.device_communication:
            # First instance, load the dll and connect to the device
            wgfmu.load_dll()

            wgfmu.open_session(address)
            wgfmu.initialize()
            wgfmu.clear()  # clear any previous waveforms and sequences
            self.device_communication[self.device_communication_key] = -1  # will be set to master channel in configure

        # Independent of whether this is the first instance or not, connect to the channel
        wgfmu.connect(self.channel)

    def deinitialize(self):
        """Disconnect the channel and close the WGFMU session."""
        wgfmu.disconnect(self.channel)
        if self.device_communication_key in self.device_communication:
            wgfmu.close_session()
            del self.device_communication[self.device_communication_key]

    def configure(self):
        """Upload patterns and sequences from the widget to the hardware.

        Called every time the module enters an active sequencer branch.
        Reads sequence tabs (time increments, voltages, measure events, range events) and
        the waveform table (playback order + repetitions).
        """
        wgfmu.clear()

        is_current_mode = "current" in self.measure_mode.lower()
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

            pattern_name = f"sweepme_pattern_{self.channel}_{i}"
            wgfmu.create_pattern(pattern_name, voltages[0])
            if len(increments) > 1:
                wgfmu.add_vector_array(pattern_name, increments[1:], voltages[1:])

            for j, (start, points, interval, average) in enumerate(tab.get_measure_events()):
                self.measure_events.append((start, points, interval))
                wgfmu.set_measure_event(
                    pattern_name,
                    event=f"event_{i}_{j}",
                    start_time=start,
                    points=points,
                    interval=interval,
                    average=average,
                    mode="average",
                )

            # Range events are only valid in current measurement mode
            if is_current_mode:
                for k, (start_time, range_enum) in enumerate(tab.get_range_events()):
                    wgfmu.set_range_event(
                        pattern_name,
                        event=f"range_event_{i}_{k}",
                        start_time=start_time,
                        range=range_enum,
                    )

        for seq_id, reps in self.widget.waveform_table.get_waveform_data():
            wgfmu.add_sequence(self.channel, f"sweepme_pattern_{self.channel}_{seq_id - 1}", reps)

        wgfmu.set_operation_mode(self.channel, wgfmu.OperationMode.FASTIV)
        measure_mode = "Voltage" if "voltage" in self.measure_mode.lower() else "Current"
        wgfmu.set_measure_mode(self.channel, measure_mode)

    def measure(self) -> None:
        """Perform the measurement."""
        master_channel = self.device_communication[self.device_communication_key]
        if master_channel < 0:  # no master channel set yet
            self.is_master = True
            self.device_communication[self.device_communication_key] = self.channel
        elif master_channel == self.channel:
            self.is_master = True
        else:
            self.is_master = False

        if self.is_master:
            wgfmu.execute()
            # ensure the measurement is started by waiting for the running state (max 3s)
            start_time = time.time()
            while not self.is_run_stopped() and time.time() - start_time < 3:
                status, _, _ = wgfmu.get_channel_status(self.channel)
                if status == wgfmu.ChannelStatus.RUNNING:
                    break
                time.sleep(0.1)

    def request_result(self) -> None:
        """Each channel waits until its status is not 'RUNNING'."""
        while not self.is_run_stopped():
            status, elapsed_time, estimated_total_time = wgfmu.get_channel_status(self.channel)
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

        completed_points, total_points = wgfmu.get_measure_value_size(self.channel)
        if completed_points < 1:
            msg = "No measurement points completed. Cannot read results."
            raise RuntimeError(msg)
        self.measured_timestamps, self.measured_voltages = wgfmu.get_measure_values(self.channel, 0, completed_points)

    def main(self, **kwargs):
        """Execute the waveform, wait for completion, and return measured data."""
        # TODO: add execution = 'call'
        return self.measured_timestamps, self.measured_voltages
