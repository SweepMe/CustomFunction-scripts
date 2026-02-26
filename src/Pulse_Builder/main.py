# author:
# created at:
# company/institute:

try:
    from ErrorMessage import error
except Exception:
    def error(*args, **kwargs):
        # fallback used when running outside SweepMe!
        print("ErrorMessage.error called", args, kwargs)

import os
import time
import datetime
from PySide2 import QtWidgets, QtGui, QtCore
import matplotlib.dates as mdates

# you can import any module that is shipped with SweepMe!, see credits.html
# Any other module must be put into the folder of your function and loaded by adding the path the python environment using the following two lines:
# from FolderManager import addFolderToPATH
# addFolderToPATH()

class Main():

    # please define variables and units as returned by the function 'main'
    variables = []
    units = []

    ## Attention: this function is called in the main GUI thread so that the widget is automatically
    ## created in the correct thread
    def renew_widget(self, widget = None):
        """ gets the widget from the module and returns the same widget or creates a new one"""
    
        if widget is None:
            # if the widget has not been created so far, we create it now and store it as self.widget
            self.widget = Widget()
        else:
            # the second time a run is started, we can use the widget that is handed over to 'renew_widget' to store it as self.widget
            self.widget = widget
            
        # return the actual widget to inform the module which one has to be inserted into the DockWidget of the Dashboard    
        return self.widget
        
    def initialize(self):
        
        # clear both plot and table when (re)initializing
        self.widget.plot_widget.clear_data()
        try:
            self.widget.table_widget.clear_data()
        except AttributeError:
            pass

    def main(self,):

        return


## the widget to be displayed
class Widget(QtWidgets.QWidget):

    renewValues = QtCore.Signal(str, str)
    updateData = QtCore.Signal(object, float)
    addTableEntry = QtCore.Signal(object, float)

    def __init__(self):

        super().__init__()

        layout = self.create_MainLayout()

        self.setLayout(layout)

        # link signals
        self.updateData.connect(self.plot_widget.update_data)
        self.addTableEntry.connect(self.table_widget.add_row)
        # update the plot whenever table content changes (add/edit/clear)
        self.table_widget.data_changed.connect(self.plot_widget.set_data)

    def create_MainLayout(self):
        """ returns a main layout that includes all widgets to be shown"""
        
        grid = QtWidgets.QGridLayout()
        
        # create a horizontal splitter to hold the plot and the table side-by-side
        self.plot_widget = PlotWidget(self)
        self.table_widget = TableWidget(self)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self.plot_widget)
        splitter.addWidget(self.table_widget)
        splitter.setSizes([700, 300])

        # place splitter at the top row so it's immediately visible even when the other label rows are not present
        grid.addWidget(splitter, 0, 0, 1, 3)

        return grid
    

from matplotlib import pyplot as plt

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT

from matplotlib.figure import Figure
from matplotlib import rcParams as mplParams


class PlotWidget(QtWidgets.QWidget):

    def __init__(self, parent = None):
    
        super(PlotWidget, self).__init__(parent)

        layout = self.create_MainLayout()
        
        self.setLayout(layout)
        
        # numeric x-axis in seconds
        self.plotCanvas.axes = self.plotCanvas.fig.add_subplot(111)
        self.plotCanvas.axes.set_title("Voltage over time")
        self.plotCanvas.axes.set_xlabel("Time (s)")
        self.plotCanvas.axes.set_ylabel("Voltage")

        # store a single Line2D object (unpack the list returned by plot)
        line_obj = self.plotCanvas.axes.plot([], [], linewidth = 1, marker = 'o', markersize = 3)
        # plot(...) returns a list of Line2D; keep the first
        self.line = line_obj[0]

        self.plotCanvas.draw()
        
        self.x, self.y = [],[]
        

    def create_MainLayout(self):

        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setSizePolicy(sizePolicy)
        self.gridLayout = QtWidgets.QGridLayout(self)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setVerticalSpacing(0)
        self.frame = QtWidgets.QFrame(self)
        self.frame.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame.sizePolicy().hasHeightForWidth())
        self.frame.setSizePolicy(sizePolicy)
        self.frame.setSizeIncrement(QtCore.QSize(0, 0))
        self.gridLayout.addWidget(self.frame, 0, 0, 1, 1)
        
        self.layout = QtWidgets.QVBoxLayout(self.frame)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0,0,0,0)
        
        self.plotCanvas = MyMplCanvas(self.frame)
        self.layout.addWidget(self.plotCanvas)
        
        
    def update_data(self, x, y):
    
        # x is expected to be numeric seconds, y is numeric (voltage)
        try:
            xn = float(x)
        except Exception:
            # invalid x, ignore the update
            return
        try:
            yn = float(y)
        except Exception:
            return

        self.x.append(xn)
        self.y.append(yn)

        plt.setp(self.line, xdata = self.x, ydata = self.y)
                
        try:
            self.plotCanvas.axes.relim()
            self.plotCanvas.axes.autoscale_view()
            
            self.plotCanvas.fig.tight_layout(pad=0.2, w_pad=0.1, h_pad=0.1)
            self.plotCanvas.draw()
        except:
            error()

    def set_data(self, x_list, y_list):
        """Replace the full dataset shown in the plot (x_list, y_list are iterables of numbers)."""
        try:
            xs = [float(v) for v in x_list]
            ys = [float(v) for v in y_list]
        except Exception:
            # if conversion fails, do nothing
            return
        self.x = xs
        self.y = ys
        try:
            plt.setp(self.line, xdata = self.x, ydata = self.y)
            self.plotCanvas.axes.relim()
            self.plotCanvas.axes.autoscale_view()
            self.plotCanvas.fig.tight_layout(pad=0.2, w_pad=0.1, h_pad=0.1)
            self.plotCanvas.draw()
        except Exception:
            error()

    def clear_data(self):
    
        self.x, self.y = [],[]
        try:
            # also clear the plotted line data
            plt.setp(self.line, xdata = [], ydata = [])
            self.plotCanvas.draw()
        except Exception:
            pass



class TableWidget(QtWidgets.QWidget):
    """Simple two-column table: Timestamp (seconds) | Voltage

    The table is editable. Always keep one empty trailing row for user input.
    Programmatic add_row fills the first empty row. Any change emits data_changed(xs, ys)
    where xs/ys only include rows with valid numeric entries.
    """
    data_changed = QtCore.Signal(list, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)

        self.table = QtWidgets.QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Time (s)", "Voltage"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        # allow editing so the user can modify rows
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        # protect against recursive cellChanged signals
        self._block_cell_signals = False

        # react to edits in the table
        self.table.cellChanged.connect(self._on_cell_changed)

        # ensure we have one empty row for the user to type into
        self._ensure_trailing_empty_row()

    def _row_is_empty(self, r):
        it0 = self.table.item(r, 0)
        it1 = self.table.item(r, 1)
        empty0 = (it0 is None) or (it0.text().strip() == '')
        empty1 = (it1 is None) or (it1.text().strip() == '')
        return empty0 and empty1

    def _ensure_trailing_empty_row(self):
        rows = self.table.rowCount()
        if rows == 0:
            self._block_cell_signals = True
            self.table.insertRow(0)
            self.table.setItem(0, 0, QtWidgets.QTableWidgetItem(''))
            self.table.setItem(0, 1, QtWidgets.QTableWidgetItem(''))
            self._block_cell_signals = False
            return
        # if last row is not empty, append an empty row
        if not self._row_is_empty(rows - 1):
            self._block_cell_signals = True
            self.table.insertRow(rows)
            self.table.setItem(rows, 0, QtWidgets.QTableWidgetItem(''))
            self.table.setItem(rows, 1, QtWidgets.QTableWidgetItem(''))
            self._block_cell_signals = False

    def add_row(self, timestamp, voltage):
        # ensure numeric conversion
        try:
            tsf = float(timestamp)
            vf = float(voltage)
        except Exception:
            return

        self._block_cell_signals = True
        # try to fill the first empty row
        rows = self.table.rowCount()
        filled = False
        for r in range(rows):
            if self._row_is_empty(r):
                self.table.setItem(r, 0, QtWidgets.QTableWidgetItem("%1.6g" % tsf))
                self.table.setItem(r, 1, QtWidgets.QTableWidgetItem("%1.6g" % vf))
                filled = True
                break
        if not filled:
            r = rows
            self.table.insertRow(r)
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem("%1.6g" % tsf))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem("%1.6g" % vf))
        self._block_cell_signals = False

        # ensure an empty trailing row exists and emit updated data
        self._ensure_trailing_empty_row()
        self.table.scrollToBottom()
        self._emit_data_changed()

    def _on_cell_changed(self, row, column):
        # ignore events triggered while we modify the table programmatically
        if self._block_cell_signals:
            return
        # validate and reformat the edited cell if possible
        try:
            item0 = self.table.item(row, 0)
            item1 = self.table.item(row, 1)
            if item0 is not None and item0.text().strip() != '':
                try:
                    t = float(item0.text())
                    item0.setText("%1.6g" % t)
                except Exception:
                    # invalid -> set to 0.0
                    item0.setText("0.0")
            # if empty, leave it as empty (user may still be typing)
            if item1 is not None and item1.text().strip() != '':
                try:
                    v = float(item1.text())
                    item1.setText("%1.6g" % v)
                except Exception:
                    item1.setText("0.0")
        except Exception:
            pass

        # after validation, ensure trailing empty row and emit full data set
        self._ensure_trailing_empty_row()
        self._emit_data_changed()

    def _emit_data_changed(self):
        xs = []
        ys = []
        rows = self.table.rowCount()
        for r in range(rows):
            try:
                it0 = self.table.item(r, 0)
                it1 = self.table.item(r, 1)
                if it0 is None or it1 is None:
                    continue
                ttxt = it0.text().strip()
                vtxt = it1.text().strip()
                if ttxt == '' or vtxt == '':
                    # skip incomplete rows (including the trailing empty row)
                    continue
                xs.append(float(ttxt))
                ys.append(float(vtxt))
            except Exception:
                # skip malformed rows
                continue
        self.data_changed.emit(xs, ys)

    def clear_data(self):
        self.table.setRowCount(0)
        self._ensure_trailing_empty_row()
        self._emit_data_changed()


class NavigationToolbar(NavigationToolbar2QT):

    # only display the buttons we need
    toolitems = [t for t in NavigationToolbar2QT.toolitems if
                 t[0] in ('Home', 'Pan', 'Zoom', 'Save')] # 'Subplots'
                 
    def __init__(self, canvas, widget, coordinates):
        super(__class__, self).__init__(canvas, widget, coordinates)
        self.setVisible(False)
                 
                 
class MyMplCanvas(FigureCanvas):

    # this class creates a matplotlib-plot on a canvas as a widget
    def __init__(self, parent=None):

        self.fig = Figure()
        self.fig.patch.set_alpha(0.0)
        
        FigureCanvas.__init__(self, self.fig)
        FigureCanvas.setSizePolicy(self, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        FigureCanvas.updateGeometry(self)
        
        self.setParent(parent)
        
        self.mpl_toolbar = NavigationToolbar(self.fig.canvas, self, coordinates=True)
                
        self.fig.tight_layout(pad=0.2, w_pad=0.1, h_pad=0.1)
                

    def enterEvent(self, event):
        self.mpl_toolbar.setVisible(True)
        self.mpl_toolbar.setMinimumWidth(100)
        self.mpl_toolbar.move(self.width()-self.mpl_toolbar.width(),20)

    def leaveEvent(self, event):
        self.mpl_toolbar.setVisible(False)
