# author:
# created at:
# company/institute:

from pysweepme.ErrorMessage import error

from PySide2 import QtWidgets, QtGui, QtCore
from matplotlib import pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT
from matplotlib.figure import Figure


# Shared color cycle — used by both SegmentTabWidget (tab icons) and PlotWidget (lines)
# so that each segment's tab icon always matches its plot line color.
COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
]

def _segment_color(index):
    return COLORS[index % len(COLORS)]

def _color_icon(color_str):
    """Small filled square icon used to link a tab visually to its plot line."""
    pixmap = QtGui.QPixmap(12, 12)
    pixmap.fill(QtGui.QColor(color_str))
    return QtGui.QIcon(pixmap)


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

        self.setLayout(self._create_layout())

        # Live plot updates whenever any segment's table data changes
        self.segment_tabs.segments_changed.connect(self.plot_widget.set_segments)

    def _create_layout(self):
        self.plot_widget = PlotWidget(self)
        self.segment_tabs = SegmentTabWidget(self)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self.plot_widget)
        splitter.addWidget(self.segment_tabs)
        splitter.setSizes([700, 300])

        grid = QtWidgets.QGridLayout()
        grid.addWidget(splitter, 0, 0)
        return grid


# ---------------------------------------------------------------------------
# Matplotlib plot widget
# ---------------------------------------------------------------------------

class PlotWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setSizePolicy(
            QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                  QtWidgets.QSizePolicy.Expanding)
        )

        self.plotCanvas = MyMplCanvas(self)
        self.lines = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plotCanvas)

        ax = self.plotCanvas.fig.add_subplot(111)
        self.plotCanvas.axes = ax
        ax.set_title("Pulse Waveform")
        ax.set_xlabel("Time in s")
        ax.set_ylabel("Voltage in V")
        ax.grid(True, linestyle='--', alpha=0.5)

        self.plotCanvas.draw()

    def set_segments(self, segments):
        """Redraw all segment lines from scratch.

        segments: list of (xs, ys) tuples, one entry per segment tab.
        Lines are removed and recreated on every call so that colors always
        stay in sync with the tab order.
        """
        ax = self.plotCanvas.axes

        for line in self.lines:
            line.remove()
        self.lines = []

        for i, (xs, ys) in enumerate(segments):
            line, = ax.plot(
                xs, ys,
                linewidth=1.5, marker='o', markersize=4,
                color=_segment_color(i),
            )
            self.lines.append(line)

        try:
            ax.relim()
            ax.autoscale_view()
            self.plotCanvas.fig.tight_layout(pad=0.2)
            self.plotCanvas.draw()
        except Exception:
            error()

    def clear_data(self):
        ax = self.plotCanvas.axes
        for line in self.lines:
            line.remove()
        self.lines = []
        try:
            self.plotCanvas.draw()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Multi-segment tab widget
# ---------------------------------------------------------------------------

class SegmentTabWidget(QtWidgets.QTabWidget):
    """QTabWidget holding one TableWidget per pulse segment.

    A permanent "+" tab at the end lets the user add new segments. Tabs are
    closable, but at least one segment is always kept. Each tab shows a small
    colored icon that matches its corresponding plot line.
    """

    segments_changed = QtCore.Signal(list)  # list of (xs, ys) tuples, one per segment

    def __init__(self, parent=None):
        super().__init__(parent)

        self._plus_tab_added = False
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self._on_close_tab)
        self.currentChanged.connect(self._on_current_changed)

        self._add_segment_tab()  # initial segment
        self._append_plus_tab()  # "+" tab at the end

    # ------------------------------------------------------------------
    # Internal structure helpers
    # ------------------------------------------------------------------

    def _segment_count(self):
        """Number of segment tabs, excluding the "+" tab."""
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

    def _add_segment_tab(self):
        """Insert a new segment tab before the "+" tab and switch to it."""
        seg_idx = self._segment_count()
        table = TableWidget()
        table.data_changed.connect(self._on_any_data_changed)

        insert_pos = self.count() - 1 if self._plus_tab_added else self.count()

        # Block currentChanged so inserting/switching doesn't trigger _on_current_changed
        self.blockSignals(True)
        self.insertTab(insert_pos, table, "Segment %d" % (seg_idx + 1))
        self.setTabIcon(insert_pos, _color_icon(_segment_color(seg_idx)))
        self.setCurrentIndex(insert_pos)
        self.blockSignals(False)

        self._hide_plus_close_button()

    def _reindex_tabs(self):
        """Rename tabs and refresh icons after a segment is removed."""
        for i in range(self._segment_count()):
            self.setTabText(i, "Segment %d" % (i + 1))
            self.setTabIcon(i, _color_icon(_segment_color(i)))

    def _get_all_segments(self):
        return [self.widget(i).get_pulse_data() for i in range(self._segment_count())]

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_current_changed(self, index):
        """Clicking the "+" tab creates a new segment instead of staying on it."""
        if self._plus_tab_added and index == self.count() - 1:
            self._add_segment_tab()
            self.segments_changed.emit(self._get_all_segments())

    def _on_close_tab(self, index):
        if self._segment_count() <= 1:
            return  # always keep at least one segment

        self.blockSignals(True)
        self.removeTab(index)
        self._reindex_tabs()
        # Ensure the "+" tab is not left as the active tab
        if self.currentIndex() == self.count() - 1:
            self.setCurrentIndex(self.count() - 2)
        self.blockSignals(False)

        self._hide_plus_close_button()
        self.segments_changed.emit(self._get_all_segments())

    def _on_any_data_changed(self):
        self.segments_changed.emit(self._get_all_segments())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all_segments(self):
        """Return [(timestamps, voltages), ...] for all segments."""
        return self._get_all_segments()


# ---------------------------------------------------------------------------
# Editable table widget (one per segment)
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
        # If nothing is selected, insert just before the trailing empty row
        row = self.table.currentRow() if indexes else max(0, self.table.rowCount() - 1)
        self._block_cell_signals = True
        self.table.insertRow(row)
        self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(''))
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(''))
        self._block_cell_signals = False
        # No data change to emit — the inserted row is empty

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
    # Trailing empty-row management
    # ------------------------------------------------------------------

    def _row_is_empty(self, r):
        it0, it1 = self.table.item(r, 0), self.table.item(r, 1)
        return (
            (it0 is None or it0.text().strip() == '') and
            (it1 is None or it1.text().strip() == '')
        )

    def _add_empty_rows(self, n=10):
        """Append n blank rows without triggering cell-changed signals."""
        self._block_cell_signals = True
        for _ in range(n):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(''))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(''))
        self._block_cell_signals = False

    def _ensure_trailing_empty_row(self):
        rows = self.table.rowCount()
        if rows == 0 or not self._row_is_empty(rows - 1):
            self._block_cell_signals = True
            self.table.insertRow(rows)
            self.table.setItem(rows, 0, QtWidgets.QTableWidgetItem(''))
            self.table.setItem(rows, 1, QtWidgets.QTableWidgetItem(''))
            self._block_cell_signals = False

    # ------------------------------------------------------------------
    # Programmatic row insertion (used from measurement thread via signal)
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
