.pragma library

// The bar's application menu (Ocultar, Ocultar outros, Mostrar tudo, Encerrar).
// Rows are plain snapshots of ungrouped TasksModel rows:
// {index, appId, isWindow, active, minimized, minimizable, closable, winIds}.

function sameIds(left, right) {
    return JSON.stringify((left || []).map(String)) === JSON.stringify((right || []).map(String));
}

// Who "the app" is, read from the active window. It is captured when the menu
// opens: the menu's own window takes the focus, so later there is no active task.
function target(rows) {
    const active = (rows || []).find(row => row && row.isWindow && row.active);
    return active ? {appId: String(active.appId || ""), winIds: (active.winIds || []).map(String)} : null;
}

// Every window sharing the AppId; without one, only the captured window.
function appWindows(rows, app) {
    if (!app) return [];
    return (rows || []).filter(row => row && row.isWindow
        && (app.appId ? row.appId === app.appId : sameIds(row.winIds, app.winIds)));
}

function otherWindows(rows, app) {
    const mine = appWindows(rows, app);
    return (rows || []).filter(row => row && row.isWindow && mine.indexOf(row) === -1);
}

function hideTargets(windows) {
    return (windows || []).filter(window => window.minimizable && !window.minimized);
}

function showTargets(rows) {
    return (rows || []).filter(row => row && row.isWindow && row.minimized);
}

function closeTargets(windows) {
    return (windows || []).filter(window => window.closable);
}

// How many windows each action would reach; zero disables its menu item.
function summary(rows, app) {
    const mine = appWindows(rows, app);
    return {hide: hideTargets(mine).length, hideOthers: hideTargets(otherWindows(rows, app)).length,
        showAll: showTargets(rows).length, quit: closeTargets(mine).length};
}
