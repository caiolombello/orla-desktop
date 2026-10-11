.pragma library

function remaining(deadline, now) {
    return Math.max(0, Math.ceil((deadline - now) / 1000));
}

function duration(seconds) {
    const value = Math.max(0, Math.floor(seconds));
    return Math.floor(value / 60).toString().padStart(2, "0")
        + ":" + (value % 60).toString().padStart(2, "0");
}

function launcherUrl(input) {
    const value = input.trim();
    if (/^applications:[A-Za-z0-9_.-]+\.desktop$/.test(value)) return value;
    if (/^[A-Za-z0-9_.-]+\.desktop$/.test(value)) return "applications:" + value;
    if (/^file:\/\/\/[^\r\n]+\.desktop$/.test(value)) return value;
    return "";
}
