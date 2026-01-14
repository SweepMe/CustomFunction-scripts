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
        "PASS message": "PASS",
        "FAIL message": "FAIL",
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
        pass_message = kwargs.get("PASS message", "PASS")
        fail_message = kwargs.get("FAIL message", "FAIL")

        if isinstance(state, str):
            state = state.lower()

        if state in ["true", True, 1, "1", "pass"]:
            self.widget.pass_signal.emit(pass_message)
        elif state in ["false", False, 0, "0", "fail"]:
            self.widget.fail_signal.emit(fail_message)
        else:
            msg=f"State {state!r} cannot be interpreted as pass or fail."
            raise ValueError(msg)

        return None
     

class Widget(QtWidgets.QWidget):

    pass_signal = QtCore.Signal(str)
    fail_signal = QtCore.Signal(str)
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

        self.fail_message: str = "FAIL"
        self.pass_message: str = "PASS"

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

    def set_pass(self, message: str = "PASS"):
        """Set the widget to PASS state."""
        self.pass_message = message
        self.label.setText(message)
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

    def set_fail(self, message: str = "FAIL"):
        """Set the widget to FAIL state."""
        self.fail_message = message
        self.label.setText(message)
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
        if self.label.text() == self.pass_message:
            self.set_fail(self.fail_message)
        else:
            self.set_pass(self.pass_message)
