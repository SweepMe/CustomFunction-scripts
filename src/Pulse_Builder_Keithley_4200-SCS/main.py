# author: Franz Hempel
# created on: 2026-06-19
# company/institute: SweepMe!
"""CustomFunction script: Pulse Builder for the Keithley 4200A-SCS PMU (SegArb via KXCI).

The pulse sequences and their playback order are drawn in the shared Pulse Builder GUI (libs/pulse_builder.py).
Each sequence tab becomes one SegArb sequence on the instrument, each pair of consecutive (time, voltage) points
one segment. The waveform table becomes the SegArb sequence list. Every segment is measured (waveform-discrete)
over its full duration; the captured voltage, current and timestamp are returned as three arrays.
"""
from __future__ import annotations

import time

import numpy as np
from PySide6 import QtWidgets

from pysweepme import FolderManager, Ports
FolderManager.addFolderToPATH()  # makes libs/kxci_pmu.py and libs/pulse_builder.py importable

import importlib
import kxci_pmu

importlib.reload(kxci_pmu)

from kxci_pmu import KXCIPMU
from pulse_builder import Widget


# SegArb timing limits (KXCI manual, :PMU:SARB:SEQ:TIME)
SEGMENT_TIME_RESOLUTION = 10e-9
SEGMENT_TIME_MIN = 20e-9
MAX_SEGMENTS_PER_SEQUENCE = 128  # one :PMU:SARB:SEQ:* call; the ...:ADD variants are not wrapped yet

START_TIMEOUT_S = 10.0  # max. time between :PMU:EXECUTE and the test reporting RUNNING

CURRENT_RANGES = ["1e-7", "1e-6", "1e-5", "1e-4", "1e-3", "1e-2", "2e-1", "8e-1"]
VOLTAGE_RANGES = ["10", "40"]


# ---------------------------------------------------------------------------
# Waveform conversion: Pulse Builder points -> SegArb segments
# ---------------------------------------------------------------------------

def build_segments(sequence_number: int, xs: list[float], ys: list[float]):
    """Convert the (time, voltage) points of one sequence tab into SegArb segment arrays.

    The points are absolute times within the sequence (first point at 0 s). Consecutive points give one segment each:
    its duration is the time difference, its start/stop voltages are the two point voltages. This guarantees the
    seamless transitions SegArb requires within a sequence.

    Returns:
        (times, start_voltages, stop_voltages) - three lists of equal length.
    """
    label = f"Sequence {sequence_number}"
    if len(xs) < 2:
        raise ValueError(f"{label}: at least two points (one segment) are required.")
    if abs(xs[0]) > 1e-15:
        raise ValueError(f"{label}: the first point must be at 0 s (got {xs[0]:g} s).")
    if len(xs) - 1 > MAX_SEGMENTS_PER_SEQUENCE:
        raise ValueError(
            f"{label}: {len(xs) - 1} segments exceed the maximum of {MAX_SEGMENTS_PER_SEQUENCE} per sequence."
        )

    times = []
    for i, (t_start, t_stop) in enumerate(zip(xs[:-1], xs[1:])):
        duration = t_stop - t_start
        steps = round(duration / SEGMENT_TIME_RESOLUTION)
        if steps * SEGMENT_TIME_RESOLUTION < SEGMENT_TIME_MIN - 1e-15:
            raise ValueError(
                f"{label}, points {i + 1}->{i + 2}: segment time {duration:g} s is shorter than the minimum of "
                f"{SEGMENT_TIME_MIN:g} s. Times must increase; model jumps with a finite rise/fall time."
            )
        if abs(duration / SEGMENT_TIME_RESOLUTION - steps) > 1e-3:
            raise ValueError(
                f"{label}, points {i + 1}->{i + 2}: segment time {duration:g} s is not a multiple of "
                f"{SEGMENT_TIME_RESOLUTION:g} s."
            )
        times.append(round(steps * SEGMENT_TIME_RESOLUTION, 10))

    return times, list(ys[:-1]), list(ys[1:])


def check_sequence_list(sequences: dict, sequence_list: list[tuple[int, int]]) -> None:
    """Check that the playback order yields a seamless waveform.

    SegArb requires the stop voltage of each sequence to equal the start voltage of the next one - also between
    two repetitions of the same sequence.
    """
    previous = None
    for seq_id, reps in sequence_list:
        _times, start_v, stop_v = sequences[seq_id]
        if reps > 1 and stop_v[-1] != start_v[0]:
            raise ValueError(
                f"Sequence {seq_id} is repeated {reps} times, but ends at {stop_v[-1]:g} V and starts at "
                f"{start_v[0]:g} V. Repeated sequences must end at their start voltage."
            )
        if previous is not None and sequences[previous][2][-1] != start_v[0]:
            raise ValueError(
                f"Sequence {previous} ends at {sequences[previous][2][-1]:g} V, but the following sequence {seq_id} "
                f"starts at {start_v[0]:g} V. Consecutive sequences must connect seamlessly."
            )
        previous = seq_id


# ---------------------------------------------------------------------------
# GUI: instrument settings + Pulse Builder
# ---------------------------------------------------------------------------

class InstrumentSettingsWidget(QtWidgets.QGroupBox):
    """Connection, channel and range settings of the 4200A-SCS PMU."""

    def __init__(self, parent=None):
        super().__init__("Keithley 4200A-SCS PMU (KXCI)", parent)

        self.port_edit = QtWidgets.QLineEdit("TCPIP0::192.168.100.4::8888::SOCKET")
        self.port_edit.setToolTip("VISA SOCKET address of the KXCI server")

        self.channel_spin = QtWidgets.QSpinBox()
        self.channel_spin.setRange(1, 8)
        self.channel_spin.setToolTip("PMU channel to pulse and measure (card 1: channels 1, 2; card 2: 3, 4; ...)")

        self.rpm_check = QtWidgets.QCheckBox("Configure RPM")
        self.rpm_check.setChecked(True)
        self.rpm_check.setToolTip("Enable when a 4225-RPM is connected to the channel")

        self.voltage_range_combo = QtWidgets.QComboBox()
        self.voltage_range_combo.addItems(VOLTAGE_RANGES)
        self.voltage_range_combo.setToolTip("Fixed voltage source range; must cover the largest absolute voltage")

        self.current_range_combo = QtWidgets.QComboBox()
        self.current_range_combo.setEditable(True)
        self.current_range_combo.addItems(CURRENT_RANGES)
        self.current_range_combo.setCurrentText("1e-6")
        self.current_range_combo.setToolTip("Fixed current measure range in A (SegArb requires a fixed range)")

        self.load_edit = QtWidgets.QLineEdit("1e6")
        self.load_edit.setToolTip("DUT load resistance used for load-line correction, 1 to 1e7 Ohm")

        self.sample_rate_edit = QtWidgets.QLineEdit("200e6")
        self.sample_rate_edit.setToolTip(
            "A/D sample rate, 1e3 to 200e6 Sa/s. The instrument lowers it to keep within 65536 points."
        )

        grid = QtWidgets.QGridLayout(self)
        grid.addWidget(QtWidgets.QLabel("Port"), 0, 0)
        grid.addWidget(self.port_edit, 0, 1, 1, 3)
        grid.addWidget(QtWidgets.QLabel("Channel"), 0, 4)
        grid.addWidget(self.channel_spin, 0, 5)
        grid.addWidget(self.rpm_check, 0, 6, 1, 2)

        grid.addWidget(QtWidgets.QLabel("Voltage range in V"), 1, 0)
        grid.addWidget(self.voltage_range_combo, 1, 1)
        grid.addWidget(QtWidgets.QLabel("Current range in A"), 1, 2)
        grid.addWidget(self.current_range_combo, 1, 3)
        grid.addWidget(QtWidgets.QLabel("Load in Ohm"), 1, 4)
        grid.addWidget(self.load_edit, 1, 5)
        grid.addWidget(QtWidgets.QLabel("Sample rate in Sa/s"), 1, 6)
        grid.addWidget(self.sample_rate_edit, 1, 7)

    def get_parameters(self) -> dict:
        """Return the validated settings as plain Python values."""

        def to_float(text: str, name: str) -> float:
            try:
                return float(text.strip())
            except ValueError:
                raise ValueError(f"'{name}' must be a number, got '{text}'.") from None

        port = self.port_edit.text().strip()
        if not port:
            raise ValueError("Please enter the KXCI port, e.g. TCPIP0::192.168.100.4::8888::SOCKET.")

        return {
            "port": port,
            "channel": self.channel_spin.value(),
            "configure_rpm": self.rpm_check.isChecked(),
            "voltage_range": int(self.voltage_range_combo.currentText()),
            "current_range": to_float(self.current_range_combo.currentText(), "Current range in A"),
            "load": to_float(self.load_edit.text(), "Load in Ohm"),
            "sample_rate": to_float(self.sample_rate_edit.text(), "Sample rate in Sa/s"),
        }

    def get_setting(self) -> list[str]:
        """Serialize the settings as "instrument_<key>: <value>" lines for the SweepMe! setting file."""
        return [
            f"instrument_port: {self.port_edit.text()}",
            f"instrument_channel: {self.channel_spin.value()}",
            f"instrument_configure_rpm: {self.rpm_check.isChecked()}",
            f"instrument_voltage_range: {self.voltage_range_combo.currentText()}",
            f"instrument_current_range: {self.current_range_combo.currentText()}",
            f"instrument_load: {self.load_edit.text()}",
            f"instrument_sample_rate: {self.sample_rate_edit.text()}",
        ]

    def set_setting(self, setting: list[str]) -> None:
        """Restore the settings written by get_setting(); unknown or broken lines are skipped."""
        for line in setting:
            if not line.startswith("instrument_") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key, value = key[len("instrument_"):], value.strip()
            try:
                if key == "port":
                    self.port_edit.setText(value)
                elif key == "channel":
                    self.channel_spin.setValue(int(value))
                elif key == "configure_rpm":
                    self.rpm_check.setChecked(value == "True")
                elif key == "voltage_range" and value in VOLTAGE_RANGES:
                    self.voltage_range_combo.setCurrentText(value)
                elif key == "current_range":
                    self.current_range_combo.setCurrentText(value)
                elif key == "load":
                    self.load_edit.setText(value)
                elif key == "sample_rate":
                    self.sample_rate_edit.setText(value)
            except ValueError:
                continue


class KeithleyPulseBuilderWidget(Widget):
    """Pulse Builder with the 4200A-SCS instrument settings on top."""

    def _create_layout(self):
        self.instrument_settings = InstrumentSettingsWidget()

        grid = super()._create_layout()
        splitter = grid.itemAtPosition(0, 0).widget()
        grid.removeWidget(splitter)
        grid.addWidget(self.instrument_settings, 0, 0)
        grid.addWidget(splitter, 1, 0)
        grid.setRowStretch(1, 1)
        return grid

    def get_setting(self) -> list[str]:
        return super().get_setting() + self.instrument_settings.get_setting()

    def set_setting(self, setting: list[str]) -> None:
        super().set_setting(setting)
        self.instrument_settings.set_setting(setting)


# ---------------------------------------------------------------------------
# CustomFunction script
# ---------------------------------------------------------------------------

class Main():

    """
    <h2>Pulse Builder &ndash; Keithley 4200A-SCS (SegArb via KXCI)</h2>

    <p>Draw pulse sequences in the Pulse Builder and play them on one PMU channel of a Keithley 4200A-SCS as a
    <b>segmented arbitrary (SegArb) waveform</b>. Every segment is captured as a waveform, and the <b>voltage</b>,
    <b>current</b> and <b>time</b> samples are returned as three equally long traces.</p>

    <p>Communication uses <b>KXCI</b> (Keithley External Control Interface) over a raw TCP/IP socket. KXCI must be
    enabled on the 4200A-SCS and the instrument reachable at the configured address before the run is started.</p>

    <h3>Instrument settings</h3>
    <ul>
    <li><b>Port</b> &ndash; VISA SOCKET address of the KXCI server, e.g.
    <code>TCPIP0::192.168.100.4::8888::SOCKET</code>.</li>
    <li><b>Channel</b> &ndash; PMU channel to pulse and measure.</li>
    <li><b>Configure RPM</b> &ndash; enable when a 4225-RPM is connected to the channel.</li>
    <li><b>Voltage range in V</b> &ndash; <code>10</code> or <code>40</code>; must cover the largest absolute
    voltage.</li>
    <li><b>Current range in A</b> &ndash; fixed current measure range (SegArb requires a fixed range).</li>
    <li><b>Load in Ohm</b> &ndash; DUT resistance for load-line correction (instrument default 1e6).</li>
    <li><b>Sample rate in Sa/s</b> &ndash; the instrument lowers it automatically to stay within 65536 points.</li>
    </ul>

    <h3>Defining the waveform</h3>
    <ul>
    <li>Each <b>sequence tab</b> becomes one SegArb sequence. Its points are absolute times within the sequence and
    must start at 0&nbsp;s. Each pair of consecutive points is one segment (min. 20&nbsp;ns, 10&nbsp;ns
    resolution, max. 128 segments per sequence). Jumps need a finite rise/fall time.</li>
    <li>The <b>waveform table</b> sets the playback order and repetitions. Consecutive sequences &ndash; and repeated
    ones &ndash; must connect seamlessly: each sequence has to end at the start voltage of the next.</li>
    <li>Every segment is measured over its full duration.</li>
    </ul>

    <h3>Notes</h3>
    <ul>
    <li>The sequences and the waveform table are stored in the setting via their CSV file paths. Save them to CSV
    before saving the setting.</li>
    <li>Configuration errors reported by the instrument (KXCI error buffer) stop the run with the instrument's
    message.</li>
    <li>The Stop button aborts a running test; the data captured so far is returned.</li>
    <li>The channel output is always switched off when the run finishes, including after an error.</li>
    </ul>
    """

    variables = ["Voltage", "Current", "Time"]
    units = ["V", "A", "s"]

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
        """Return the CSV paths and instrument settings as list[str]."""
        return self.widget.get_setting()

    def set_setting(self, setting: list[str]) -> None:
        """Restore the CSV paths and instrument settings."""
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

    def main(self):
        parameters = self.widget.instrument_settings.get_parameters()
        sequences, sequence_list = self._read_waveform()

        for _times, start_v, stop_v in sequences.values():
            v_max = max(abs(v) for v in start_v + stop_v)
            if v_max > parameters["voltage_range"]:
                raise ValueError(
                    f"The waveform reaches {v_max:g} V, which exceeds the {parameters['voltage_range']} V source range."
                )

        self.channel = channel = parameters["channel"]
        self._ensure_connected(parameters["port"])
        pmu = self.pmu

        # Clear the KXCI error buffer so any error read later belongs to this run. Ethernet KXCI acknowledges every
        # command with ACK on receipt; real errors (e.g. -951 from the final verification in EXECUTE) land only in
        # this buffer and on the instrument's console.
        pmu.clear_last_error()

        # :PMU:INIT must come first - it also clears the data buffer and deletes any previously defined sequences.
        pmu.init(KXCIPMU.MODE_SEGARB)
        if parameters["configure_rpm"]:
            pmu.configure_rpm(self._rpm_hrid(channel), KXCIPMU.RPM_MODE_PMU)
        # SegArb requires fixed ranges for both voltage (source) and current (measure).
        pmu.set_source_range(channel, parameters["voltage_range"])
        pmu.set_measure_range(channel, KXCIPMU.RANGE_FIXED, parameters["current_range"])
        pmu.set_load(channel, parameters["load"])

        setup_error = self._read_error()
        if setup_error:
            raise RuntimeError(f"PMU channel setup (RPM/ranges/load) failed - instrument reports: {setup_error}")

        # Define every used sequence; each segment is measured over its full duration.
        for seq_id, (times, start_v, stop_v) in sequences.items():
            pmu.set_segment_times(channel, seq_id, times)
            pmu.set_start_voltages(channel, seq_id, start_v)
            pmu.set_stop_voltages(channel, seq_id, stop_v)
            pmu.set_measure_types(channel, seq_id, [KXCIPMU.MEAS_WAVEFORM_DISCRETE] * len(times))
            pmu.set_measure_starts(channel, seq_id, [0.0] * len(times))
            pmu.set_measure_stops(channel, seq_id, times)

        pmu.set_sequence_list(channel, sequence_list)
        pmu.set_sample_rate(parameters["sample_rate"])

        total_duration = sum(sum(sequences[seq_id][0]) * reps for seq_id, reps in sequence_list)

        try:
            pmu.set_output_state(channel, KXCIPMU.OUTPUT_ON)
            pmu.execute()
            self._wait_until_idle(timeout=2 * total_duration + START_TIMEOUT_S)
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
            sequences: {seq_id: (times, start_voltages, stop_voltages)} for every sequence used in the waveform.
            sequence_list: [(seq_id, repetitions), ...] in playback order.
        """
        all_sequences = self.widget.sequence_tabs.get_all_sequences()
        sequence_list = self.widget.waveform_table.get_waveform_data()
        if not sequence_list:
            raise ValueError("The waveform table is empty. Add at least one row (sequence ID, repetitions).")

        sequences = {}
        for seq_id, _reps in sequence_list:
            if seq_id not in sequences:
                xs, ys = all_sequences[seq_id - 1]
                sequences[seq_id] = build_segments(seq_id, xs, ys)

        check_sequence_list(sequences, sequence_list)
        return sequences, sequence_list

    @staticmethod
    def _rpm_hrid(channel: int) -> str:
        """Map a global pulse channel (1-8) to its RPM id ``PMU<card>-<channel-on-card>``.

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
            error = self.pmu.get_last_error().strip()
        except Exception:
            return ""
        return error if "(-" in error else ""

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
            error = self._read_error()
            if error:
                self.pmu.abort()
                raise RuntimeError(f"SegArb test failed to arm - instrument reports: {error}")
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
