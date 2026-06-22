"""Thin Python wrappers around the Keithley 4200A-SCS KXCI PMU SegArb commands.

Each public method maps to exactly one ``:PMU:...`` KXCI remote command as documented in the
*4200A-SCS KXCI Programming* manual (4200A-KXCI-907-01 Rev. D, May 2024, Section 7
"KXCI PGU and PMU commands"). The wrappers cover the Segmented Arbitrary Waveform (SegArb)
workflow used by the pulse-generator MWE: initialise the PMU, configure ranges, define one or
more segment sequences, build a waveform sequence list, run the test, and read the data back.

A connected ``pysweepme`` port object is injected on construction. Every command - including the
setters - is sent with ``port.query()`` because KXCI returns an acknowledgement string for each
command; the acknowledgement is returned by the private ``_query`` helper so it can be inspected
later if needed.

Typical use (mirrors the MWE)::

    from kxci_pmu import KXCIPMU

    pmu = KXCIPMU(port)
    pmu.init(KXCIPMU.MODE_SEGARB)                 # :PMU:INIT 1
    pmu.configure_rpm("PMU1-1")                   # :PMU:RPM:CONFIGURE PMU1-1, 0
    pmu.set_measure_range(1, KXCIPMU.RANGE_FIXED, 1e-6)

    pmu.set_segment_times(1, 1, [1e-6, 1e-7, 1e-6, 1e-7, 1e-6])
    pmu.set_start_voltages(1, 1, [0, 0, 1, 1, 0])
    pmu.set_stop_voltages(1, 1, [0, 1, 1, 0, 0])
    pmu.set_measure_types(1, 1, [KXCIPMU.MEAS_WAVEFORM_DISCRETE] * 5)
    pmu.set_measure_starts(1, 1, [0, 0, 0, 0, 0])
    pmu.set_measure_stops(1, 1, [1e-6, 1e-7, 1e-6, 1e-7, 1e-6])

    pmu.set_sequence_list(1, [(1, 1)])            # play sequence 1 once
    pmu.set_output_state(1, KXCIPMU.OUTPUT_ON)
    pmu.execute()
    while pmu.get_test_status() != KXCIPMU.STATUS_IDLE:
        ...
    count = pmu.get_data_count(1)
    raw = pmu.get_data(1, 0, 2048, ["V"])
    pmu.set_output_state(1, KXCIPMU.OUTPUT_OFF)

This module covers the full single-call SegArb workflow, including the commands the MWE omits but
that SegArb requires or benefits from: the fixed *voltage* source range (``:PMU:SOURCE:RANGE`` -
the manual requires fixed ranges for BOTH current and voltage), the sample rate
(``:PMU:SAMPLE:RATE``) and the per-segment relay (``:PMU:SARB:SEQ:SSR``) and trigger
(``:PMU:SARB:SEQ:TRIG``) arrays, plus ``:PMU:ABORT`` for a safety stop.

Still out of scope (add when needed): the ``...:ADD`` array variants for sequences longer than
128 segments, connection/load-line compensation, and the standard (non-SegArb) pulse-mode commands.
"""
from __future__ import annotations


class KXCIPMU:
    """Wrapper for the KXCI ``:PMU:`` SegArb command set of the Keithley 4200A-SCS."""

    # :PMU:INIT <mode>
    MODE_PULSE = 0
    MODE_SEGARB = 1

    # :PMU:RPM:CONFIGURE <hrid>, <mode> - the RPM signal path
    RPM_MODE_PMU = 0
    RPM_MODE_CV_2W = 1
    RPM_MODE_SMU = 2
    RPM_MODE_CV_4W = 3

    # :PMU:MEASURE:RANGE <ch>, <range_type>[, <range>] - current range type
    RANGE_AUTO = 0
    RANGE_LIMITED = 1
    RANGE_FIXED = 2

    # :PMU:SOURCE:RANGE <ch>, <voltage_range> - fixed voltage source range (V)
    SOURCE_RANGE_10V = 10
    SOURCE_RANGE_40V = 40

    # :PMU:SARB:SEQ:MEAS:TYPE - per-segment measure mode
    MEAS_NONE = 0
    MEAS_SPOT_MEAN_DISCRETE = 1
    MEAS_WAVEFORM_DISCRETE = 2
    MEAS_SPOT_MEAN_AVERAGE = 3
    MEAS_WAVEFORM_AVERAGE = 4

    # :PMU:SARB:SEQ:SSR - per-segment high-endurance output relay state
    SSR_OPEN = 0
    SSR_CLOSED = 1

    # :PMU:SARB:SEQ:TRIG - per-segment trigger-output state
    TRIG_LOW = 0
    TRIG_HIGH = 1

    # :PMU:OUTPUT:STATE <ch>, <state>
    OUTPUT_OFF = 0
    OUTPUT_ON = 1

    # :PMU:TEST:STATUS? return values
    STATUS_IDLE = 0
    STATUS_RUNNING = 1

    # :PMU:DATA:GET - maximum number of points returned per call
    MAX_POINTS_PER_GET = 2048

    def __init__(self, port) -> None:
        """Store the connected pysweepme port used for all KXCI communication."""
        self.port = port

    # ------------------------------------------------------------------ #
    # low-level helpers
    # ------------------------------------------------------------------ #

    def _query(self, command: str) -> str:
        """Send a single KXCI command and return its acknowledgement string.

        KXCI replies to every command (setters included), so all commands are funnelled through
        ``port.query`` here. Centralising it keeps a single place to add acknowledgement/error
        checking later.
        """
        return self.port.query(command)

    @staticmethod
    def _format_array(values) -> str:
        """Format a numeric iterable as the comma-separated tail of a command."""
        return ", ".join(str(value) for value in values)

    # ------------------------------------------------------------------ #
    # setup
    # ------------------------------------------------------------------ #

    def init(self, mode: int = MODE_SEGARB) -> str:
        """``:PMU:INIT`` - reset the pulse card and select the pulse mode.

        Must be the FIRST PMU command sent. Resets both channels to the mode defaults, clears
        the data buffer and deletes all existing SegArb sequences.

        Args:
            mode: ``MODE_PULSE`` (0) for standard pulse, ``MODE_SEGARB`` (1) for Segment Arb.
        """
        return self._query(f":PMU:INIT {mode}")

    def configure_rpm(self, hrid: str, mode: int = RPM_MODE_PMU) -> str:
        """``:PMU:RPM:CONFIGURE`` - route an RPM channel to a given signal path.

        Required when a 4225-RPM is present: connects the PMU pulse source to the RPM output.

        Args:
            hrid: instrument/channel id, e.g. ``"PMU1-1"`` (card 1, channel 1) or ``"PMU1-2"``.
            mode: signal path - ``RPM_MODE_PMU`` (0), ``RPM_MODE_CV_2W`` (1),
                ``RPM_MODE_SMU`` (2) or ``RPM_MODE_CV_4W`` (3).
        """
        return self._query(f":PMU:RPM:CONFIGURE {hrid}, {mode}")

    def set_measure_range(
        self, channel: int, range_type: int, current_range: float | None = None,
    ) -> str:
        """``:PMU:MEASURE:RANGE`` - set the current measure range for a channel.

        SegArb requires a FIXED range (``RANGE_FIXED``). The voltage range is set separately with
        ``:PMU:SOURCE:RANGE`` (not wrapped here) and is also required to be fixed for SegArb.

        Args:
            channel: pulse channel, 1-8.
            range_type: ``RANGE_AUTO`` (0), ``RANGE_LIMITED`` (1) or ``RANGE_FIXED`` (2).
            current_range: fixed/limited range in amps (e.g. ``1e-6``). Ignored - and may be
                omitted - when ``range_type`` is ``RANGE_AUTO``.
        """
        if current_range is None:
            return self._query(f":PMU:MEASURE:RANGE {channel}, {range_type}")
        return self._query(f":PMU:MEASURE:RANGE {channel}, {range_type}, {current_range}")

    def set_source_range(self, channel: int, voltage_range: int = SOURCE_RANGE_10V) -> str:
        """``:PMU:SOURCE:RANGE`` - set the voltage source (and measure) range for a channel.

        Required for SegArb, which needs a fixed voltage range. This bounds the STARTV/STOPV
        values and takes effect on :meth:`execute`.

        Args:
            channel: pulse channel, 1-8.
            voltage_range: ``SOURCE_RANGE_10V`` (10) or ``SOURCE_RANGE_40V`` (40).
        """
        return self._query(f":PMU:SOURCE:RANGE {channel}, {voltage_range}")

    def set_load(self, channel: int, load: float) -> str:
        """``:PMU:LOAD`` - tell the PMU the DUT load resistance for a channel.

        Used by the instrument for load-line correction of the programmed voltage.

        Args:
            channel: pulse channel, 1-8.
            load: DUT impedance in ohms, 1.0 to 1e7 (default on the instrument is 1e6).
        """
        return self._query(f":PMU:LOAD {channel}, {load}")

    def set_sample_rate(self, rate: int) -> str:
        """``:PMU:SAMPLE:RATE`` - set the A/D sample rate in samples/second (1e3 to 200e6).

        Applies to all channels. The instrument auto-adjusts the rate if it is too slow for the
        shortest measure window, or too fast to keep the total point count within 65536.
        """
        return self._query(f":PMU:SAMPLE:RATE {int(rate)}")

    # ------------------------------------------------------------------ #
    # SegArb sequence definition (one array per call, overwrites previous)
    # ------------------------------------------------------------------ #

    def set_segment_times(self, channel: int, sequence: int, times) -> str:
        """``:PMU:SARB:SEQ:TIME`` - per-segment durations (s) for one sequence.

        One value per segment; 10 ns resolution. Up to 128 values per call. Overwrites any
        previous array for this (channel, sequence).
        """
        return self._set_sarb_seq("TIME", channel, sequence, times)

    def set_start_voltages(self, channel: int, sequence: int, voltages) -> str:
        """``:PMU:SARB:SEQ:STARTV`` - per-segment start voltages (V) for one sequence.

        Transitions must be seamless: each segment's stop voltage must equal the next segment's
        start voltage. The range is limited by the source range (+/-10 V or +/-40 V).
        """
        return self._set_sarb_seq("STARTV", channel, sequence, voltages)

    def set_stop_voltages(self, channel: int, sequence: int, voltages) -> str:
        """``:PMU:SARB:SEQ:STOPV`` - per-segment stop voltages (V) for one sequence."""
        return self._set_sarb_seq("STOPV", channel, sequence, voltages)

    def set_measure_types(self, channel: int, sequence: int, meas_types) -> str:
        """``:PMU:SARB:SEQ:MEAS:TYPE`` - per-segment measure mode for one sequence.

        Each value is one of ``MEAS_NONE`` (0), ``MEAS_SPOT_MEAN_DISCRETE`` (1),
        ``MEAS_WAVEFORM_DISCRETE`` (2), ``MEAS_SPOT_MEAN_AVERAGE`` (3) or
        ``MEAS_WAVEFORM_AVERAGE`` (4).
        """
        return self._set_sarb_seq("MEAS:TYPE", channel, sequence, meas_types)

    def set_measure_starts(self, channel: int, sequence: int, start_times) -> str:
        """``:PMU:SARB:SEQ:MEAS:START`` - per-segment measure start times (s).

        Elapsed time within each segment at which measuring begins (0 = start of segment). Each
        value must be <= the matching MEAS:STOP value and <= the segment TIME value.
        """
        return self._set_sarb_seq("MEAS:START", channel, sequence, start_times)

    def set_measure_stops(self, channel: int, sequence: int, stop_times) -> str:
        """``:PMU:SARB:SEQ:MEAS:STOP`` - per-segment measure stop times (s).

        Elapsed time within each segment at which measuring stops. Each value must be > the
        matching MEAS:START (unless both are 0) and <= the segment TIME value.
        """
        return self._set_sarb_seq("MEAS:STOP", channel, sequence, stop_times)

    def set_ssr(self, channel: int, sequence: int, states) -> str:
        """``:PMU:SARB:SEQ:SSR`` - per-segment high-endurance output relay (HEOR) states.

        One value per segment: ``SSR_OPEN`` (0) electrically isolates the output (floating),
        ``SSR_CLOSED`` (1) outputs the segment. A segment containing a relay transition needs at
        least 25 us. Defaults to closed for all segments if never set.
        """
        return self._set_sarb_seq("SSR", channel, sequence, states)

    def set_triggers(self, channel: int, sequence: int, states) -> str:
        """``:PMU:SARB:SEQ:TRIG`` - per-segment trigger-output states.

        One value per segment: ``TRIG_LOW`` (0) or ``TRIG_HIGH`` (1) on the trigger output.
        Defaults to high for all segments if never set.
        """
        return self._set_sarb_seq("TRIG", channel, sequence, states)

    def _set_sarb_seq(self, keyword: str, channel: int, sequence: int, values) -> str:
        """Send a ``:PMU:SARB:SEQ:<keyword> ch, seq, v1, v2, ...`` array command."""
        return self._query(
            f":PMU:SARB:SEQ:{keyword} {channel}, {sequence}, {self._format_array(values)}"
        )

    # ------------------------------------------------------------------ #
    # waveform list & execution
    # ------------------------------------------------------------------ #

    def set_sequence_list(self, channel: int, sequence_loops) -> str:
        """``:PMU:SARB:WFM:SEQ:LIST`` - playback order for a channel.

        Args:
            channel: pulse channel, 1-8.
            sequence_loops: ordered list of ``(sequence_id, loop_count)`` pairs. Each referenced
                sequence must already be defined. ``loop_count`` may be 1 to 1e12.
                Example: ``[(1, 10)]`` plays sequence 1 ten times; ``[(1, 1), (2, 3)]`` plays
                sequence 1 once then sequence 2 three times.
        """
        flat = []
        for sequence_id, loop_count in sequence_loops:
            flat.append(sequence_id)
            flat.append(loop_count)
        return self._query(f":PMU:SARB:WFM:SEQ:LIST {channel}, {self._format_array(flat)}")

    def set_output_state(self, channel: int, state: int) -> str:
        """``:PMU:OUTPUT:STATE`` - turn a channel output on/off.

        Turning on takes effect on :meth:`execute`; turning off is immediate. Always set the
        output back to ``OUTPUT_OFF`` at the end of a test.

        Args:
            channel: pulse channel, 1-8.
            state: ``OUTPUT_OFF`` (0) or ``OUTPUT_ON`` (1).
        """
        return self._query(f":PMU:OUTPUT:STATE {channel}, {state}")

    def execute(self) -> str:
        """``:PMU:EXECUTE`` - start the configured test. Returns immediately.

        Poll :meth:`get_test_status` until it returns ``STATUS_IDLE`` before reading data.
        """
        return self._query(":PMU:EXECUTE")

    def abort(self) -> str:
        """``:PMU:ABORT`` - stop all running PMU processes and turn the outputs off.

        Buffered data is retained. Useful to interrupt a running test or as a safety stop.
        """
        return self._query(":PMU:ABORT")

    # ------------------------------------------------------------------ #
    # status & data readback
    # ------------------------------------------------------------------ #

    def get_test_status(self) -> int:
        """``:PMU:TEST:STATUS?`` - ``STATUS_IDLE`` (0, complete/idle) or ``STATUS_RUNNING`` (1)."""
        return int(self._query(":PMU:TEST:STATUS?"))

    def get_data_count(self, channel: int) -> int:
        """``:PMU:DATA:COUNT?`` - number of readings buffered for ``channel`` (1-8)."""
        return int(self._query(f":PMU:DATA:COUNT? {channel}"))

    def get_data(
        self,
        channel: int,
        start_index: int | None = None,
        num_points: int | None = None,
        requested_values: list[str] | None = None,
    ) -> str:
        """``:PMU:DATA:GET`` - read one block of buffered data for ``channel``.

        Returns at most ``MAX_POINTS_PER_GET`` (2048) points per call; loop with an advancing
        ``start_index`` to read all points reported by :meth:`get_data_count`.

        Args:
            channel: pulse channel, 1-8.
            start_index: 0-based index of the first point to return. Omit to start at 0.
            num_points: number of points to return, 1-2048. Omit for "all available" (<=2048).
            requested_values: which fields to return per point, in order. Waveform fields:
                ``"V"``, ``"I"``, ``"T"`` (timestamp), ``"S"`` (status). Spot-mean fields:
                ``"VH"/"IH"/"TH"/"SH"`` (high) and ``"VL"/"IL"/"TL"/"SL"`` (low). Omit for the
                instrument default. If given, ``start_index`` and ``num_points`` are required too
                (the command is positional).

        Returns:
            Raw response string: points separated by ``;``, fields within a point by ``,``.
        """
        if requested_values and (start_index is None or num_points is None):
            raise ValueError(
                "requested_values requires both start_index and num_points to be specified"
            )

        parts = [str(channel)]
        if start_index is not None:
            parts.append(str(start_index))
        if num_points is not None:
            parts.append(str(num_points))
        if requested_values:
            parts.append(", ".join(requested_values))
        return self._query(":PMU:DATA:GET " + ", ".join(parts))

    def read_value(self, channel: int, value_type: str) -> list[float]:
        """Read ALL buffered points of a single numeric quantity for a channel.

        Loops :meth:`get_data` in ``MAX_POINTS_PER_GET``-sized blocks until every point reported
        by :meth:`get_data_count` has been read. A single field is requested per call, so each
        response is simply ``;``-separated values (no commas within a point).

        Args:
            channel: pulse channel, 1-8.
            value_type: one numeric field - ``"V"``, ``"I"``, ``"T"`` (timestamp), or a numeric
                spot-mean field (``"VH"/"IH"/"TH"/"VL"/"IL"/"TL"``). Status (``"S"``) is not a
                float and must be read via :meth:`get_data` instead.

        Returns:
            All points of the requested quantity as a list of floats.
        """
        count = self.get_data_count(channel)
        values: list[float] = []
        for start in range(0, count, self.MAX_POINTS_PER_GET):
            num_points = min(self.MAX_POINTS_PER_GET, count - start)
            response = self.get_data(channel, start, num_points, [value_type])
            values.extend(float(item) for item in response.split(";") if item.strip())
        return values

    def read_voltage_current_time(self, channel: int):
        """Read all buffered voltage, current and timestamp points for a channel.

        Each quantity is fetched with its own single-field :meth:`read_value` pass (the firmware
        returns single-field blocks more reliably than multi-field ones). The reads are
        non-destructive, so fetching the three quantities one after another is safe.

        Returns:
            ``(voltages, currents, timestamps)`` - three lists of floats of equal length.
        """
        return (
            self.read_value(channel, "V"),
            self.read_value(channel, "I"),
            self.read_value(channel, "T"),
        )
