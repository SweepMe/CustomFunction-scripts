# author: Franz Hempel
# created at: 2026-05-27
# company/institute: SweepMe! GmbH

"""CustomFunction example: embed a QML widget into the SweepMe! Dashboard.

The widget itself is declared in hello.qml (Qt Quick) and rendered through
PySide6's QQuickWidget. The Python side increments a counter on each call and
pushes it into the QML root object via a thread-safe Qt signal.

QML is useful for SVG-heavy panels and HMI-style controls. Note that QSS does
not style QML — they live in separate rendering stacks.
"""

from pathlib import Path

from PySide6 import QtCore, QtQuickWidgets


class Main:

    variables = ["Counter"]
    units = [""]

    def __init__(self):
        self.counter = 0
        self.widget = None

    def renew_widget(self, widget=None):
        # Called in the GUI thread, so it's safe to construct Qt objects here.
        if widget is None:
            widget = QmlWidget()
        self.widget = widget
        return self.widget

    def initialize(self):
        self.counter = 0
        if self.widget is not None:
            self.widget.counterChanged.emit(0)

    def main(self):
        self.counter += 1
        if self.widget is not None:
            # main() runs in the measurement thread — cross threads via signal.
            self.widget.counterChanged.emit(self.counter)
        return [self.counter]


class QmlWidget(QtQuickWidgets.QQuickWidget):

    counterChanged = QtCore.Signal(int)

    def __init__(self):
        super().__init__()

        qml_file = Path(__file__).parent / "hello.qml"
        self.setSource(QtCore.QUrl.fromLocalFile(str(qml_file)))
        self.setResizeMode(QtQuickWidgets.QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.setMinimumSize(420, 320)

        self.counterChanged.connect(self._on_counter_changed)

    def _on_counter_changed(self, value: int) -> None:
        root = self.rootObject()
        if root is not None:
            root.setProperty("counter", value)
