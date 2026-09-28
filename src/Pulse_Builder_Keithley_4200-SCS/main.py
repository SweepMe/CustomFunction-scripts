# author: Franz Hempel
# created on: 2026-06-19
# company/institute: SweepMe!
"""CustomFunction script: run a segmented-arbitrary (SegArb) pulse on a Keithley 4200A-SCS via KXCI.

The waveform is described by a list of voltage levels and the segment durations between them
(N levels -> N-1 segments). Start/stop voltages are derived from consecutive levels so the
segment transitions are always seamless. Every segment is measured (waveform-discrete) over its
full duration; the captured voltage, current and timestamp are returned as three arrays.
"""
from __future__ import annotations

import time

import numpy as np

from pysweepme import FolderManager, Ports
FolderManager.addFolderToPATH()  # makes libs/kxci_pmu.py importable

import importlib
import kxci_pmu

importlib.reload(kxci_pmu)

from kxci_pmu import KXCIPMU


class Main():

    """
    <h2>Keithley 4200A-SCS &ndash; SegArb pulse (KXCI)</h2>

    <p>Outputs a user-defined <b>segmented arbitrary (SegArb) waveform</b> on one PMU channel of a
    Keithley 4200A-SCS and records the pulse response. Every segment is captured as a waveform, and
    the <b>voltage</b>, <b>current</b> and <b>time</b> samples are returned as three equally long
    traces.</p>

    <p>Communication uses <b>KXCI</b> (Keithley External Control Interface) over a raw TCP/IP
    socket. KXCI must be enabled on the 4200A-SCS and the instrument reachable at the configured
    address before the run is started.</p>

    <h3>Defining the waveform</h3>
    <p>The waveform is given as a list of <b>voltage levels</b> (the voltage at each segment
    boundary) plus the <b>segment times</b> between them. <i>N</i> levels therefore need
    <i>N&nbsp;-&nbsp;1</i> times. Consecutive levels become the start and stop voltage of each
    segment, so the transitions are always seamless &ndash; a hard requirement of SegArb. Each
    segment is measured over its full duration.</p>
    <p><b>Example</b> (the defaults): levels <code>0, 0, 1, 1, 0, 0</code> with times
    <code>1e-6, 1e-7, 1e-6, 1e-7, 1e-6</code> produce: hold 0&nbsp;V for 1&micro;s, ramp
    0&rarr;1&nbsp;V in 0.1&micro;s, hold 1&nbsp;V for 1&micro;s, ramp 1&rarr;0&nbsp;V in
    0.1&micro;s, hold 0&nbsp;V for 1&micro;s. Set <b>Repetitions</b> above 1 to replay the whole
    sequence back-to-back.</p>

    <h3>Parameters</h3>
    <ul>
    <li><b>Port</b> &ndash; VISA SOCKET address of the KXCI server, e.g.
    <code>TCPIP0::192.168.100.4::8888::SOCKET</code>.</li>
    <li><b>Channel</b> &ndash; PMU channel to pulse and measure (1 or 2).</li>
    <li><b>Voltage levels in V</b> &ndash; comma-separated voltages at the segment boundaries (at
    least two). Each value must lie within the selected source range.</li>
    <li><b>Segment times in s</b> &ndash; comma-separated segment durations; exactly one fewer than
    the number of voltage levels. Roughly 20&nbsp;ns to 1&nbsp;s per segment, in 10&nbsp;ns
    steps.</li>
    <li><b>Repetitions</b> &ndash; how often the sequence is replayed in a row (1 to 1e12).</li>
    <li><b>Current measure range in A</b> &ndash; fixed current range (SegArb requires a fixed
    range), e.g. <code>1e-2</code>, <code>1e-4</code> or <code>1e-6</code>. Pick one that covers the
    expected current.</li>
    <li><b>Voltage source range in V</b> &ndash; <code>10</code> or <code>40</code>; must be larger
    than the largest absolute voltage level (&plusmn;10&nbsp;V or &plusmn;40&nbsp;V).</li>
    <li><b>Configure RPM</b> &ndash; enable when a 4225-RPM is connected to the channel (routes the
    pulse through the RPM); disable for a direct PMU connection.</li>
    </ul>

    <h3>Output</h3>
    <p>Three traces are returned and saved: <b>Voltage</b> (V), <b>Current</b> (A) and <b>Time</b>
    (s), one entry per measured sample. The number of samples grows with the total measured time
    (instrument default sample rate, up to 65536 points per channel).</p>

    <h3>Notes</h3>
    <ul>
    <li>The number of segment times must equal the number of voltage levels minus one, and at least
    one segment is required &ndash; otherwise the run stops with an error.</li>
    <li>Fixed voltage and current ranges are mandatory for SegArb and are applied automatically from
    the values above.</li>
    <li>The channel output is always switched off when the run finishes, including after an
    error.</li>
    </ul>
    """

    variables = ["Voltage", "Current", "Time"]
    units = ["V", "A", "s"]

    arguments = {
        "Port": "TCPIP0::192.168.100.4::8888::SOCKET",
        "Channel": [1, 2],
        "Voltage levels in V": "0, 0, 1, 1, 0, 0",
        "Segment times in s": "1e-6, 1e-7, 1e-6, 1e-7, 1e-6",
        "Repetitions": 1,
        "Current measure range in A": 1e-6,
        "Voltage source range in V": ["10", "40"],
        "Configure RPM": True,
    }

    def __init__(self):
        self.port = None
        self.pmu = None

    # ------------------------------------------------------------------ #
    # port lifecycle
    # ------------------------------------------------------------------ #

    def _ensure_connected(self, port_id: str) -> None:
        """Open the KXCI socket once and wrap it; reused across main() calls within a run.

        The port is built manually - a TCPIPport plus a directly-opened pyvisa resource - instead
        of via pysweepme.get_port(), to work around a bug in the PortManager shipped with the
        SweepMe! executable. The null-character terminators and timeout are applied straight onto
        the pyvisa resource.
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
        channel = int(kwargs["Channel"])
        levels = self._parse_floats(kwargs["Voltage levels in V"])
        times = self._parse_floats(kwargs["Segment times in s"])
        repetitions = int(kwargs["Repetitions"])
        current_range = float(kwargs["Current measure range in A"])
        voltage_range = int(kwargs["Voltage source range in V"])
        configure_rpm = bool(kwargs["Configure RPM"])

        if len(levels) < 2:
            raise ValueError("Provide at least two voltage levels (i.e. at least one segment).")
        if len(times) != len(levels) - 1:
            raise ValueError(
                f"Expected {len(levels) - 1} segment time(s) for {len(levels)} voltage levels, "
                f"but got {len(times)}."
            )

        self._ensure_connected(kwargs["Port"])
        pmu = self.pmu
        sequence = 1

        # One-time SegArb setup. :PMU:INIT must come first - it also clears the data buffer and
        # deletes any previously defined sequences, so the run starts from a clean state.
        pmu.init(KXCIPMU.MODE_SEGARB)
        if configure_rpm:
            pmu.configure_rpm(self._rpm_hrid(channel), KXCIPMU.RPM_MODE_PMU)
        # SegArb requires fixed ranges for both voltage (source) and current (measure).
        pmu.set_source_range(channel, voltage_range)
        pmu.set_measure_range(channel, KXCIPMU.RANGE_FIXED, current_range)

        # Define the sequence. Consecutive levels give the per-segment start/stop voltages, which
        # guarantees the seamless transitions SegArb requires. Each segment is measured over its
        # full duration (start = 0, stop = segment time).
        start_voltages = levels[:-1]
        stop_voltages = levels[1:]
        measure_types = [KXCIPMU.MEAS_WAVEFORM_DISCRETE] * len(times)
        measure_starts = [0.0] * len(times)
        measure_stops = list(times)

        pmu.set_segment_times(channel, sequence, times)
        pmu.set_start_voltages(channel, sequence, start_voltages)
        pmu.set_stop_voltages(channel, sequence, stop_voltages)
        pmu.set_measure_types(channel, sequence, measure_types)
        pmu.set_measure_starts(channel, sequence, measure_starts)
        pmu.set_measure_stops(channel, sequence, measure_stops)

        # Play sequence 1 the requested number of times, then run.
        pmu.set_sequence_list(channel, [(sequence, repetitions)])

        try:
            pmu.set_output_state(channel, KXCIPMU.OUTPUT_ON)
            pmu.execute()
            self._wait_until_idle()
            voltage, current, timestamp = pmu.read_voltage_current_time(channel)
        finally:
            # Always turn the output off, even if the run or readback fails.
            pmu.set_output_state(channel, KXCIPMU.OUTPUT_OFF)

        return np.array(voltage), np.array(current), np.array(timestamp)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_floats(text: str) -> list[float]:
        """Parse a comma-separated string of numbers into a list of floats."""
        return [float(item) for item in text.split(",") if item.strip() != ""]

    @staticmethod
    def _rpm_hrid(channel: int) -> str:
        """Map a global pulse channel (1-8) to its RPM id ``PMU<card>-<channel-on-card>``.

        Each PMU card carries two channels, so channels 1,2 -> PMU1-1,PMU1-2; 3,4 -> PMU2-1, ...
        """
        card = (channel - 1) // 2 + 1
        channel_on_card = (channel - 1) % 2 + 1
        return f"PMU{card}-{channel_on_card}"

    def _wait_until_idle(self, poll_interval: float = 0.2) -> None:
        """Block until :PMU:TEST:STATUS? reports the test is idle/complete."""
        while self.pmu.get_test_status() == KXCIPMU.STATUS_RUNNING:
            time.sleep(poll_interval)


if __name__ == "__main__":

    # Standalone test - requires a reachable 4200A-SCS. Run from this folder: python main.py
    script = Main()

    arguments = {
        "Port": "TCPIP0::192.168.100.4::8888::SOCKET",
        "Channel": 1,
        "Voltage levels in V": "0, 0, 1, 1, 0, 0",
        "Segment times in s": "1e-6, 1e-7, 1e-6, 1e-7, 1e-6",
        "Repetitions": 1,
        "Current measure range in A": 1e-6,
        "Voltage source range in V": "10",  # the GUI ComboBox hands over the selected string
        "Configure RPM": True,
    }

    try:
        voltage, current, timestamp = script.main(**arguments)
        print(f"Captured {len(voltage)} points.")
        print("V:", voltage)
        print("I:", current)
        print("T:", timestamp)
    finally:
        script.disconnect()

    print("CustomFunction script 'Pulse_Builder_Keithley_4200-SCS' finished.")
