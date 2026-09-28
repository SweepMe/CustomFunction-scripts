# author: Franz Hempel
# created on: 2026-06-19
# company/institute: SweepMe!
"""CustomFunction script: Pulse Builder for the Keithley 4200A-SCS PMU (SegArb via KXCI).

The pulse sequences are defined segment by segment like in the SegArb dialog of Clarius: each row of a sequence tab
is one segment with start voltage, stop voltage, segment time, measure enable, optional measure window, SSR and
trigger output. Each sequence tab becomes one SegArb sequence on the instrument, the waveform table of the shared
Pulse Builder GUI (libs/pulse_builder.py) becomes the SegArb sequence list. The captured voltage, current and
timestamp are returned as three arrays.
"""
from __future__ import annotations

import csv
import time

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from pysweepme import FolderManager, Ports
from pysweepme.ErrorMessage import error
FolderManager.addFolderToPATH()  # makes libs/kxci_pmu.py and libs/pulse_builder.py importable

import importlib
import kxci_pmu

importlib.reload(kxci_pmu)

from kxci_pmu import KXCIPMU
from pulse_builder import (
    Widget,
    PlotWidget,
    SequenceTabWidget,
    WaveformTableWidget,
    CSV_DEFAULT_DIR,
    _color_icon,
    _sequence_color,
)


# SegArb timing limits (KXCI manual, :PMU:SARB:SEQ:TIME)
SEGMENT_TIME_RESOLUTION = 10e-9
SEGMENT_TIME_MIN = 20e-9
MAX_SEGMENTS_PER_SEQUENCE = 128  # one :PMU:SARB:SEQ:* call; the ...:ADD variants are not wrapped yet

START_TIMEOUT_S = 10.0  # max. time between :PMU:EXECUTE and the test reporting RUNNING

# Measure types of :PMU:SARB:SEQ:MEAS:TYPE, applied to all segments with "Measure" checked
MEASURE_TYPES = {
    "Waveform discrete": KXCIPMU.MEAS_WAVEFORM_DISCRETE,
    "Waveform average": KXCIPMU.MEAS_WAVEFORM_AVERAGE,
    "Spot mean discrete": KXCIPMU.MEAS_SPOT_MEAN_DISCRETE,
    "Spot mean average": KXCIPMU.MEAS_SPOT_MEAN_AVERAGE,
}
SPOT_MEAN_TYPES = {KXCIPMU.MEAS_SPOT_MEAN_DISCRETE, KXCIPMU.MEAS_SPOT_MEAN_AVERAGE}

# Segment table columns, in the order of the Clarius SegArb dialog
(
    COL_START_V, COL_STOP_V, COL_TIME, COL_MEASURE, COL_MEAS_START, COL_MEAS_STOP, COL_SSR, COL_TRIGGER,
) = range(8)
SEGMENT_HEADERS = [
    "Start voltage in V", "Stop voltage in V", "Segment time in s", "Measure",
    "Measure start in s", "Measure stop in s", "SSR", "Trigger out",
]
SEGMENT_TOOLTIPS = [
    "Voltage at the start of the segment; must equal the stop voltage of the previous segment",
    "Voltage at the end of the segment",
    f"Duration of the segment, min. {SEGMENT_TIME_MIN:g} s in steps of {SEGMENT_TIME_RESOLUTION:g} s",
    "Checked = measure this segment with the selected measure type",
    "Start of the measurement relative to the segment start; empty = 0 s",
    "Stop of the measurement relative to the segment start; empty = end of the segment",
    "Checked = output relay closed (segment is output), unchecked = open (output floating); relay transitions need "
    ">= 25 us",
    "Checked = trigger output high during this segment, unchecked = low",
]
FLAG_COLUMNS = {COL_MEASURE: 1, COL_SSR: 1, COL_TRIGGER: 0}  # checkbox column -> default state of a new row


# ---------------------------------------------------------------------------
# Segment rules and conversion to the SegArb arrays
# ---------------------------------------------------------------------------

def segment_problems(segment: dict, previous_stop_v: float | None) -> list[tuple[int, str]]:
    """Check one segment against the SegArb rules.

    Returns a list of (column, message) - empty if the segment is valid. Used both for highlighting cells in the
    table and for the checks before a run.
    """
    problems = []

    if previous_stop_v is not None and segment["start_v"] != previous_stop_v:
        problems.append((COL_START_V, (
            f"start voltage {segment['start_v']:g} V differs from the stop voltage {previous_stop_v:g} V of the "
            f"previous segment; SegArb transitions must be seamless."
        )))

    duration = segment["time"]
    steps = round(duration / SEGMENT_TIME_RESOLUTION)
    if steps * SEGMENT_TIME_RESOLUTION < SEGMENT_TIME_MIN - 1e-15:
        problems.append((COL_TIME, f"segment time {duration:g} s is below the minimum of {SEGMENT_TIME_MIN:g} s."))
    elif abs(duration / SEGMENT_TIME_RESOLUTION - steps) > 1e-3:
        problems.append((COL_TIME, f"segment time {duration:g} s is not a multiple of {SEGMENT_TIME_RESOLUTION:g} s."))

    if segment["measure"]:
        meas_start = 0.0 if segment["meas_start"] is None else segment["meas_start"]
        meas_stop = duration if segment["meas_stop"] is None else segment["meas_stop"]
        if not 0.0 <= meas_start < meas_stop <= duration + 1e-15:
            column = COL_MEAS_START if not 0.0 <= meas_start < duration else COL_MEAS_STOP
            problems.append((column, (
                f"measure window {meas_start:g} s to {meas_stop:g} s must satisfy "
                f"0 <= start < stop <= segment time ({duration:g} s)."
            )))

    return problems


def build_segments(sequence_number: int, segments: list[dict], measure_type: int) -> dict:
    """Convert the validated segments of one sequence tab into the SegArb arrays.

    Segments with "measure" = 1 get measure_type and their measure window (empty start/stop = whole segment);
    all others get MEAS_NONE with a 0/0 window.

    Returns:
        dict with the lists "times", "start_v", "stop_v", "meas_types", "meas_starts", "meas_stops", "ssr", "trig".
    """
    label = f"Sequence {sequence_number}"
    if not segments:
        raise ValueError(f"{label}: at least one segment is required.")
    if len(segments) > MAX_SEGMENTS_PER_SEQUENCE:
        raise ValueError(
            f"{label}: {len(segments)} segments exceed the maximum of {MAX_SEGMENTS_PER_SEQUENCE} per sequence."
        )

    arrays = {key: [] for key in ("times", "start_v", "stop_v", "meas_types", "meas_starts", "meas_stops", "ssr",
                                  "trig")}
    for segment in segments:
        duration = round(round(segment["time"] / SEGMENT_TIME_RESOLUTION) * SEGMENT_TIME_RESOLUTION, 10)
        if segment["measure"]:
            meas_type = measure_type
            meas_start = 0.0 if segment["meas_start"] is None else segment["meas_start"]
            meas_stop = duration if segment["meas_stop"] is None else segment["meas_stop"]
        else:
            meas_type, meas_start, meas_stop = KXCIPMU.MEAS_NONE, 0.0, 0.0

        arrays["times"].append(duration)
        arrays["start_v"].append(segment["start_v"])
        arrays["stop_v"].append(segment["stop_v"])
        arrays["meas_types"].append(meas_type)
        arrays["meas_starts"].append(meas_start)
        arrays["meas_stops"].append(meas_stop)
        arrays["ssr"].append(segment["ssr"])
        arrays["trig"].append(segment["trigger"])

    return arrays


def check_sequence_list(sequences: dict, sequence_list: list[tuple[int, int]]) -> None:
    """Check that the playback order yields a seamless waveform.

    SegArb requires the stop voltage of each sequence to equal the start voltage of the next one - also between
    two repetitions of the same sequence.
    """
    previous = None
    for seq_id, reps in sequence_list:
        start_v, stop_v = sequences[seq_id]["start_v"][0], sequences[seq_id]["stop_v"][-1]
        if reps > 1 and stop_v != start_v:
            raise ValueError(
                f"Sequence {seq_id} is repeated {reps} times, but ends at {stop_v:g} V and starts at {start_v:g} V. "
                f"Repeated sequences must end at their start voltage."
            )
        if previous is not None and sequences[previous]["stop_v"][-1] != start_v:
            raise ValueError(
                f"Sequence {previous} ends at {sequences[previous]['stop_v'][-1]:g} V, but the following sequence "
                f"{seq_id} starts at {start_v:g} V. Consecutive sequences must connect seamlessly."
            )
        previous = seq_id


# ---------------------------------------------------------------------------
# GUI: segment table (one per sequence tab)
# ---------------------------------------------------------------------------

class SegmentTableWidget(QtWidgets.QWidget):
    """Editable SegArb segment table, one row per segment (like the SegArb dialog of Clarius).

    Provides the table API the shared Pulse Builder relies on: the data_changed signal and get_pulse_data() for
    the plots, csv_path / load_csv() for the setting file and clear_data(). Invalid cells are highlighted in red
    with the reason as tooltip, without overwriting the user's text.
    """

    data_changed = QtCore.Signal(list, list)

    _COLOR_INVALID = QtGui.QColor(255, 180, 180)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.table = QtWidgets.QTableWidget(0, len(SEGMENT_HEADERS), self)
        self.table.setHorizontalHeaderLabels(SEGMENT_HEADERS)
        for column, tooltip in enumerate(SEGMENT_TOOLTIPS):
            self.table.horizontalHeaderItem(column).setToolTip(tooltip)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.verticalHeader().setToolTip("Segment number")  # row numbers = segment numbers
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        btn_bar = QtWidgets.QHBoxLayout()
        self.btn_insert = QtWidgets.QPushButton("Insert Above")
        self.btn_delete = QtWidgets.QPushButton("Delete Row")
        self.btn_clear = QtWidgets.QPushButton("Clear All")
        self.btn_load_csv = QtWidgets.QPushButton("Load from CSV")
        self.btn_save_csv = QtWidgets.QPushButton("Save to CSV")
        for button in (self.btn_insert, self.btn_delete, self.btn_clear, self.btn_load_csv, self.btn_save_csv):
            btn_bar.addWidget(button)
        layout.addLayout(btn_bar)

        self._block_cell_signals = False
        self.table.cellChanged.connect(self._on_cell_changed)
        self.btn_insert.clicked.connect(self._on_insert_above)
        self.btn_delete.clicked.connect(self._on_delete_rows)
        self.btn_clear.clicked.connect(self.clear_data)
        self.btn_load_csv.clicked.connect(self._on_load_csv)
        self.btn_save_csv.clicked.connect(self._on_save_csv)

        self._add_empty_rows(10)

        self.csv_path: str = ""

    # ------------------------------------------------------------------
    # Row management
    # ------------------------------------------------------------------

    def _insert_empty_row(self, row: int) -> None:
        self.table.insertRow(row)
        for column in range(self.table.columnCount()):
            item = QtWidgets.QTableWidgetItem("")
            if column in FLAG_COLUMNS:
                # Checkbox cell: checkable but not text-editable, pre-set to the default state
                item.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                item.setCheckState(QtCore.Qt.Checked if FLAG_COLUMNS[column] else QtCore.Qt.Unchecked)
            self.table.setItem(row, column, item)

    def _add_empty_rows(self, n=10):
        self._block_cell_signals = True
        for _ in range(n):
            self._insert_empty_row(self.table.rowCount())
        self._block_cell_signals = False

    def _row_is_empty(self, r) -> bool:
        """True if no text cell is filled; the checkbox columns always have a state and do not count."""
        return all(self._text(r, column) == "" for column in range(self.table.columnCount())
                   if column not in FLAG_COLUMNS)

    def _ensure_trailing_empty_row(self):
        rows = self.table.rowCount()
        if rows == 0 or not self._row_is_empty(rows - 1):
            self._block_cell_signals = True
            self._insert_empty_row(rows)
            self._block_cell_signals = False

    def _on_insert_above(self):
        """Insert a blank segment above the currently selected row."""
        row = self.table.currentRow() if self.table.selectedIndexes() else max(0, self.table.rowCount() - 1)
        self._block_cell_signals = True
        self._insert_empty_row(row)
        self._block_cell_signals = False
        self._refresh()

    def _on_delete_rows(self):
        """Delete all currently selected segments."""
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        self._block_cell_signals = True
        for r in rows:
            self.table.removeRow(r)
        self._block_cell_signals = False
        self._ensure_trailing_empty_row()
        self._refresh()

    def clear_data(self):
        self.table.setRowCount(0)
        self._add_empty_rows(10)
        self._refresh()

    # ------------------------------------------------------------------
    # Cell editing and validation
    # ------------------------------------------------------------------

    def _text(self, r, column) -> str:
        item = self.table.item(r, column)
        return item.text().strip() if item is not None else ""

    def _is_checked(self, r, column) -> bool:
        item = self.table.item(r, column)
        return item is not None and item.checkState() == QtCore.Qt.Checked

    def _set_checked(self, r, column, checked: bool) -> None:
        self.table.item(r, column).setCheckState(QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked)

    def _on_cell_changed(self, row, column):
        if self._block_cell_signals:
            return

        self._block_cell_signals = True
        text = self._text(row, column)
        if text and column not in FLAG_COLUMNS:
            try:
                self.table.item(row, column).setText("%1.6g" % float(text))
            except ValueError:
                pass  # flagged by _refresh
        # Continue the waveform seamlessly: pre-fill the next start voltage with this stop voltage
        if column == COL_STOP_V and text and row + 1 < self.table.rowCount() and self._text(row + 1, COL_START_V) == "":
            self.table.item(row + 1, COL_START_V).setText(self._text(row, COL_STOP_V))
        self._block_cell_signals = False

        self._ensure_trailing_empty_row()
        self._refresh()

    def _parse_row(self, r):
        """Parse one row into a segment dict.

        Returns (segment, problems): segment is None if the row holds no segment or a value cannot be parsed;
        problems is a list of (column, message) covering parse errors and the SegArb rules (except the seamless
        check, which needs the previous segment).
        """
        if all(self._text(r, column) == "" for column in range(self.table.columnCount())
               if column != COL_START_V and column not in FLAG_COLUMNS):
            return None, []  # empty, or only the pre-filled start voltage of a segment not started yet

        problems = []
        values = {}
        for key, column in (("start_v", COL_START_V), ("stop_v", COL_STOP_V), ("time", COL_TIME)):
            try:
                values[key] = float(self._text(r, column))
            except ValueError:
                problems.append((column, f"'{SEGMENT_HEADERS[column]}' must be a number."))
        for key, column in (("meas_start", COL_MEAS_START), ("meas_stop", COL_MEAS_STOP)):
            text = self._text(r, column)
            try:
                values[key] = float(text) if text else None
            except ValueError:
                problems.append((column, f"'{SEGMENT_HEADERS[column]}' must be a number or empty."))
        for key, column in (("measure", COL_MEASURE), ("ssr", COL_SSR), ("trigger", COL_TRIGGER)):
            values[key] = int(self._is_checked(r, column))

        if problems:
            return None, problems
        return values, segment_problems(values, None)

    def _refresh(self):
        """Highlight invalid cells and emit the plot data."""
        self._block_cell_signals = True
        previous_stop_v = None
        for r in range(self.table.rowCount()):
            segment, problems = self._parse_row(r)
            if segment is not None:
                problems += [p for p in segment_problems(segment, previous_stop_v) if p[0] == COL_START_V]
                previous_stop_v = segment["stop_v"]
            bad = {}
            for column, message in problems:
                bad.setdefault(column, message)
            for column in range(self.table.columnCount()):
                item = self.table.item(r, column)
                if item is None:
                    continue
                item.setBackground(self._COLOR_INVALID if column in bad else QtGui.QBrush())
                item.setToolTip(bad.get(column, ""))
        self._block_cell_signals = False
        self._emit_data_changed()

    def _emit_data_changed(self):
        xs, ys = self.get_pulse_data()
        self.data_changed.emit(xs, ys)

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def get_pulse_data(self):
        """Return (timestamps, voltages) of the segment corners for the plots.

        Rows that cannot be parsed are skipped; the segments are placed back to back starting at 0 s.
        """
        xs, ys = [], []
        t = 0.0
        for r in range(self.table.rowCount()):
            segment, _problems = self._parse_row(r)
            if segment is None:
                continue
            xs += [t, t + segment["time"]]
            ys += [segment["start_v"], segment["stop_v"]]
            t += segment["time"]
        return xs, ys

    def get_segments(self) -> list[dict]:
        """Return all segments for a run; raises ValueError naming the first invalid segment."""
        segments = []
        previous_stop_v = None
        for r in range(self.table.rowCount()):
            segment, problems = self._parse_row(r)
            if segment is not None:
                problems += [p for p in segment_problems(segment, previous_stop_v) if p[0] == COL_START_V]
            if problems:
                raise ValueError(f"Segment {r + 1}: {problems[0][1]}")
            if segment is None:
                continue  # empty row
            segments.append(segment)
            previous_stop_v = segment["stop_v"]
        return segments

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------

    def _on_save_csv(self):
        """Save all non-empty segment rows to a CSV file; the checkbox columns are written as 0/1."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.table, "Save Sequence to CSV", CSV_DEFAULT_DIR, "CSV files (*.csv);;All files (*.*)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(SEGMENT_HEADERS)
                for r in range(self.table.rowCount()):
                    if not self._row_is_empty(r):
                        writer.writerow([
                            str(int(self._is_checked(r, column))) if column in FLAG_COLUMNS else self._text(r, column)
                            for column in range(self.table.columnCount())
                        ])
            self.csv_path = path
        except Exception:
            error()

    def _on_load_csv(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.table, "Load Sequence from CSV", CSV_DEFAULT_DIR, "CSV files (*.csv);;All files (*.*)"
        )
        if not path:
            return
        self.load_csv(path)

    def load_csv(self, path) -> None:
        """Load segments from a CSV file (columns as in the table), replacing the table contents.

        The header and any line whose first cell is not a number are skipped. The checkbox columns are read as 0/1;
        missing trailing columns stay empty or keep their default state.
        """
        try:
            rows = []
            with open(path, newline="") as f:
                for row in csv.reader(f):
                    try:
                        float(row[0].strip())
                    except (IndexError, ValueError):
                        continue
                    rows.append([cell.strip() for cell in row[:len(SEGMENT_HEADERS)]])
            if not rows:
                return

            self.table.setRowCount(0)
            self._block_cell_signals = True
            for cells in rows:
                r = self.table.rowCount()
                self._insert_empty_row(r)
                for column, text in enumerate(cells):
                    if column in FLAG_COLUMNS:
                        if text in ("0", "1"):
                            self._set_checked(r, column, text == "1")
                    else:
                        self.table.item(r, column).setText(text)
            self._block_cell_signals = False
            self._ensure_trailing_empty_row()
            self._refresh()
            self.csv_path = path
        except Exception:
            error()


class KeithleySequenceTabWidget(SequenceTabWidget):
    """SequenceTabWidget that instantiates SegmentTableWidget instead of the point-based TableWidget."""

    def add_sequence_tab(self):
        seq_idx = self.sequence_count()
        table = SegmentTableWidget()
        table.data_changed.connect(self._on_any_data_changed)

        insert_pos = self.count() - 1 if self._plus_tab_added else self.count()

        self.blockSignals(True)
        self.insertTab(insert_pos, table, "Sequence %d" % (seq_idx + 1))
        self.setTabIcon(insert_pos, _color_icon(_sequence_color(seq_idx)))
        self.setCurrentIndex(insert_pos)
        self.blockSignals(False)

        self._hide_plus_close_button()


class KeithleyPulseBuilderWidget(Widget):
    """Pulse Builder using the SegArb segment tables."""

    def _create_layout(self):
        self.plot_widget = PlotWidget()
        self.sequence_tabs = KeithleySequenceTabWidget(self)
        self.waveform_table = WaveformTableWidget(self)

        # Top row: sequence plot (left) + segment tables (right); the tables are wide due to the eight columns
        top_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        top_splitter.addWidget(self.plot_widget.seq_canvas)
        top_splitter.addWidget(self.sequence_tabs)
        top_splitter.setSizes([400, 600])

        # Bottom row: waveform plot (left) + waveform table (right)
        bot_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        bot_splitter.addWidget(self.plot_widget.wf_canvas)
        bot_splitter.addWidget(self.waveform_table)
        bot_splitter.setSizes([400, 600])

        v_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        v_splitter.addWidget(top_splitter)
        v_splitter.addWidget(bot_splitter)

        grid = QtWidgets.QGridLayout()
        grid.addWidget(v_splitter, 0, 0)
        return grid


# ---------------------------------------------------------------------------
# CustomFunction script
# ---------------------------------------------------------------------------

class Main():

    """
    <h2>Pulse Builder &ndash; Keithley 4200A-SCS (SegArb via KXCI)</h2>

    <p>Define segmented arbitrary (SegArb) waveforms segment by segment, like in the SegArb dialog of Clarius, and
    play them on one PMU channel of a Keithley 4200A-SCS. The <b>voltage</b>, <b>current</b> and <b>time</b>
    samples of the measured segments are returned as three equally long traces.</p>

    <p>Communication uses <b>KXCI</b> (Keithley External Control Interface) over a raw TCP/IP socket. KXCI must be
    enabled on the 4200A-SCS and the instrument reachable at the configured address before the run is started.</p>

    <h3>Arguments</h3>
    <ul>
    <li><b>Port</b> &ndash; VISA SOCKET address of the KXCI server, e.g.
    <code>TCPIP0::192.168.100.4::8888::SOCKET</code>.</li>
    <li><b>PMU card</b> &ndash; number of the pulse card as named in Clarius/KCon (<code>1</code> for PMU1,
    <code>2</code> for PMU2, ...). This is not the physical slot: a PMU in slot 5 is still PMU1 if it is the
    first pulse card.</li>
    <li><b>Channel</b> &ndash; channel on that card, 1 or 2. KXCI numbers the channels across all cards (PMU1: 1,
    2; PMU2: 3, 4; ...); the script converts card and channel accordingly.</li>
    <li><b>Measure type</b> &ndash; applied to every segment with <i>Measure</i> checked: waveform (all samples) or spot
    mean (one value per segment), each discrete or averaged over the repetitions.</li>
    <li><b>Voltage source range in V</b> &ndash; <code>10</code> or <code>40</code>; must cover the largest absolute
    voltage.</li>
    <li><b>Current measure range in A</b> &ndash; fixed current range (SegArb requires a fixed range), e.g.
    <code>1e-2</code>, <code>1e-4</code> or <code>1e-6</code>.</li>
    <li><b>Load in Ohm</b> &ndash; DUT resistance for load-line correction (instrument default 1e6).</li>
    <li><b>Sample rate in Sa/s</b> &ndash; 1e3 to 200e6; the instrument lowers it automatically to stay within 65536
    points.</li>
    <li><b>Configure RPM</b> &ndash; enable when a 4225-RPM is connected to the channel.</li>
    </ul>

    <h3>Defining the waveform</h3>
    <ul>
    <li>Each <b>sequence tab</b> becomes one SegArb sequence; each row is one segment (row number = segment number,
    max. 128 segments per sequence).</li>
    <li><b>Start/Stop voltage in V</b> &ndash; the voltage ramps linearly from start to stop over the segment. The
    start voltage must equal the stop voltage of the previous segment (it is pre-filled when you enter a stop
    voltage).</li>
    <li><b>Segment time in s</b> &ndash; min. 20&nbsp;ns, in steps of 10&nbsp;ns.</li>
    <li><b>Measure</b> &ndash; check to measure this segment with the selected measure type. <b>Measure start/stop in
    s</b> optionally limit the measurement to a window relative to the segment start; empty means the whole
    segment.</li>
    <li><b>SSR</b> &ndash; checked closes the output relay, unchecked leaves the output floating (relay transitions
    need at least 25&nbsp;&micro;s). <b>Trigger out</b> &ndash; checked sets the trigger output high during the
    segment.</li>
    <li>Invalid cells are highlighted in red; hover over them for the reason.</li>
    <li>The <b>waveform table</b> sets the playback order and repetitions. Consecutive sequences &ndash; and repeated
    ones &ndash; must connect seamlessly: each sequence has to end at the start voltage of the next.</li>
    </ul>

    <h3>Notes</h3>
    <ul>
    <li>The sequences and the waveform table are stored in the setting via their CSV file paths. Save them to CSV
    before saving the setting.</li>
    <li>Spot-mean results are read from the VH/IH/TH fields (one value per measured segment).</li>
    <li>Configuration errors reported by the instrument (KXCI error buffer) stop the run with the instrument's
    message.</li>
    <li>The Stop button aborts a running test; the data captured so far is returned.</li>
    <li>The channel output is always switched off when the run finishes, including after an error.</li>
    </ul>
    """

    variables = ["Voltage", "Current", "Time"]
    units = ["V", "A", "s"]

    arguments = {
        "Port": "TCPIP0::192.168.100.4::8888::SOCKET",
        "PMU card": "1",
        "Channel": ["1", "2"],
        "Measure type": list(MEASURE_TYPES),
        "Voltage source range in V": ["10", "40"],
        "Current measure range in A": 1e-6,
        "Load in Ohm": 1e6,
        "Sample rate in Sa/s": 200e6,
        "Configure RPM": True,
    }

    def __init__(self):
        self.widget = None
        self.port = None
        self.pmu = None
        self.channel = 1

    # ------------------------------------------------------------------ #
    # widget
    # ------------------------------------------------------------------ #

    def renew_widget(self, widget=None):
        """Gets the widget from the module and returns the same or creates a new one.
        Called in the main GUI thread."""
        if widget is None:
            self.widget = KeithleyPulseBuilderWidget()
        else:
            self.widget = widget
        return self.widget

    def get_setting(self) -> list[str]:
        """Return the CSV save paths as list[str], if they exist."""
        return self.widget.get_setting()

    def set_setting(self, setting: list[str]) -> None:
        """Receive the CSV save paths and load them into the respective tables."""
        self.widget.set_setting(setting)

    # ------------------------------------------------------------------ #
    # port lifecycle
    # ------------------------------------------------------------------ #

    def _ensure_connected(self, port_id: str) -> None:
        """Open the KXCI socket once and wrap it; reused across main() calls within a run.

        The port is built manually - a TCPIPport plus a directly-opened pyvisa resource - instead of via
        pysweepme.get_port(), to work around a bug in the PortManager shipped with the SweepMe! executable. The
        null-character terminators and timeout are applied straight onto the pyvisa resource.
        """
        if self.port is not None:
            return

        port_properties = {
            "timeout": 10.0,
            "TCPIP_EOLwrite": "\x00",
            "TCPIP_EOLread": "\x00",
            "SOCKET_EOLwrite": "\x00",
            "SOCKET_EOLread": "\x00",
        }

        port = Ports.TCPIPport(port_id)
        port.properties = port_properties
        port.initialize_port_properties()

        resource_manager = Ports.get_resourcemanager()
        port.port = resource_manager.open_resource(port_id)
        port.port.timeout = int(port_properties["timeout"] * 1000)  # pyvisa timeout is in ms
        port.port.write_termination = "\x00"
        port.port.read_termination = "\x00"

        self.port = port
        self.pmu = KXCIPMU(self.port)

    def disconnect(self):
        """Close the KXCI socket at the end of the measurement."""
        if self.port is not None:
            self.port.close()
            self.port = None
            self.pmu = None

    # ------------------------------------------------------------------ #
    # measurement
    # ------------------------------------------------------------------ #

    def main(self, **kwargs):
        card = self._parse_card(kwargs["PMU card"])
        card_channel = int(kwargs["Channel"])
        # KXCI numbers the pulse channels across all cards: PMU1 -> 1, 2; PMU2 -> 3, 4; ...
        self.channel = channel = (card - 1) * 2 + card_channel
        measure_type = MEASURE_TYPES[kwargs["Measure type"]]
        voltage_range = int(kwargs["Voltage source range in V"])
        current_range = float(kwargs["Current measure range in A"])
        load = float(kwargs["Load in Ohm"])
        sample_rate = float(kwargs["Sample rate in Sa/s"])
        configure_rpm = bool(kwargs["Configure RPM"])

        sequences, sequence_list = self._read_waveform(measure_type)

        for seq_id, arrays in sequences.items():
            v_max = max(abs(v) for v in arrays["start_v"] + arrays["stop_v"])
            if v_max > voltage_range:
                raise ValueError(
                    f"Sequence {seq_id} reaches {v_max:g} V, which exceeds the {voltage_range} V source range."
                )
        is_measured = any(t != KXCIPMU.MEAS_NONE for arrays in sequences.values() for t in arrays["meas_types"])

        self._ensure_connected(kwargs["Port"])
        pmu = self.pmu

        # Clear the KXCI error buffer so any error read later belongs to this run. Ethernet KXCI acknowledges every
        # command with ACK on receipt; real errors (e.g. -951 from the final verification in EXECUTE) land only in
        # this buffer and on the instrument's console.
        pmu.clear_last_error()

        # :PMU:INIT must come first - it also clears the data buffer and deletes any previously defined sequences.
        pmu.init(KXCIPMU.MODE_SEGARB)
        if configure_rpm:
            pmu.configure_rpm(f"PMU{card}-{card_channel}", KXCIPMU.RPM_MODE_PMU)
        # SegArb requires fixed ranges for both voltage (source) and current (measure).
        pmu.set_source_range(channel, voltage_range)
        pmu.set_measure_range(channel, KXCIPMU.RANGE_FIXED, current_range)
        pmu.set_load(channel, load)

        setup_error = self._read_error()
        if setup_error:
            raise RuntimeError(f"PMU channel setup (RPM/ranges/load) failed - instrument reports: {setup_error}")

        for seq_id, arrays in sequences.items():
            pmu.set_segment_times(channel, seq_id, arrays["times"])
            pmu.set_start_voltages(channel, seq_id, arrays["start_v"])
            pmu.set_stop_voltages(channel, seq_id, arrays["stop_v"])
            pmu.set_measure_types(channel, seq_id, arrays["meas_types"])
            pmu.set_measure_starts(channel, seq_id, arrays["meas_starts"])
            pmu.set_measure_stops(channel, seq_id, arrays["meas_stops"])
            pmu.set_ssr(channel, seq_id, arrays["ssr"])
            pmu.set_triggers(channel, seq_id, arrays["trig"])

        pmu.set_sequence_list(channel, sequence_list)
        pmu.set_sample_rate(sample_rate)

        total_duration = sum(sum(sequences[seq_id]["times"]) * reps for seq_id, reps in sequence_list)

        try:
            pmu.set_output_state(channel, KXCIPMU.OUTPUT_ON)
            pmu.execute()
            self._wait_until_idle(timeout=2 * total_duration + START_TIMEOUT_S)
            if not is_measured:
                voltage, current, timestamp = [], [], []
            elif measure_type in SPOT_MEAN_TYPES:
                voltage = pmu.read_value(channel, "VH")
                current = pmu.read_value(channel, "IH")
                timestamp = pmu.read_value(channel, "TH")
            else:
                voltage, current, timestamp = pmu.read_voltage_current_time(channel)
        finally:
            # Always turn the output off, even if the run or readback fails.
            pmu.set_output_state(channel, KXCIPMU.OUTPUT_OFF)

        return np.array(voltage), np.array(current), np.array(timestamp)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def _read_waveform(self, measure_type: int):
        """Convert the Pulse Builder content into SegArb sequences and the sequence list.

        Returns:
            sequences: {seq_id: SegArb arrays of build_segments()} for every sequence used in the waveform.
            sequence_list: [(seq_id, repetitions), ...] in playback order.
        """
        sequence_list = self.widget.waveform_table.get_waveform_data()
        if not sequence_list:
            raise ValueError("The waveform table is empty. Add at least one row (sequence ID, repetitions).")

        sequences = {}
        for seq_id, _reps in sequence_list:
            if seq_id not in sequences:
                try:
                    segments = self.widget.sequence_tabs.widget(seq_id - 1).get_segments()
                except ValueError as e:
                    raise ValueError(f"Sequence {seq_id}, {e}") from None
                sequences[seq_id] = build_segments(seq_id, segments, measure_type)

        check_sequence_list(sequences, sequence_list)
        return sequences, sequence_list

    @staticmethod
    def _parse_card(text) -> int:
        """Parse the PMU card argument (entered as text, 1 for PMU1, ...) into a positive card number."""
        try:
            card = int(str(text).strip())
        except ValueError:
            raise ValueError(f"PMU card must be a positive integer (1 for PMU1, ...), got '{text}'.") from None
        if card < 1:
            raise ValueError(f"PMU card must be a positive integer (1 for PMU1, ...), got '{text}'.")
        return card

    def _read_error(self) -> str:
        """Return the instrument's last KXCI error message, or '' if there is none.

        Real errors carry a numeric code in parentheses, e.g. ``(-951)`` - responses without one (empty string,
        plain ACK) are treated as "no error". Read failures are swallowed so this stays safe to call inside
        error/polling paths.
        """
        try:
            message = self.pmu.get_last_error().strip()
        except Exception:
            return ""
        return message if "(-" in message else ""

    def _stop_requested(self) -> bool:
        """True when the user pressed Stop in SweepMe!.

        The CustomFunction module injects an ``is_run_stopped`` function onto this instance. Standalone it does not
        exist -> False.
        """
        check = getattr(self, "is_run_stopped", None)
        return bool(check()) if callable(check) else False

    def _wait_until_idle(self, timeout: float, poll_interval: float = 0.2) -> None:
        """Wait for the SegArb test to run to completion.

        ``:PMU:EXECUTE`` returns *before* the test is actually running, so a naive "poll until idle" mistakes the
        brief pre-start idle for completion. First wait until the instrument reports RUNNING (or has already
        buffered data, for a test shorter than one poll), then wait for the run to finish.
        """
        start = time.time()

        # Phase 1: wait for the test to actually begin.
        while self.pmu.get_test_status() != KXCIPMU.STATUS_RUNNING:
            if self.pmu.get_data_count(self.channel) > 0:
                return  # started and finished faster than we could poll; data is already buffered
            # If the final verification of EXECUTE failed (e.g. -951), the test never arms and the error is only in
            # the KXCI error buffer.
            message = self._read_error()
            if message:
                self.pmu.abort()
                raise RuntimeError(f"SegArb test failed to arm - instrument reports: {message}")
            if self._stop_requested():
                self.pmu.abort()
                return
            if time.time() - start > START_TIMEOUT_S:
                self.pmu.abort()
                raise RuntimeError(
                    f"SegArb test did not start within {START_TIMEOUT_S:g} s (no RUNNING status, no data, "
                    f"no KXCI error)."
                )
            time.sleep(0.02)

        # Phase 2: wait for the run to finish.
        while self.pmu.get_test_status() == KXCIPMU.STATUS_RUNNING:
            if self._stop_requested():
                self.pmu.abort()
                return  # return the data captured so far
            if time.time() - start > timeout:
                self.pmu.abort()
                raise TimeoutError(f"SegArb test exceeded the timeout of {timeout:g} s.")
            time.sleep(poll_interval)


if __name__ == "__main__":

    # Standalone GUI preview (no instrument needed). Run from this folder: python main.py
    app = QtWidgets.QApplication([])
    script = Main()
    script.renew_widget().show()
    app.exec()
