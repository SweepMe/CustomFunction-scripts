import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    width: 420
    height: 320
    color: "#1e1e2e"

    property int counter: 0

    Column {
        anchors.centerIn: parent
        spacing: 18

        Text {
            text: "Hello from QML!"
            color: "#cdd6f4"
            font.pixelSize: 28
            font.bold: true
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Image {
            width: 96
            height: 96
            anchors.horizontalCenter: parent.horizontalCenter
            source: "data:image/svg+xml;utf8," + encodeURIComponent(
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">' +
                '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
                '<stop offset="0%" stop-color="#89b4fa"/>' +
                '<stop offset="100%" stop-color="#cba6f7"/>' +
                '</linearGradient></defs>' +
                '<circle cx="48" cy="48" r="42" fill="url(#g)" stroke="#f5e0dc" stroke-width="3"/>' +
                '<text x="48" y="55" text-anchor="middle" fill="#1e1e2e" ' +
                'font-family="sans-serif" font-size="22" font-weight="bold">SVG</text>' +
                '</svg>'
            )
        }

        Text {
            text: "Counter: " + root.counter
            color: "#a6e3a1"
            font.pixelSize: 22
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Text {
            text: "Rendered by Qt Quick / QML"
            color: "#6c7086"
            font.pixelSize: 12
            font.italic: true
            anchors.horizontalCenter: parent.horizontalCenter
        }
    }
}
