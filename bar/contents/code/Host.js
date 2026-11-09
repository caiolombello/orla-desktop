.pragma library

// Plasma series whose private QML bridges (session actions, Kicker's recent
// model, the tray watcher) were checked: 6.7 (6.7.5) and 6.8 (6.8.2). Any other
// series keeps the native adapters unloaded until it is checked too.
function supported(version) {
    return /^6\.[78]\.[0-9]+(?:[-+].*)?$/.test(String(version || ""));
}
