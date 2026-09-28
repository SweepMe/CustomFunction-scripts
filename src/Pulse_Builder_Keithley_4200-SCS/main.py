# author: Franz Hempel
# created on: 2026-06-19
# company/institute: SweepMe!
"""CustomFunction script: Pulse Builder for the Keithley 4200A-SCS PMU (SegArb via KXCI).

The pulse sequences and their playback order are drawn in the shared Pulse Builder GUI (libs/pulse_builder.py).
Each sequence tab becomes one SegArb sequence on the instrument, each pair of consecutive points one segment. The
measure type, start and stop of a segment are set in the row of its first point. The waveform table becomes the
SegArb sequence list. The captured voltage, current and timestamp are returned as three arrays.
"""
from __future__ import annotations

import csv
import time

import numpy as np
from PySide6 import QtCore, QtWidgets

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
    TableWidget,
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

# Measure types of :PMU:SARB:SEQ:MEAS:TYPE as shown in the sequence table
MEASURE_TYPES = {
    "None": KXCIPMU.MEAS_NONE,
    "Waveform discrete": KXCIPMU.MEAS_WAVEFORM_DISCRETE,
    "Waveform average": KXCIPMU.MEAS_WAVEFORM_AVERAGE,
    "Spot mean discrete": KXCIPMU.MEAS_SPOT_MEAN_DISCRETE,
    "Spot mean average": KXCIPMU.MEAS_SPOT_MEAN_AVERAGE,
}
DEFAULT_MEASURE_TYPE = "Waveform discrete"
WAVEFORM_TYPES = {KXCIPMU.MEAS_WAVEFORM_DISCRETE, KXCIPMU.MEAS_WAVEFORM_AVERAGE}
SPOT_MEAN_TYPES = {KXCIPMU.MEAS_SPOT_MEAN_DISCRETE, KXCIPMU.MEAS_SPOT_MEAN_AVERAGE}

# Sequence table columns
COL_TIME, COL_VOLTAGE, COL_MEAS_TYPE, COL_MEAS_START, COL_MEAS_STOP = range(5)
TABLE_HEADERS = ["Time in s", "Voltage in V", "Measure type", "Measure start in s", "Measure stop in s"]
TABLE_TOOLTIPS = [
    "Absolute time of the point within the sequence; the first point must be at 0 s",
    "Voltage of the point",
    "Measure type of the segment starting at this point (ignored on the last point)",
    "Measure start relative to the segment start; empty = 0 s",
    "Measure stop relative to the segment start; empty = end of the segment",
]


# ---------------------------------------------------------------------------
# Waveform conversion: sequence table rows -> SegArb segments
# ---------------------------------------------------------------------------

def build_segments(sequence_number: int, rows: list[tuple]) -> dict:
    """Convert the rows of one sequence tab into the SegArb segment arrays.

    rows: [(time, voltage, measure_type, measure_start, measure_stop), ...] with absolute times within the sequence
    (first point at 0 s). Consecutive points give one segment each: its duration is the time difference, its
    start/stop voltages are the two point voltages - which guarantees the seamless transitions SegArb requires. The
    measure settings of a segment are taken from its first point; measure_start/stop may be None (= 0 s / segment end).

    Returns:
        dict with the lists "times", "start_v", "stop_v", "meas_types", "meas_starts", "meas_stops".
    """
    label = f"Sequence {sequence_number}"
    if len(rows) < 2:
        raise ValueError(f"{label}: at least two points (one segment) are required.")
    if abs(rows[0][0]) > 1e-15:
        raise ValueError(f"{label}: the first point must be at 0 s (got {rows[0][0]:g} s).")
    if len(rows) - 1 > MAX_SEGMENTS_PER_SEQUENCE:
        raise ValueError(
            f"{label}: {len(rows) - 1} segments exceed the maximum of {MAX_SEGMENTS_PER_SEQUENCE} per sequence."
        )

    segments = {key: [] for key in ("times", "start_v", "stop_v", "meas_types", "meas_starts", "meas_stops")}
    for i, (first, second) in enumerate(zip(rows[:-1], rows[1:])):
        where = f"{label}, segment {i + 1} (points {i + 1}->{i + 2})"
        t_start, v_start, meas_type, meas_start, meas_stop = first
        t_stop, v_stop = second[0], second[1]

        duration = t_stop - t_start
        steps = round(duration / SEGMENT_TIME_RESOLUTION)
        if steps * SEGMENT_TIME_RESOLUTION < SEGMENT_TIME_MIN - 1e-15:
            raise ValueError(
                f"{where}: segment time {duration:g} s is shorter than the minimum of {SEGMENT_TIME_MIN:g} s. "
                f"Times must increase; model jumps with a finite rise/fall time."
            )
        if abs(duration / SEGMENT_TIME_RESOLUTION - steps) > 1e-3:
            raise ValueError(f"{where}: segment time {duration:g} s is not a multiple of {SEGMENT_TIME_RESOLUTION:g} s.")
        duration = round(steps * SEGMENT_TIME_RESOLUTION, 10)

        if meas_type == KXCIPMU.MEAS_NONE:
            meas_start, meas_stop = 0.0, 0.0
        else:
            meas_start = 0.0 if meas_start is None else meas_start
            meas_stop = duration if meas_stop is None else meas_stop
            if not 0.0 <= meas_start < meas_stop <= duration + 1e-15:
                raise ValueError(
                    f"{where}: measure window {meas_start:g} s to {meas_stop:g} s must satisfy "
                    f"0 <= start < stop <= segment time ({duration:g} s)."
                )

        segments["times"].append(duration)
        segments["start_v"].append(v_start)
        segments["stop_v"].append(v_stop)
        segments["meas_types"].append(meas_type)
        segments["meas_starts"].append(meas_start)
        segments["meas_stops"].append(meas_stop)

    return segments


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
# GUI: sequence table with measure columns
# ---------------------------------------------------------------------------

class KeithleyTableWidget(TableWidget):
    """Sequence table with the per-segment measure settings as additional columns.

    Columns: Time in s | Voltage in V | Measure type | Measure start in s | Measure stop in s. Only time and voltage
    define the plotted points; the measure columns of a row apply to the segment starting at that point.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.table.setColumnCount(len(TABLE_HEADERS))
        self.table.setHorizontalHeaderLabels(TABLE_HEADERS)
        for column, tooltip in enumerate(TABLE_TOOLTIPS):
            self.table.horizontalHeaderItem(column).setToolTip(tooltip)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self._fill_measure_cells()

    # ------------------------------------------------------------------
    # Keep the measure cells present in every row
    # ------------------------------------------------------------------

    @staticmethod
    def _make_type_combo(selected: str = DEFAULT_MEASURE_TYPE) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        combo.addItems(list(MEASURE_TYPES))
        combo.setCurrentText(selected if selected in MEASURE_TYPES else DEFAULT_MEASURE_TYPE)
        return combo

    def _fill_measure_cells(self):
        """Add the measure type combo and the start/stop items to all rows that miss them."""
        if self.table.columnCount() < len(TABLE_HEADERS):
            return  # called by the base __init__ before the columns are added
        blocked = self._block_cell_signals
        self._block_cell_signals = True
        for r in range(self.table.rowCount()):
            if self.table.cellWidget(r, COL_MEAS_TYPE) is None:
                self.table.setCellWidget(r, COL_MEAS_TYPE, self._make_type_combo())
            for column in (COL_MEAS_START, COL_MEAS_STOP):
                if self.table.item(r, column) is None:
                    self.table.setItem(r, column, QtWidgets.QTableWidgetItem(""))
        self._block_cell_signals = blocked

    def _add_empty_rows(self, n=10):
        super()._add_empty_rows(n)
        self._fill_measure_cells()

    def _ensure_trailing_empty_row(self):
        super()._ensure_trailing_empty_row()
        self._fill_measure_cells()

    def _on_insert_above(self):
        super()._on_insert_above()
        self._fill_measure_cells()

    def add_row(self, timestamp, voltage):
        super().add_row(timestamp, voltage)
        self._fill_measure_cells()

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def get_rows(self) -> list[tuple]:
        """Return [(time, voltage, measure_type, measure_start, measure_stop), ...] for all valid points.

        measure_type is the KXCI enum; measure_start/stop are None when left empty. Rows without a valid time and
        voltage are skipped (like in get_pulse_data), an invalid measure start/stop raises a ValueError.
        """
        rows = []
        for r in range(self.table.rowCount()):
            try:
                t = float(self.table.item(r, COL_TIME).text().strip())
                v = float(self.table.item(r, COL_VOLTAGE).text().strip())
            except Exception:
                continue
            combo = self.table.cellWidget(r, COL_MEAS_TYPE)
            meas_type = MEASURE_TYPES[combo.currentText()] if combo else MEASURE_TYPES[DEFAULT_MEASURE_TYPE]
            window = []
            for column in (COL_MEAS_START, COL_MEAS_STOP):
                item = self.table.item(r, column)
                text = item.text().strip() if item else ""
                try:
                    window.append(float(text) if text else None)
                except ValueError:
                    raise ValueError(f"Row {r + 1}: '{TABLE_HEADERS[column]}' must be a number, got '{text}'.")
            rows.append((t, v, meas_type, *window))
        return rows

    # ------------------------------------------------------------------
    # CSV with all five columns
    # ------------------------------------------------------------------

    def _on_save_csv(self):
        """Save all valid points including their measure settings to a CSV file."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.table, "Save Sequence to CSV", CSV_DEFAULT_DIR, "CSV files (*.csv);;All files (*.*)"
        )
        if not path:
            return
        try:
            type_names = {value: name for name, value in MEASURE_TYPES.items()}
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(TABLE_HEADERS)
                for t, v, meas_type, meas_start, meas_stop in self.get_rows():
                    writer.writerow([
                        "%1.6g" % t,
                        "%1.6g" % v,
                        type_names[meas_type],
                        "" if meas_start is None else "%1.6g" % meas_start,
                        "" if meas_stop is None else "%1.6g" % meas_stop,
                    ])
            self.csv_path = path
        except Exception:
            error()

    def load_csv(self, path) -> None:
        """Load a sequence CSV, replacing the table contents.

        Accepts the five-column format written by _on_save_csv and plain two-column (time, voltage) files of the
        base Pulse Builder; missing measure settings get the defaults. Header and non-numeric lines are skipped.
        """
        try:
            rows = []
            with open(path, newline="") as f:
                for row in csv.reader(f):
                    if len(row) < 2:
                        continue
                    try:
                        t, v = float(row[0].strip()), float(row[1].strip())
                    except ValueError:
                        continue  # skip header or non-numeric lines
                    extra = [cell.strip() for cell in row[2:5]] + [""] * (3 - len(row[2:5]))
                    rows.append((t, v, *extra))
            if not rows:
                return

            self.table.setRowCount(0)
            self._block_cell_signals = True
            for t, v, meas_type, meas_start, meas_stop in rows:
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, COL_TIME, QtWidgets.QTableWidgetItem("%1.6g" % t))
                self.table.setItem(r, COL_VOLTAGE, QtWidgets.QTableWidgetItem("%1.6g" % v))
                self.table.setCellWidget(r, COL_MEAS_TYPE, self._make_type_combo(meas_type or DEFAULT_MEASURE_TYPE))
                self.table.setItem(r, COL_MEAS_START, QtWidgets.QTableWidgetItem(meas_start))
                self.table.setItem(r, COL_MEAS_STOP, QtWidgets.QTableWidgetItem(meas_stop))
            self._block_cell_signals = False
            self._ensure_trailing_empty_row()
            self._emit_data_changed()
            self.csv_path = path
        except Exception:
            error()


class KeithleySequenceTabWidget(SequenceTabWidget):
    """SequenceTabWidget that instantiates KeithleyTableWidget instead of TableWidget."""

    def add_sequence_tab(self):
        seq_idx = self.sequence_count()
        table = KeithleyTableWidget()
        table.data_changed.connect(self._on_any_data_changed)

        insert_pos = self.count() - 1 if self._plus_tab_added else self.count()

        self.blockSignals(True)
        self.insertTab(insert_pos, table, "Sequence %d" % (seq_idx + 1))
        self.setTabIcon(insert_pos, _color_icon(_sequence_color(seq_idx)))
        self.setCurrentIndex(insert_pos)
        self.blockSignals(False)

        self._hide_plus_close_button()


class KeithleyPulseBuilderWidget(Widget):
    """Pulse Builder using the sequence tables with measure columns."""

    def _create_layout(self):
        self.plot_widget = PlotWidget()
        self.sequence_tabs = KeithleySequenceTabWidget(self)
        self.waveform_table = WaveformTableWidget(self)

        # Top row: sequence plot (left) + sequence tabs (right); the tables are wider due to the measure columns
        top_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        top_splitter.addWidget(self.plot_widget.seq_canvas)
        top_splitter.addWidget(self.sequence_tabs)
        top_splitter.setSizes([400, 500])

        # Bottom row: waveform plot (left) + waveform table (right)
        bot_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        bot_splitter.addWidget(self.plot_widget.wf_canvas)
        bot_splitter.addWidget(self.waveform_table)
        bot_splitter.setSizes([400, 500])

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

    <p>Draw pulse sequences in the Pulse Builder and play them on one PMU channel of a Keithley 4200A-SCS as a
    <b>segmented arbitrary (SegArb) waveform</b>. The <b>voltage</b>, <b>current</b> and <b>time</b> samples of the
    measured segments are returned as three equally long traces.</p>

    <p>Communication uses <b>KXCI</b> (Keithley External Control Interface) over a raw TCP/IP socket. KXCI must be
    enabled on the 4200A-SCS and the instrument reachable at the configured address before the run is started.</p>

    <h3>Arguments</h3>
    <ul>
    <li><b>Port</b> &ndash; VISA SOCKET address of the KXCI server, e.g.
    <code>TCPIP0::192.168.100.4::8888::SOCKET</code>.</li>
    <li><b>Channel</b> &ndash; PMU channel to pulse and measure (card 1: 1, 2; card 2: 3, 4; ...). Entered as
    text, so any channel number the mainframe offers can be used.</li>
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
    <li>Each <b>sequence tab</b> becomes one SegArb sequence. Its points are absolute times within the sequence and
    must start at 0&nbsp;s. Each pair of consecutive points is one segment (min. 20&nbsp;ns, 10&nbsp;ns
    resolution, max. 128 segments per sequence). Jumps need a finite rise/fall time.</li>
    <li><b>Measure type</b>, <b>Measure start</b> and <b>Measure stop</b> of a row apply to the segment starting at
    that point (they are ignored on the last point). Start and stop are relative to the segment start; empty means
    0&nbsp;s and the segment end, i.e. the whole segment. Waveform and spot-mean types cannot be mixed in one
    waveform.</li>
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
        "Channel": "1",
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
        self.channel = channel = self._parse_channel(kwargs["Channel"])
        voltage_range = int(kwargs["Voltage source range in V"])
        current_range = float(kwargs["Current measure range in A"])
        load = float(kwargs["Load in Ohm"])
        sample_rate = float(kwargs["Sample rate in Sa/s"])
        configure_rpm = bool(kwargs["Configure RPM"])

        sequences, sequence_list = self._read_waveform()

        for seq_id, segments in sequences.items():
            v_max = max(abs(v) for v in segments["start_v"] + segments["stop_v"])
            if v_max > voltage_range:
                raise ValueError(
                    f"Sequence {seq_id} reaches {v_max:g} V, which exceeds the {voltage_range} V source range."
                )

        measure_types = {t for segments in sequences.values() for t in segments["meas_types"]} - {KXCIPMU.MEAS_NONE}
        if measure_types & WAVEFORM_TYPES and measure_types & SPOT_MEAN_TYPES:
            raise ValueError("Waveform and spot-mean measure types cannot be mixed in one waveform.")

        self._ensure_connected(kwargs["Port"])
        pmu = self.pmu

        # Clear the KXCI error buffer so any error read later belongs to this run. Ethernet KXCI acknowledges every
        # command with ACK on receipt; real errors (e.g. -951 from the final verification in EXECUTE) land only in
        # this buffer and on the instrument's console.
        pmu.clear_last_error()

        # :PMU:INIT must come first - it also clears the data buffer and deletes any previously defined sequences.
        pmu.init(KXCIPMU.MODE_SEGARB)
        if configure_rpm:
            pmu.configure_rpm(self._rpm_hrid(channel), KXCIPMU.RPM_MODE_PMU)
        # SegArb requires fixed ranges for both voltage (source) and current (measure).
        pmu.set_source_range(channel, voltage_range)
        pmu.set_measure_range(channel, KXCIPMU.RANGE_FIXED, current_range)
        pmu.set_load(channel, load)

        setup_error = self._read_error()
        if setup_error:
            raise RuntimeError(f"PMU channel setup (RPM/ranges/load) failed - instrument reports: {setup_error}")

        for seq_id, segments in sequences.items():
            pmu.set_segment_times(channel, seq_id, segments["times"])
            pmu.set_start_voltages(channel, seq_id, segments["start_v"])
            pmu.set_stop_voltages(channel, seq_id, segments["stop_v"])
            pmu.set_measure_types(channel, seq_id, segments["meas_types"])
            pmu.set_measure_starts(channel, seq_id, segments["meas_starts"])
            pmu.set_measure_stops(channel, seq_id, segments["meas_stops"])

        pmu.set_sequence_list(channel, sequence_list)
        pmu.set_sample_rate(sample_rate)

        total_duration = sum(sum(sequences[seq_id]["times"]) * reps for seq_id, reps in sequence_list)

        try:
            pmu.set_output_state(channel, KXCIPMU.OUTPUT_ON)
            pmu.execute()
            self._wait_until_idle(timeout=2 * total_duration + START_TIMEOUT_S)
            if not measure_types:
                voltage, current, timestamp = [], [], []
            elif measure_types & SPOT_MEAN_TYPES:
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

    def _read_waveform(self):
        """Convert the Pulse Builder content into SegArb sequences and the sequence list.

        Returns:
            sequences: {seq_id: segment arrays of build_segments()} for every sequence used in the waveform.
            sequence_list: [(seq_id, repetitions), ...] in playback order.
        """
        sequence_list = self.widget.waveform_table.get_waveform_data()
        if not sequence_list:
            raise ValueError("The waveform table is empty. Add at least one row (sequence ID, repetitions).")

        sequences = {}
        for seq_id, _reps in sequence_list:
            if seq_id not in sequences:
                try:
                    rows = self.widget.sequence_tabs.widget(seq_id - 1).get_rows()
                except ValueError as e:
                    raise ValueError(f"Sequence {seq_id}: {e}") from None
                sequences[seq_id] = build_segments(seq_id, rows)

        check_sequence_list(sequences, sequence_list)
        return sequences, sequence_list

    @staticmethod
    def _parse_channel(text) -> int:
        """Parse the Channel argument (entered as text) into a positive channel number."""
        try:
            channel = int(str(text).strip())
        except ValueError:
            raise ValueError(f"Channel must be a positive integer, got '{text}'.") from None
        if channel < 1:
            raise ValueError(f"Channel must be a positive integer, got '{text}'.")
        return channel

    @staticmethod
    def _rpm_hrid(channel: int) -> str:
        """Map a global pulse channel to its RPM id ``PMU<card>-<channel-on-card>``.

        Each PMU card carries two channels, so channels 1,2 -> PMU1-1,PMU1-2; 3,4 -> PMU2-1, ...
        """
        card = (channel - 1) // 2 + 1
        channel_on_card = (channel - 1) % 2 + 1
        return f"PMU{card}-{channel_on_card}"

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
