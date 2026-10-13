pragma Singleton
import QtQuick
import QtQuick.Window

// Private package-local routing; models and services remain owned by the dock.
QtObject {
    id: root
    readonly property int apiVersion: 1
    readonly property int ownerCount: _leases.length
    readonly property QtObject owner: ownerCount === 1 ? _leases[0].owner : null
    readonly property string status: ownerCount === 0 ? "unavailable" : ownerCount === 1 ? "ready" : "ambiguous"
    readonly property int generation: _generation
    property int _generation: 0
    property list<QtObject> _leases: []
    property Component _leaseFactory: Component {
        QtObject {
            id: lease
            property QtObject owner: null
            property bool registered: false
            onOwnerChanged: if (registered && owner === null) root.removeLease(lease)
        }
    }

    function validOwner(value) {
        return Qt.isQtObject(value) && typeof value.requestControlCenter === "function"
            && typeof value.releaseControlCenter === "function"
            && typeof value.controlCenterVisibleFor === "function";
    }
    function validHost(host, anchor) {
        return host instanceof Item && anchor instanceof Item
            && host.Window.window !== null && host.Window.window === anchor.Window.window
            && host.Window.window.visible && host.visible && anchor.visible && anchor.enabled;
    }
    function removeLease(lease) {
        const keep = [];
        let found = false;
        for (const current of _leases) {
            if (current === lease) found = true;
            else keep.push(current);
        }
        if (!found) return false;
        lease.registered = false;
        _leases = keep;
        _generation += 1;
        lease.destroy();
        return true;
    }
    function registerOwner(value, version) {
        if (typeof version !== "number" || version !== apiVersion || !validOwner(value)) return false;
        for (const lease of _leases) if (lease.owner === value) return false;
        const created = _leaseFactory.createObject(root, {owner: value});
        created.registered = true;
        _leases = _leases.concat([created]);
        _generation += 1;
        return true;
    }
    function unregisterOwner(value) {
        if (!Qt.isQtObject(value)) return false;
        for (const lease of _leases) if (lease.owner === value) return removeLease(lease);
        return false;
    }
    function requestOpen(client, host, anchor, version) {
        if (typeof version !== "number" || version !== apiVersion || !Qt.isQtObject(client)
                || !validHost(host, anchor) || !owner || !validOwner(owner)) return false;
        try {
            return owner.requestControlCenter(client, host, anchor) === true;
        } catch (_) {
            return false;
        }
    }
}
