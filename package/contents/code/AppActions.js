.pragma library

// App-wide dock actions (Ocultar, Encerrar, Mostrar todas as janelas, Mover).
// Rows are plain snapshots of TasksModel rows:
// {index, appId, isWindow, minimized, minimizable, closable, winIds, desktops,
// allDesktops, desktopsChangeable}.

function sameIds(left, right) {
    return JSON.stringify((left || []).map(String)) === JSON.stringify((right || []).map(String));
}

// The dock runs ungrouped, so one app may own several rows. Without an AppId
// only the window the menu was opened on counts as "the app".
function appWindows(rows, appId, winIds) {
    const id = String(appId || "");
    return (rows || []).filter(row => row && row.isWindow
        && (id ? row.appId === id : sameIds(row.winIds, winIds)));
}

function hideTargets(windows) {
    return (windows || []).filter(window => window.minimizable && !window.minimized);
}

function closeTargets(windows) {
    return (windows || []).filter(window => window.closable);
}

function windowHandles(windows) {
    const handles = [];
    for (const window of windows || [])
        for (const id of window.winIds || []) {
            const handle = String(id);
            if (handle.length && handles.indexOf(handle) === -1) handles.push(handle);
        }
    return handles;
}

function onlyOn(window, desktopId) {
    return !window.allDesktops && (window.desktops || []).length === 1 && String(window.desktops[0]) === desktopId;
}

function movable(windows) {
    return (windows || []).filter(window => window.desktopsChangeable !== false);
}

// One choice per desktop, numbered from 1; none when there is a single desktop
// or KWin refuses to move every window of the app.
function desktopChoices(desktopIds, desktopNames, windows) {
    const ids = Array.from(desktopIds || []).map(String);
    const names = Array.from(desktopNames || []).map(String);
    windows = movable(windows);
    if (ids.length < 2 || !windows.length) return [];
    return ids.map((id, position) => ({ id: id, number: position + 1, name: names[position] || "",
        current: windows.every(window => onlyOn(window, id)) }));
}

function moveTargets(windows, desktopId) {
    return movable(windows).filter(window => !onlyOn(window, String(desktopId)));
}

function summary(windows, desktopIds, desktopNames) {
    return { count: (windows || []).length, hideable: hideTargets(windows).length,
        closable: closeTargets(windows).length, handles: windowHandles(windows).length,
        desktops: desktopChoices(desktopIds, desktopNames, windows) };
}
