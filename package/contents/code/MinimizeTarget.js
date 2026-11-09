.pragma library

// Where KWin's minimize effect (magic lamp) lands for a task. Pure math so the
// target can be checked without a compositor.

// Plasma's task manager waits 500 ms; a shorter beat still coalesces a scroll
// or resize burst into one request while keeping the target fresh.
var publishInterval = 250;

// The artwork's resting box in the delegate's coordinates: `slot` is the
// untransformed artwork (no hover lift, press scale or bounce). With `bounds`
// (the visible lane, same coordinates) a tile scrolled out of view still
// targets the nearest edge of the dock instead of an off-screen point.
function stableRect(slot, bounds) {
    if (!slot || !(slot.width > 0) || !(slot.height > 0)) return null;
    const width = Math.round(slot.width);
    const height = Math.round(slot.height);
    let x = Math.round(slot.x);
    const y = Math.round(slot.y);
    if (bounds && bounds.width >= width) {
        const left = Math.ceil(bounds.x);
        const right = Math.max(left, Math.floor(bounds.x + bounds.width) - width);
        x = Math.min(Math.max(x, left), right);
    }
    return {x: x, y: y, width: width, height: height};
}

// The same box in global coordinates, given where its top-left maps to.
function globalRect(local, origin) {
    if (!local || !origin) return null;
    return {x: Math.round(origin.x), y: Math.round(origin.y), width: local.width, height: local.height};
}

// Identity of one publication; an unchanged key needs no new request.
function publicationKey(row, windows, rect) {
    if (!rect) return "";
    return [row, windows, rect.x, rect.y, rect.width, rect.height].join("|");
}
