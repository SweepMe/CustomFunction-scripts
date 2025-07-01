# author:
# created at:
# company/institute:

from ErrorMessage import error
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
    variables = ["Dial value"]
    units = [""]

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
        
        self.widget.plot_widget.clear_data()
        
    def main(self, x = (), y = (), ):
        '''
        This example shows how to create a basic GUI widget. Please use open/modify to see the code and modify it to your needs.
        Press 'Reload' to make sure that your widget is renewed after you did a modification.
        '''
        
        
        # Use of a signal to transfer the values to from the Measurement thread to the GUI thread
        self.widget.renewValues.emit("%1.3g" % x[-1], "%1.3g" % y[-1])
        
        # Using a thread-safe function to retrieve the value of the dial
        dial_value = self.widget.get_dial_value()
        
        # here we update the plot with the new value
        self.widget.updateData.emit(datetime.datetime.now(), dial_value)        

        return dial_value


## the widget to be displayed
class Widget(QtWidgets.QWidget):

    renewValues = QtCore.Signal(str, str)
    updateData = QtCore.Signal(object, float)

    def __init__(self):
        
        super().__init__()
    
        layout = self.create_MainLayout()
        
        self.setLayout(layout)
        
        # here, the custom signal is linked
        self.renewValues.connect(self.renew_values)
        self.updateData.connect(self.plot_widget.update_data)
        
        self._dial_value = self.dial.value()
        
        
    def create_MainLayout(self):
        """ returns a main layout that includes all widgets to be shown"""
        
        grid = QtWidgets.QGridLayout()
        
        lbl = QtWidgets.QLabel("x:")
        lbl.setFont(QtGui.QFont("Open Sans", 30, QtGui.QFont.Bold))
        grid.addWidget(lbl, 0, 0)
        self.lbl_value1 = QtWidgets.QLabel("1.0")
        self.lbl_value1.setFont(QtGui.QFont("Open Sans", 30, QtGui.QFont.Bold))
        grid.addWidget(self.lbl_value1, 0, 1)
        
        lbl = QtWidgets.QLabel("y:")
        lbl.setFont(QtGui.QFont("Open Sans", 30, QtGui.QFont.Bold))
        grid.addWidget(lbl, 1, 0)
        self.lbl_value2 = QtWidgets.QLabel("1.0")
        self.lbl_value2.setFont(QtGui.QFont("Open Sans", 30, QtGui.QFont.Bold))
        grid.addWidget(self.lbl_value2, 1, 1)
        
        lbl = QtWidgets.QLabel("Dial:")
        lbl.setFont(QtGui.QFont("Open Sans", 30, QtGui.QFont.Bold))
        grid.addWidget(lbl, 2, 0)
        self.lbl_value3 = QtWidgets.QLabel("1.0")
        self.lbl_value3.setFont(QtGui.QFont("Open Sans", 30, QtGui.QFont.Bold))
        grid.addWidget(self.lbl_value3, 2, 1)
        
        self.dial =  QtWidgets.QDial()
        self.dial.valueChanged[int].connect(self.update_dial_value)
        grid.addWidget(self.dial, 0, 2, 3, 1)
        
        self.lbl_value3.setText(str(self.dial.value()))
        
        self.plot_widget = PlotWidget(self)
        grid.addWidget(self.plot_widget, 3, 0, 1, 3)
    
        return grid
    
    def set_value1(self, value):
        
        self.lbl_value1.setText(str(value))
        
    def set_value2(self, value):
        
        self.lbl_value2.setText(str(value))
        
    def renew_values(self, val1, val2):

        self.lbl_value1.setText(str(val1))
        self.lbl_value2.setText(str(val2))
                        
    def update_dial_value(self, val):
        self.lbl_value3.setText(str(val))
        self._dial_value = val
        
    def get_dial_value(self):
        return self._dial_value
        


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
        
        self.plotCanvas.axes = self.plotCanvas.fig.add_subplot(111)
        self.plotCanvas.axes.set_title("Plot")
        self.plotCanvas.axes.set_xlabel("Time")
        self.plotCanvas.axes.set_ylabel("Dial value")
        
        self.line = self.plotCanvas.axes.plot([],[], linewidth = 1, marker = 'o', markersize = 1)
       
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
    
        self.x.append(x)
        self.y.append(float(y))
        
        self.plotCanvas.axes.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        self.plotCanvas.fig.autofmt_xdate()
    
        
        plt.setp(self.line, xdata = self.x, ydata = self.y)
                
        try:
            self.plotCanvas.axes.relim()
            self.plotCanvas.axes.autoscale_view()
            
            self.plotCanvas.fig.tight_layout(pad=0.2, w_pad=0.1, h_pad=0.1)
            self.plotCanvas.draw()
        except:
            error()
            
    def clear_data(self):
    
        self.x, self.y = [],[]
    


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
        


       