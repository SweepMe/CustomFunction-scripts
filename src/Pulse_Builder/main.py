# author:
# created at:
# company/institute:

from pysweepme.ErrorMessage import error

from PySide2 import QtWidgets, QtGui, QtCore
from matplotlib import pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT
from matplotlib.figure import Figure


# Shared color cycle — used by both SequenceTabWidget (tab icons) and PlotWidget (lines)
# so that each sequence's tab icon always matches its plot line color.
COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
]

def _sequence_color(index):
    return COLORS[index % len(COLORS)]

def _color_icon(color_str):
    """Small filled square icon used to link a tab visually to its plot line."""
    pixmap = QtGui.QPixmap(12, 12)
    pixmap.fill(QtGui.QColor(color_str))
    return QtGui.QIcon(pixmap)


def compute_waveform(sequences, waveform_entries):
    """Build a combined (xs, ys) waveform from sequence data and waveform table entries.

    sequences:        list of (xs, ys) — one per sequence tab, timestamps relative (start at 0)
    waveform_entries: list of (seq_id, reps) — 1-based seq_id, positive int repetitions

    For each entry the sequence is repeated `reps` times. Timestamps are offset by a
    running time cursor that advances by max(xs) of that sequence per repetition.
    Returns flat (xs, ys) lists, or ([], []) for empty/invalid input.
    """
    xs_out, ys_out = [], []
    t_cursor = 0.0

    for seq_id, reps in waveform_entries:
        idx = seq_id - 1
        if idx < 0 or idx >= len(sequences):
            continue
        seq_xs, seq_ys = sequences[idx]
        if not seq_xs:
            continue
        duration = max(seq_xs)
        for _ in range(reps):
            for x, y in zip(seq_xs, seq_ys):
                xs_out.append(t_cursor + x)
                ys_out.append(y)
            t_cursor += duration

    return xs_out, ys_out


class Main():

    variables = []
    units = []

    def renew_widget(self, widget=None):
        """Gets the widget from the module and returns the same or creates a new one.
        Called in the main GUI thread."""

        if widget is None:
            self.widget = Widget()
        else:
            self.widget = widget

        return self.widget

    def initialize(self):
        # Preserve the user-defined pulse form across runs — do not clear the table.
        pass

    def main(self):
        return


# ---------------------------------------------------------------------------
# Top-level container widget
# ---------------------------------------------------------------------------

class Widget(QtWidgets.QWidget):

    def __init__(self):
        super().__init__()

        self._sequences = []
        self._waveform_entries = []

        self.setLayout(self._create_layout())

        # Initialize sequence count for waveform table validation
        self._sequences = self.sequence_tabs.get_all_sequences()
        self.waveform_table.update_sequence_count(len(self._sequences))

        # Wire signals
        self.sequence_tabs.sequences_changed.connect(self._on_sequences_changed)
        self.waveform_table.waveform_changed.connect(self._on_waveform_changed)

    def _create_layout(self):
        self.plot_widget   = PlotWidget(self)
        self.sequence_tabs = SequenceTabWidget(self)
        self.waveform_table = WaveformTableWidget(self)

        # Right panel: sequence tabs on top, waveform table on bottom
        right_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        right_splitter.addWidget(self.sequence_tabs)
        right_splitter.addWidget(self.waveform_table)
        right_splitter.setSizes([350, 200])

        # Main horizontal split: plot (left) | right panel
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self.plot_widget)
        splitter.addWidget(right_splitter)
        splitter.setSizes([700, 300])

        grid = QtWidgets.QGridLayout()
        grid.addWidget(splitter, 0, 0)
        return grid

    def _on_sequences_changed(self, sequences):
        self._sequences = sequences
        self.plot_widget.set_segments(sequences)
        self.waveform_table.update_sequence_count(len(sequences))
        self._recompute_waveform()

    def _on_waveform_changed(self, entries):
        self._waveform_entries = entries
        self._recompute_waveform()

    def _recompute_waveform(self):
        xs, ys = compute_waveform(self._sequences, self._waveform_entries)
        self.plot_widget.set_waveform(xs, ys)


# ---------------------------------------------------------------------------
# Matplotlib plot widget — two tabs: Sequences + Waveform
# ---------------------------------------------------------------------------

class PlotWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setSizePolicy(
            QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                  QtWidgets.QSizePolicy.Expanding)
        )

        # --- Sequences canvas ---
        self.seq_canvas = MyMplCanvas(self)
        self.lines = []
        seq_ax = self.seq_canvas.fig.add_subplot(111)
        self.seq_canvas.axes = seq_ax
        seq_ax.set_title("Sequences")
        seq_ax.set_xlabel("Time in s")
        seq_ax.set_ylabel("Voltage in V")
        seq_ax.grid(True, linestyle='--', alpha=0.5)
        self.seq_canvas.draw()

        # --- Waveform canvas ---
        self.wf_canvas = MyMplCanvas(self)
        wf_ax = self.wf_canvas.fig.add_subplot(111)
        self.wf_canvas.axes = wf_ax
        wf_ax.set_title("Waveform")
        wf_ax.set_xlabel("Time in s")
        wf_ax.set_ylabel("Voltage in V")
        wf_ax.grid(True, linestyle='--', alpha=0.5)
        self.waveform_line, = wf_ax.plot([], [], linewidth=1.5, marker='o', markersize=4)
        self.wf_canvas.draw()

        # --- Tab widget holding both canvases ---
        self.tab_widget = QtWidgets.QTabWidget(self)
        self.tab_widget.addTab(self.seq_canvas, "Sequences")
        self.tab_widget.addTab(self.wf_canvas, "Waveform")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tab_widget)

    def set_segments(self, segments):
        """Redraw all sequence lines from scratch.

        segments: list of (xs, ys) tuples, one entry per sequence tab.
        Lines are removed and recreated on every call so that colors always
        stay in sync with the tab order.
        """
        ax = self.seq_canvas.axes

        for line in self.lines:
            line.remove()
        self.lines = []

        for i, (xs, ys) in enumerate(segments):
            line, = ax.plot(
                xs, ys,
                linewidth=1.5, marker='o', markersize=4,
                color=_sequence_color(i),
            )
            self.lines.append(line)

        try:
            ax.relim()
            ax.autoscale_view()
            self.seq_canvas.fig.tight_layout(pad=0.2)
            self.seq_canvas.draw()
        except Exception:
            error()

    def set_waveform(self, xs, ys):
        """Update the combined waveform plot."""
        try:
            plt.setp(self.waveform_line, xdata=xs, ydata=ys)
            self.wf_canvas.axes.relim()
            self.wf_canvas.axes.autoscale_view()
            self.wf_canvas.fig.tight_layout(pad=0.2)
            self.wf_canvas.draw()
        except Exception:
            error()

    def clear_data(self):
        ax = self.seq_canvas.axes
        for line in self.lines:
            line.remove()
        self.lines = []
        try:
            self.seq_canvas.draw()
        except Exception:
            pass
        try:
            plt.setp(self.waveform_line, xdata=[], ydata=[])
            self.wf_canvas.draw()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Multi-sequence tab widget
# ---------------------------------------------------------------------------

class SequenceTabWidget(QtWidgets.QTabWidget):
    """QTabWidget holding one TableWidget per pulse sequence.

    A permanent "+" tab at the end lets the user add new sequences. Tabs are
    closable, but at least one sequence is always kept. Each tab shows a small
    colored icon that matches its corresponding plot line.
    """

    sequences_changed = QtCore.Signal(list)  # list of (xs, ys) tuples, one per sequence

    def __init__(self, parent=None):
        super().__init__(parent)

        self._plus_tab_added = False
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self._on_close_tab)
        self.currentChanged.connect(self._on_current_changed)

        self._add_sequence_tab()  # initial sequence
        self._append_plus_tab()   # "+" tab at the end

    # ------------------------------------------------------------------
    # Internal structure helpers
    # ------------------------------------------------------------------

    def _sequence_count(self):
        """Number of sequence tabs, excluding the "+" tab."""
        return self.count() - 1

    def _append_plus_tab(self):
        self.addTab(QtWidgets.QWidget(), "+")
        self._plus_tab_added = True
        self._hide_plus_close_button()

    def _hide_plus_close_button(self):
        """Remove the close button from the "+" tab after any structural change."""
        plus_idx = self.count() - 1
        self.tabBar().setTabButton(plus_idx, QtWidgets.QTabBar.RightSide, None)
        self.tabBar().setTabButton(plus_idx, QtWidgets.QTabBar.LeftSide, None)

    def _add_sequence_tab(self):
        """Insert a new sequence tab before the "+" tab and switch to it."""
        seq_idx = self._sequence_count()
        table = TableWidget()
        table.data_changed.connect(self._on_any_data_changed)

        insert_pos = self.count() - 1 if self._plus_tab_added else self.count()

        # Block currentChanged so inserting/switching doesn't trigger _on_current_changed
        self.blockSignals(True)
        self.insertTab(insert_pos, table, "Sequence %d" % (seq_idx + 1))
        self.setTabIcon(insert_pos, _color_icon(_sequence_color(seq_idx)))
        self.setCurrentIndex(insert_pos)
        self.blockSignals(False)

        self._hide_plus_close_button()

    def _reindex_tabs(self):
        """Rename tabs and refresh icons after a sequence is removed."""
        for i in range(self._sequence_count()):
            self.setTabText(i, "Sequence %d" % (i + 1))
            self.setTabIcon(i, _color_icon(_sequence_color(i)))

    def _get_all_sequences(self):
        return [self.widget(i).get_pulse_data() for i in range(self._sequence_count())]

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_current_changed(self, index):
        """Clicking the "+" tab creates a new sequence instead of staying on it."""
        if self._plus_tab_added and index == self.count() - 1:
            self._add_sequence_tab()
            self.sequences_changed.emit(self._get_all_sequences())

    def _on_close_tab(self, index):
        if self._sequence_count() <= 1:
            return  # always keep at least one sequence

        self.blockSignals(True)
        self.removeTab(index)
        self._reindex_tabs()
        # Ensure the "+" tab is not left as the active tab
        if self.currentIndex() == self.count() - 1:
            self.setCurrentIndex(self.count() - 2)
        self.blockSignals(False)

        self._hide_plus_close_button()
        self.sequences_changed.emit(self._get_all_sequences())

    def _on_any_data_changed(self):
        self.sequences_changed.emit(self._get_all_sequences())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all_sequences(self):
        """Return [(timestamps, voltages), ...] for all sequences."""
        return self._get_all_sequences()


# ---------------------------------------------------------------------------
# Editable table widget — one per sequence
# ---------------------------------------------------------------------------

class TableWidget(QtWidgets.QWidget):
    """Two-column editable table: Time in s | Voltage in V.

    Always keeps one empty trailing row for new input. Emits data_changed
    with the current valid (time, voltage) pairs whenever any edit occurs.
    Invalid cells are highlighted in red without overwriting the user's text.
    """

    data_changed = QtCore.Signal(list, list)

    _COLOR_INVALID = QtGui.QColor(255, 180, 180)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- table ---
        self.table = QtWidgets.QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Time in s", "Voltage in V"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        # --- row management buttons ---
        btn_bar = QtWidgets.QHBoxLayout()
        self.btn_insert = QtWidgets.QPushButton("Insert Above")
        self.btn_delete = QtWidgets.QPushButton("Delete Row")
        self.btn_clear  = QtWidgets.QPushButton("Clear All")
        btn_bar.addWidget(self.btn_insert)
        btn_bar.addWidget(self.btn_delete)
        btn_bar.addWidget(self.btn_clear)
        layout.addLayout(btn_bar)

        # --- connections ---
        self._block_cell_signals = False
        self.table.cellChanged.connect(self._on_cell_changed)
        self.btn_insert.clicked.connect(self._on_insert_above)
        self.btn_delete.clicked.connect(self._on_delete_rows)
        self.btn_clear.clicked.connect(self.clear_data)

        self._add_empty_rows(10)

    # ------------------------------------------------------------------
    # Row management
    # ------------------------------------------------------------------

    def _on_insert_above(self):
        """Insert a blank row above the currently selected row."""
        indexes = self.table.selectedIndexes()
        row = self.table.currentRow() if indexes else max(0, self.table.rowCount() - 1)
        self._block_cell_signals = True
        self.table.insertRow(row)
        self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(''))
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(''))
        self._block_cell_signals = False

    def _on_delete_rows(self):
        """Delete all currently selected rows."""
        rows = sorted(
            {idx.row() for idx in self.table.selectedIndexes()},
            reverse=True
        )
        if not rows:
            return
        self._block_cell_signals = True
        for r in rows:
            self.table.removeRow(r)
        self._block_cell_signals = False
        self._ensure_trailing_empty_row()
        self._emit_data_changed()

    # ------------------------------------------------------------------
    # Empty-row management
    # ------------------------------------------------------------------

    def _add_empty_rows(self, n=10):
        """Append n blank rows without triggering cell-changed signals."""
        self._block_cell_signals = True
        for _ in range(n):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(''))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(''))
        self._block_cell_signals = False

    def _row_is_empty(self, r):
        it0, it1 = self.table.item(r, 0), self.table.item(r, 1)
        return (
            (it0 is None or it0.text().strip() == '') and
            (it1 is None or it1.text().strip() == '')
        )

    def _ensure_trailing_empty_row(self):
        rows = self.table.rowCount()
        if rows == 0 or not self._row_is_empty(rows - 1):
            self._block_cell_signals = True
            self.table.insertRow(rows)
            self.table.setItem(rows, 0, QtWidgets.QTableWidgetItem(''))
            self.table.setItem(rows, 1, QtWidgets.QTableWidgetItem(''))
            self._block_cell_signals = False

    # ------------------------------------------------------------------
    # Programmatic row insertion
    # ------------------------------------------------------------------

    def add_row(self, timestamp, voltage):
        try:
            tsf, vf = float(timestamp), float(voltage)
        except Exception:
            return

        self._block_cell_signals = True
        rows = self.table.rowCount()
        placed = False
        for r in range(rows):
            if self._row_is_empty(r):
                self.table.setItem(r, 0, QtWidgets.QTableWidgetItem("%1.6g" % tsf))
                self.table.setItem(r, 1, QtWidgets.QTableWidgetItem("%1.6g" % vf))
                placed = True
                break
        if not placed:
            self.table.insertRow(rows)
            self.table.setItem(rows, 0, QtWidgets.QTableWidgetItem("%1.6g" % tsf))
            self.table.setItem(rows, 1, QtWidgets.QTableWidgetItem("%1.6g" % vf))
        self._block_cell_signals = False

        self._ensure_trailing_empty_row()
        self.table.scrollToBottom()
        self._emit_data_changed()

    # ------------------------------------------------------------------
    # Cell editing
    # ------------------------------------------------------------------

    def _on_cell_changed(self, row, column):
        if self._block_cell_signals:
            return

        self._block_cell_signals = True
        item = self.table.item(row, column)
        if item is not None:
            text = item.text().strip()
            if text:
                try:
                    item.setText("%1.6g" % float(text))
                    item.setBackground(QtGui.QBrush())      # reset to default
                except ValueError:
                    item.setBackground(self._COLOR_INVALID) # flag invalid input
            else:
                item.setBackground(QtGui.QBrush())
        self._block_cell_signals = False

        self._ensure_trailing_empty_row()
        self._emit_data_changed()

    def _emit_data_changed(self):
        xs, ys = [], []
        for r in range(self.table.rowCount()):
            try:
                t = self.table.item(r, 0)
                v = self.table.item(r, 1)
                if t is None or v is None:
                    continue
                ttxt, vtxt = t.text().strip(), v.text().strip()
                if not ttxt or not vtxt:
                    continue
                x = float(ttxt)
                y = float(vtxt)
            except Exception:
                continue
            xs.append(x)
            ys.append(y)
        self.data_changed.emit(xs, ys)

    def get_pulse_data(self):
        """Return (timestamps, voltages) as two lists of floats for all valid rows."""
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

    def clear_data(self):
        self.table.setRowCount(0)
        self._add_empty_rows(10)
        self._emit_data_changed()


# ---------------------------------------------------------------------------
# Waveform table widget
# ---------------------------------------------------------------------------

class WaveformTableWidget(QtWidgets.QWidget):
    """Two-column table defining the waveform playback order.

    Each row specifies a sequence ID (1-based, matching a sequence tab) and
    the number of times that sequence should be repeated. Rows are played in
    order to build the combined waveform.

    Invalid entries (non-positive integers, out-of-range sequence IDs) are
    highlighted in red and excluded from the emitted waveform data.
    """

    waveform_changed = QtCore.Signal(list)  # list of (seq_id: int, reps: int)

    _COLOR_INVALID = QtGui.QColor(255, 180, 180)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._n_sequences = 0  # updated externally via update_sequence_count()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = QtWidgets.QLabel("Waveform")
        label.setStyleSheet("font-weight: bold; padding: 2px 0px;")
        layout.addWidget(label)

        # --- table ---
        self.table = QtWidgets.QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Sequence", "Repetitions"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        # --- row management buttons ---
        btn_bar = QtWidgets.QHBoxLayout()
        self.btn_insert = QtWidgets.QPushButton("Insert Above")
        self.btn_delete = QtWidgets.QPushButton("Delete Row")
        self.btn_clear  = QtWidgets.QPushButton("Clear All")
        btn_bar.addWidget(self.btn_insert)
        btn_bar.addWidget(self.btn_delete)
        btn_bar.addWidget(self.btn_clear)
        layout.addLayout(btn_bar)

        # --- connections ---
        self._block_cell_signals = False
        self.table.cellChanged.connect(self._on_cell_changed)
        self.btn_insert.clicked.connect(self._on_insert_above)
        self.btn_delete.clicked.connect(self._on_delete_rows)
        self.btn_clear.clicked.connect(self.clear_data)

        self._add_empty_rows(10)

    # ------------------------------------------------------------------
    # Sequence count update — called from Widget when sequences change
    # ------------------------------------------------------------------

    def update_sequence_count(self, n):
        """Update the valid range for sequence IDs and re-validate column 0."""
        self._n_sequences = n
        self._block_cell_signals = True
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item is None:
                continue
            text = item.text().strip()
            if not text:
                item.setBackground(QtGui.QBrush())
                continue
            try:
                val = int(text)
                if 1 <= val <= n:
                    item.setBackground(QtGui.QBrush())
                else:
                    item.setBackground(self._COLOR_INVALID)
            except ValueError:
                item.setBackground(self._COLOR_INVALID)
        self._block_cell_signals = False
        self._emit_waveform_changed()

    # ------------------------------------------------------------------
    # Row management
    # ------------------------------------------------------------------

    def _on_insert_above(self):
        indexes = self.table.selectedIndexes()
        row = self.table.currentRow() if indexes else max(0, self.table.rowCount() - 1)
        self._block_cell_signals = True
        self.table.insertRow(row)
        self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(''))
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(''))
        self._block_cell_signals = False

    def _on_delete_rows(self):
        rows = sorted(
            {idx.row() for idx in self.table.selectedIndexes()},
            reverse=True
        )
        if not rows:
            return
        self._block_cell_signals = True
        for r in rows:
            self.table.removeRow(r)
        self._block_cell_signals = False
        self._ensure_trailing_empty_row()
        self._emit_waveform_changed()

    # ------------------------------------------------------------------
    # Empty-row management
    # ------------------------------------------------------------------

    def _add_empty_rows(self, n=10):
        self._block_cell_signals = True
        for _ in range(n):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(''))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(''))
        self._block_cell_signals = False

    def _row_is_empty(self, r):
        it0, it1 = self.table.item(r, 0), self.table.item(r, 1)
        return (
            (it0 is None or it0.text().strip() == '') and
            (it1 is None or it1.text().strip() == '')
        )

    def _ensure_trailing_empty_row(self):
        rows = self.table.rowCount()
        if rows == 0 or not self._row_is_empty(rows - 1):
            self._block_cell_signals = True
            self.table.insertRow(rows)
            self.table.setItem(rows, 0, QtWidgets.QTableWidgetItem(''))
            self.table.setItem(rows, 1, QtWidgets.QTableWidgetItem(''))
            self._block_cell_signals = False

    # ------------------------------------------------------------------
    # Cell editing — integers only
    # ------------------------------------------------------------------

    def _on_cell_changed(self, row, column):
        if self._block_cell_signals:
            return

        self._block_cell_signals = True
        item = self.table.item(row, column)
        if item is not None:
            text = item.text().strip()
            if text:
                try:
                    val = int(text)
                    if column == 0:  # Sequence ID: must be in [1..N]
                        valid = (1 <= val <= self._n_sequences) if self._n_sequences > 0 else (val >= 1)
                    else:            # Repetitions: must be >= 1
                        valid = val >= 1
                    if valid:
                        item.setText("%d" % val)
                        item.setBackground(QtGui.QBrush())
                    else:
                        item.setBackground(self._COLOR_INVALID)
                except ValueError:
                    item.setBackground(self._COLOR_INVALID)
            else:
                item.setBackground(QtGui.QBrush())
        self._block_cell_signals = False

        self._ensure_trailing_empty_row()
        self._emit_waveform_changed()

    def _emit_waveform_changed(self):
        entries = []
        for r in range(self.table.rowCount()):
            try:
                t = self.table.item(r, 0)
                v = self.table.item(r, 1)
                if t is None or v is None:
                    continue
                ttxt, vtxt = t.text().strip(), v.text().strip()
                if not ttxt or not vtxt:
                    continue
                seq_id = int(ttxt)
                reps   = int(vtxt)
                if seq_id < 1 or reps < 1:
                    continue
                if self._n_sequences > 0 and seq_id > self._n_sequences:
                    continue
            except Exception:
                continue
            entries.append((seq_id, reps))
        self.waveform_changed.emit(entries)

    def get_waveform_data(self):
        """Return list of (seq_id, reps) for all valid rows."""
        entries = []
        for r in range(self.table.rowCount()):
            try:
                t = self.table.item(r, 0)
                v = self.table.item(r, 1)
                seq_id = int(t.text().strip())
                reps   = int(v.text().strip())
                if seq_id < 1 or reps < 1:
                    continue
                if self._n_sequences > 0 and seq_id > self._n_sequences:
                    continue
            except Exception:
                continue
            entries.append((seq_id, reps))
        return entries

    def clear_data(self):
        self.table.setRowCount(0)
        self._add_empty_rows(10)
        self._emit_waveform_changed()


# ---------------------------------------------------------------------------
# Matplotlib canvas helpers
# ---------------------------------------------------------------------------

class NavigationToolbar(NavigationToolbar2QT):

    toolitems = [t for t in NavigationToolbar2QT.toolitems
                 if t[0] in ('Home', 'Pan', 'Zoom', 'Save')]

    def __init__(self, canvas, widget, coordinates):
        super().__init__(canvas, widget, coordinates)
        self.setVisible(False)


# FigureCanvasQTAgg is the standard matplotlib backend for embedding plots in Qt widgets.
# It uses the Agg (Anti-Grain Geometry) renderer to rasterize the figure into a pixel
# buffer that Qt then displays, which is the recommended approach for matplotlib-in-Qt.
class MyMplCanvas(FigureCanvas):

    def __init__(self, parent=None):
        self.fig = Figure()
        self.fig.patch.set_alpha(0.0)

        super().__init__(self.fig)
        self.setSizePolicy(
            QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                  QtWidgets.QSizePolicy.Expanding)
        )
        self.updateGeometry()
        self.setParent(parent)

        self.mpl_toolbar = NavigationToolbar(self.fig.canvas, self, coordinates=True)
        self.fig.tight_layout(pad=0.2)

    def enterEvent(self, event):
        self.mpl_toolbar.setVisible(True)
        self.mpl_toolbar.setMinimumWidth(100)
        self.mpl_toolbar.move(self.width() - self.mpl_toolbar.width(), 20)

    def leaveEvent(self, event):
        self.mpl_toolbar.setVisible(False)
