import QtQuick
import "../code/Logic.js" as Logic

QtObject {
    id: timer
    required property var configuration
    property double now: Date.now()
    readonly property bool running: configuration.timerDeadline > 0
    readonly property int phaseSeconds: (configuration.timerBreak ? configuration.breakMinutes : configuration.focusMinutes) * 60
    readonly property int secondsLeft: running ? Logic.remaining(configuration.timerDeadline, now) : configuration.timerRemaining
    signal finished()
    function toggle() {
        now = Date.now();
        if (running) {
            configuration.timerRemaining = Logic.remaining(configuration.timerDeadline, now);
            configuration.timerDeadline = 0;
        } else {
            configuration.timerDeadline = now + Math.max(1, configuration.timerRemaining) * 1000;
        }
    }
    function reset() {
        configuration.timerDeadline = 0;
        configuration.timerBreak = false;
        configuration.timerRemaining = configuration.focusMinutes * 60;
    }
    function poll(timestamp) {
        now = timestamp;
        if (running && secondsLeft === 0) {
            if (!configuration.timerBreak) configuration.completedFocus += 1;
            configuration.timerDeadline = 0;
            configuration.timerBreak = !configuration.timerBreak;
            configuration.timerRemaining = phaseSeconds;
            finished();
        }
    }
    property Timer ticker: Timer {
        interval: 500
        repeat: true
        running: true
        onTriggered: timer.poll(Date.now())
    }
}
