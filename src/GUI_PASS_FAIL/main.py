# author: Axel Fischer
# created at: November 2024
# company/institute: SweepMe! GmbH


from PySide2 import QtWidgets, QtCore


class Main():
    """
    <p>This script can be used to add a widget to the dashboard that either displays green PASS or a red FAIL as a signal<br />for a user whether a test was successful or not.<br /><br />Please use the Parameter syntax {...} to handover a value to the script.<br /><br />Supported data types for PASS are:</p>
    <ul>
    <li>Boolean: True</li>
    <li>String: "True", "Pass", "1" (case-insensitive)</li>
    <li>Integer: 1</li>
    </ul>
    <p><br />Supported data types for FAIL are:</p>
    <ul>
    <li>Boolean: False</li>
    <li>String: "False", "Fail", "0" (case-insensitive)</li>
    <li>Integer: 0<br /><br /></li>
    </ul>
    <p>All other parameters will raise an exception.</p>
    """

    # please define variables and units as returned by the function 'main'
    variables = []
    units = []
    
    arguments = {
        "State": "",
    }

    ## Attention: this function is called in the main GUI thread so that the widget is automatically
    ## created in the correct thread
    def renew_widget(self, widget = None):
        """ gets the widget from the module and returns the same widget or creates a new one"""
    
        if widget is None:
            # if the widget has not been created so far, we create it now and store it as self.widget
            self.widget = Widget()
        else:
            # the second time a run is started, we can use the widget that is handed over to 'renew_widget'
            # to store it as self.widget
            self.widget = widget
            
        # return the widget to inform the module which one has to be inserted Widget into the Dashboard
        return self.widget
        
    def initialize(self):
        
        self.widget.reset_signal.emit()
        
    def main(self, **kwargs):
    
        state = kwargs["State"]

        if isinstance(state, str):
            state = state.lower()

        if state in ["true", True, 1, "1", "pass"]:
            self.widget.pass_signal.emit()
        elif state in ["false", False, 0, "0", "fail"]:
            self.widget.fail_signal.emit()
        else:
            msg=f"State {state!r} cannot be interpreted as pass or fail."
            raise ValueError(msg)

        return None
     

class Widget(QtWidgets.QWidget):

    pass_signal = QtCore.Signal()
    fail_signal = QtCore.Signal()
    reset_signal = QtCore.Signal()
    toggle_signal = QtCore.Signal()

    def __init__(self):
    
        super().__init__()

        # Set up the main layout and label
        self.layout = QtWidgets.QVBoxLayout()
        self.label = QtWidgets.QLabel()
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)
        # self.layout.setContentsMargins(1, 1, 1, 1)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.pass_signal.connect(self.set_pass)
        self.fail_signal.connect(self.set_fail)
        self.reset_signal.connect(self.reset)
        self.toggle_signal.connect(self.toggle_state)

        # Initialize to start state
        self.reset()
        
    def reset(self):
        """Set the widget to Start state."""
        self.label.setText("PASS/FAIL")
        self.label.setStyleSheet("""
            QLabel {
                background-color: grey;
                color: darkgrey;
                font-size: 96px;
                font-weight: bold;
                padding: 2px;
                border-radius: 2px;
            }
        """)

    def set_pass(self):
        """Set the widget to PASS state."""
        self.label.setText("PASS")
        self.label.setStyleSheet("""
            QLabel {
                background-color: limegreen;
                color: white;
                font-size: 96px;
                font-weight: bold;
                padding: 2px;
                border-radius: 2px;
            }
        """)

    def set_fail(self):
        """Set the widget to FAIL state."""
        self.label.setText("FAIL")
        self.label.setStyleSheet("""
            QLabel {
                background-color: red;
                color: black;
                font-size: 96px;
                font-weight: bold;
                padding: 2px;
                border-radius: 2px;
            }
        """)

    def toggle_state(self):
        """Toggle between PASS and FAIL states."""
        if self.label.text() == "PASS":
            self.set_fail()
        else:
            self.set_pass()
