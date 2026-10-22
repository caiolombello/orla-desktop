import QtQuick
import "../code/AddonText.js" as AddonText
import "../code/ThemeFile.js" as ThemeFile

// Management metadata only. The independent data route owns readings and leases.
QtObject {
    id: state
    property bool active: false
    property var owner: null
    property string scopeKey: ""
    property var transport: null
    readonly property alias addons: projection.rows
    readonly property alias preview: projection.previewRow
    readonly property alias generation: projection.registryGenerationValue
    readonly property alias valid: projection.validListing
    readonly property alias feedback: projection.message
    readonly property alias feedbackKind: projection.kind
    readonly property bool busy: internal.flight !== null || selecting
    readonly property bool loading: internal.flight !== null && !internal.flight.mutation
    readonly property bool selecting: internal.selection !== null
    signal mutationStarted(string member)
    signal mutationSettled(string member, var committed, var generation)

    property QtObject internal: QtObject {
        id: projection
        property var epoch: Object.freeze({})
        property var flight: null
        property var selection: null
        property var approval: null
        property bool releasing: false
        property var rows: Object.freeze([])
        property var previewRow: null
        property var registryGenerationValue: null
        property bool validListing: false
        property string message: ""
        property string kind: "status"
    }
    property Timer deadline: Timer {
        // Longer than the service's worker/reap budget; expiry never promises cancellation.
        interval: 7000
        repeat: false
        onTriggered: if (internal.flight) state.finish(internal.flight, null, true)
    }
    function emptyView(message) {
        return Object.freeze({addons: Object.freeze([]), preview: null, generation: null,
            valid: false, feedback: message, feedbackKind: message ? "error" : "status"});
    }
    function publish(value, epoch) {
        // Direct aliases avoid binding loops when a publication observer closes/reopens.
        // Invalidate first; every later setter belongs to this exact lifetime.
        const changes = [["validListing", false], ["previewRow", null], ["registryGenerationValue", null],
            ["rows", value.addons], ["previewRow", value.preview], ["registryGenerationValue", value.generation],
            ["message", value.feedback], ["kind", value.feedbackKind], ["validListing", value.valid]];
        for (const change of changes) {
            if (epoch !== internal.epoch) return false;
            internal[change[0]] = change[1];
        }
        return epoch === internal.epoch;
    }
    function available() { return active && Qt.isQtObject(owner) && transport !== null; }
    function live(op) {
        return available() && op.epoch === internal.epoch && op.owner === owner && op.transport === transport;
    }
    function idle() { return available() && !busy && !internal.releasing; }
    function invalidate() {
        if (!internal) return;
        const releasing = internal.releasing;
        internal.releasing = true;
        internal.epoch = Object.freeze({});
        internal.approval = null;
        internal.selection = null;
        publish(emptyView(""), internal.epoch);
        internal.releasing = releasing;
        if (available()) Qt.callLater(refresh);
    }
    onActiveChanged: invalidate()
    onOwnerChanged: invalidate()
    onScopeKeyChanged: invalidate()
    onTransportChanged: invalidate()
    Component.onCompleted: if (available()) Qt.callLater(refresh)

    function fields(value, names) {
        return value !== null && typeof value === "object" && !Array.isArray(value)
            && Object.keys(value).length === names.length
            && names.every(key => Object.prototype.hasOwnProperty.call(value, key));
    }
    function digest(value) { return typeof value === "string" && /^[0-9a-f]{64}$/.test(value); }
    function registryGeneration(value) { return typeof value === "string" && /^[0-9a-f]{32}$/.test(value); }
    function identifier(value) {
        return typeof value === "string" && value.length <= 120
            && /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)+$/.test(value);
    }
    function plain(value, maximum) { return AddonText.plain(value, maximum); }
    function originValid(value) {
        if (!plain(value, 512) || !/^https:\/\/[^\s?#\\<>"^`{|}]+$/.test(value)
                || /[^\x21-\x7e]/.test(value) || /%(?![0-9a-fA-F]{2})/.test(value)) return false;
        try { if (!plain(decodeURIComponent(value), 512)) return false; } catch (_) { return false; }
        const authority = value.slice(8).split("/")[0];
        const match = /^(\[[0-9a-fA-F:.]+\]|[A-Za-z0-9.-]+)(?::([0-9]+))?$/.exec(authority);
        if (!match || (match[2] && !(Number(match[2]) >= 1 && Number(match[2]) <= 65535))) return false;
        const host = match[1];
        if (host[0] !== "[") return host.length <= 253
            && /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.?$/.test(host);
        const address = host.slice(1, -1);
        const halves = address.split("::");
        if (halves.length > 2 || halves.some(part => part && (part[0] === ":" || part.slice(-1) === ":"))) return false;
        let groups = address.split(":").filter(part => part.length);
        let count = groups.length;
        if (groups.length && groups[groups.length - 1].indexOf(".") >= 0) {
            const dotted = groups.pop();
            if (address.slice(-dotted.length) !== dotted) return false;
            const tail = dotted.split(".");
            if (tail.length !== 4 || !tail.every(part => /^(0|[1-9][0-9]{0,2})$/.test(part) && Number(part) <= 255)) return false;
            count++;
        }
        return groups.every(part => /^[0-9a-fA-F]{1,4}$/.test(part))
            && (halves.length === 2 ? count < 8 : count === 8 && address[0] !== ":" && address.slice(-1) !== ":");
    }
    function row(manifest, sha) {
        if (!fields(manifest, ["formatVersion", "id", "name", "description", "author", "license", "version", "origin", "renderer", "source"])
                || manifest.formatVersion !== "0.1-experimental"
                || ["peripheral-battery", "quota-usage"].indexOf(manifest.renderer) < 0
                || !identifier(manifest.id) || !digest(sha) || !plain(manifest.name, 80)
                || !plain(manifest.description, 240) || !plain(manifest.author, 120) || !plain(manifest.license, 80)
                || typeof manifest.version !== "string" || manifest.version.length > 32
                || !/^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/.test(manifest.version)
                || !originValid(manifest.origin) || !fields(manifest.source, ["namespace", "formatVersion"])
                || manifest.source.formatVersion !== "0.1-experimental" || typeof manifest.source.namespace !== "string"
                || !/^[a-z][a-z0-9-]{0,63}$/.test(manifest.source.namespace)) return null;
        return {id: manifest.id, sha256: sha, name: manifest.name, description: manifest.description,
            author: manifest.author, license: manifest.license, version: manifest.version, origin: manifest.origin,
            namespace: manifest.source.namespace, renderer: manifest.renderer, enabled: false, state: "installed",
            previousSha256: null, valid: true};
    }
    function listing(value) {
        if (!fields(value, ["generation", "addons"]) || !Array.isArray(value.addons) || value.addons.length > 32
                || !(registryGeneration(value.generation) || (value.generation === null && !value.addons.length))) return null;
        const rows = [];
        const enabled = {};
        let previousId = "";
        for (const item of value.addons) {
            if (!fields(item, ["manifest", "sha256", "previousSha256", "enabled"]) || typeof item.enabled !== "boolean"
                    || !(item.previousSha256 === null || (digest(item.previousSha256) && item.previousSha256 !== item.sha256))) return null;
            const entry = row(item.manifest, item.sha256);
            if (!entry || entry.id <= previousId) return null;
            previousId = entry.id;
            entry.enabled = item.enabled;
            entry.previousSha256 = item.previousSha256;
            // At most one active addon per module (battery, quota).
            if (item.enabled && enabled[entry.renderer]) return null;
            if (item.enabled) enabled[entry.renderer] = true;
            rows.push(Object.freeze(entry));
        }
        return {generation: value.generation, addons: Object.freeze(rows)};
    }
    function decode(raw) {
        // Management has no numeric fields. Bound raw UTF-8, depth and duplicate keys before JSON.parse.
        if (typeof raw !== "string" || raw.length > 262144) return null;
        try { if (encodeURIComponent(raw).replace(/%[0-9A-F]{2}|./g, "x").length > 262144) return null; }
        catch (_) { return null; }
        let cursor = 0;
        function space() { while (/[ \t\r\n]/.test(raw.charAt(cursor)) && cursor < raw.length) cursor++; }
        function stringToken() {
            const start = cursor++;
            while (cursor < raw.length) {
                const c = raw.charAt(cursor++);
                if (c === '"') return JSON.parse(raw.slice(start, cursor));
                if (c.charCodeAt(0) < 32) throw new Error();
                if (c === "\\") {
                    const escape = raw.charAt(cursor++);
                    if (escape === "u") {
                        if (!/^[0-9a-fA-F]{4}$/.test(raw.slice(cursor, cursor + 4))) throw new Error();
                        cursor += 4;
                    } else if (!escape || '"\\/bfnrt'.indexOf(escape) < 0) throw new Error();
                }
            }
            throw new Error();
        }
        function value(depth) {
            space();
            const c = raw.charAt(cursor);
            if (c === '"') { stringToken(); return; }
            if (c === "{" || c === "[") {
                if (depth >= 8) throw new Error();
                const object = c === "{", end = object ? "}" : "]", seen = new Set();
                cursor++; space();
                if (raw.charAt(cursor) === end) { cursor++; return; }
                while (cursor < raw.length) {
                    space();
                    if (object) {
                        if (raw.charAt(cursor) !== '"') throw new Error();
                        const key = stringToken();
                        if (seen.has(key)) throw new Error();
                        seen.add(key); space();
                        if (raw.charAt(cursor++) !== ":") throw new Error();
                    }
                    value(depth + 1); space();
                    if (raw.charAt(cursor) === end) { cursor++; return; }
                    if (raw.charAt(cursor++) !== ",") throw new Error();
                }
                throw new Error();
            }
            for (const literal of ["true", "false", "null"]) {
                if (raw.slice(cursor, cursor + literal.length) === literal) { cursor += literal.length; return; }
            }
            throw new Error();
        }
        try {
            value(0); space();
            if (cursor !== raw.length) return null;
            const envelope = JSON.parse(raw);
            if (!envelope || envelope.formatVersion !== "0.1-experimental") return null;
            if (envelope.ok === true && fields(envelope, ["formatVersion", "ok", "result"])) return envelope;
            if (envelope.ok !== false || !fields(envelope, ["formatVersion", "ok", "error"])) return null;
            const error = envelope.error;
            const codes = "type size utf8 json depth duplicate_key nonfinite fields format range lease file missing unsafe drift hash state busy limit not_found no_previous exists io unavailable timeout invalid_response cleanup_failed source_changed cancelled".split(" ");
            if (!fields(error, ["code", "committed", "generation"]) || codes.indexOf(error.code) < 0
                    || !(error.committed === null || typeof error.committed === "boolean")
                    || !(error.generation === null || registryGeneration(error.generation))
                    || (error.committed === true && error.generation === null)
                    || (error.committed === false && error.generation !== null)) return null;
            return envelope;
        } catch (_) { return null; }
    }
    function fileUri(value) {
        if (typeof value !== "string" || !value.length || value.length > 4096
                || !/^file:\/\/\/[^?#]*$/.test(value) || /%(?![0-9a-fA-F]{2})/.test(value)) return false;
        try {
            const path = decodeURIComponent(value.slice(7));
            return path.length <= 4096 && path[0] === "/" && path.indexOf("\u0000") < 0 && path.split("/").indexOf("..") < 0;
        } catch (_) { return false; }
    }
    function beginFileSelection(selectionOwner) {
        if (!idle() || !valid || !Qt.isQtObject(selectionOwner)) return null;
        const intent = {token: Object.freeze({}), owner: selectionOwner, epoch: internal.epoch};
        internal.approval = null;
        internal.selection = intent;
        if (!ownsFileSelection(selectionOwner, intent.token)) return null;
        publish(Object.freeze({addons: addons, generation: generation, valid: valid,
            preview: null, feedback: "", feedbackKind: "status"}), intent.epoch);
        return internal.selection === intent && intent.epoch === internal.epoch ? intent.token : null;
    }
    function ownsFileSelection(selectionOwner, token) {
        const intent = internal.selection;
        return available() && intent !== null && intent.epoch === internal.epoch
            && Qt.isQtObject(selectionOwner) && intent.owner === selectionOwner && intent.token === token;
    }
    function cancelFileSelection(selectionOwner, token) {
        const intent = internal.selection;
        if (!intent || intent.owner !== selectionOwner || intent.token !== token) return false;
        internal.selection = null;
        return true;
    }
    function acceptFileSelection(selectionOwner, token, uri, dispatchGuard) {
        const intent = internal.selection;
        if (!intent || intent.owner !== selectionOwner || intent.token !== token || intent.epoch !== internal.epoch
                || !available() || !Qt.isQtObject(selectionOwner)
                || (dispatchGuard !== undefined && typeof dispatchGuard !== "function")) return false;
        if (!fileUri(uri)) {
            internal.releasing = true;
            internal.selection = null;
            if (intent.epoch === internal.epoch)
                publish(Object.freeze({addons: addons, generation: generation, valid: valid,
                    preview: null, feedback: qsTr("Escolha um arquivo local válido."), feedbackKind: "error"}), intent.epoch);
            internal.releasing = false;
            return false;
        }
        return dispatch("InspectAddonFile", [uri], false, {uri: uri}, intent, dispatchGuard);
    }
    function refresh() {
        if (!idle()) return false;
        return dispatch("ListAddons", [], false, {});
    }
    function installAddon(sha) {
        const approval = internal.approval;
        if (!idle() || !valid || !approval || sha !== approval.sha256 || approval.epoch !== internal.epoch
                || approval.generation !== generation || !digest(sha)) return false;
        return dispatch("InstallAddon", [approval.uri, sha], true, {id: approval.id, sha256: sha});
    }
    function change(member, id, sha) {
        if (!idle() || !valid || !identifier(id) || !digest(sha)) return false;
        const entry = addons.find(item => item.id === id && item.sha256 === sha);
        if (!entry || (member === "RollbackAddon" && !digest(entry.previousSha256))
                || (member === "EnableAddon" && (entry.enabled || addons.some(item => item.enabled)))
                || (member === "DisableAddon" && !entry.enabled)) return false;
        return dispatch(member, [id, sha], true, {id: id, sha256: sha, previousSha256: entry.previousSha256});
    }
    function enableAddon(id, sha) { return change("EnableAddon", id, sha); }
    function disableAddon(id, sha) { return change("DisableAddon", id, sha); }
    function removeAddon(id, sha) { return change("RemoveAddon", id, sha); }
    function rollbackAddon(id, sha) { return change("RollbackAddon", id, sha); }
    function canDispatch(op) {
        if (!live(op)) return false;
        try { if (op.dispatchGuard && op.dispatchGuard() !== true) return false; }
        catch (_) { return false; }
        return live(op);
    }
    function dispatch(member, args, mutation, target, selection, dispatchGuard) {
        if (selection ? (!ownsFileSelection(selection.owner, selection.token) || internal.flight || internal.releasing) : !idle()) return false;
        const op = {member: member, mutation: mutation, target: target, epoch: internal.epoch, owner: owner,
            transport: transport, generation: generation, dispatchGuard: dispatchGuard, dispatched: false, settling: false};
        internal.approval = null;
        internal.flight = op;
        if (selection && internal.selection === selection) internal.selection = null;
        if (mutation || member === "ListAddons") publish(emptyView(""), op.epoch);
        if (mutation) mutationStarted(member);
        if (!canDispatch(op)) { finish(op, null, true); return false; }
        deadline.restart();
        if (!canDispatch(op)) { finish(op, null, true); return false; }
        const message = {service: "org.orla.Addons", path: "/org/orla/Addons", iface: "org.orla.Addons1",
            member: member, signature: args.length === 0 ? "()" : args.length === 1 ? "(s)" : "(ss)", arguments: args};
        try {
            if (typeof op.transport.asyncCall !== "function") { finish(op, null, true); return false; }
            if (!canDispatch(op)) { finish(op, null, true); return false; }
            op.dispatched = true;
            op.transport.asyncCall(message, reply => finish(op, ThemeFile.replyText(reply), false), () => finish(op, null, true));
        } catch (_) { finish(op, null, true); }
        return true;
    }
    function mutationResult(op, result) {
        if (!result || !registryGeneration(result.generation) || result.generation === op.generation) return false;
        const entry = result.addons.find(item => item.id === op.target.id);
        if (op.member === "RemoveAddon") return !entry;
        if (!entry) return false;
        if (op.member === "RollbackAddon") return !entry.enabled && entry.sha256 === op.target.previousSha256
            && entry.previousSha256 === op.target.sha256;
        if (entry.sha256 !== op.target.sha256) return false;
        return op.member === "EnableAddon" ? entry.enabled : !entry.enabled;
    }
    function finish(op, raw, failed) {
        if (internal.flight !== op || op.settling) return;
        op.settling = true;
        deadline.stop();
        const envelope = failed ? null : decode(raw);
        let result = null, committed = op.mutation && op.dispatched ? null : false, settledGeneration = null;
        if (envelope && envelope.ok) {
            if (op.member === "InspectAddonFile") {
                if (fields(envelope.result, ["manifest", "sha256"])) result = row(envelope.result.manifest, envelope.result.sha256);
            } else {
                result = listing(envelope.result);
                if (op.mutation && !mutationResult(op, result)) result = null;
            }
            if (op.mutation && result) { committed = true; settledGeneration = result.generation; }
        } else if (envelope) {
            committed = envelope.error.committed;
            settledGeneration = envelope.error.generation;
        }
        if (live(op)) {
            if (result && op.member === "InspectAddonFile") {
                internal.approval = {uri: op.target.uri, sha256: result.sha256, id: result.id,
                    epoch: op.epoch, generation: op.generation};
                publish(Object.freeze({addons: addons, generation: generation, valid: valid,
                    preview: Object.freeze(result), feedback: "", feedbackKind: "status"}), op.epoch);
            } else if (result) {
                publish(Object.freeze({addons: result.addons, generation: result.generation, valid: true,
                    preview: null, feedback: "", feedbackKind: "status"}), op.epoch);
            } else {
                internal.approval = null;
                const code = envelope && !envelope.ok ? envelope.error.code : "invalid_response";
                const message = code === "hash" || code === "drift"
                    ? qsTr("O complemento mudou. Recarregue a lista e escolha o arquivo novamente.")
                    : op.mutation && committed !== false
                        ? qsTr("A alteração pode ter sido aplicada. Recarregando a lista; confirme o estado antes de tentar novamente.")
                        : qsTr("Não foi possível concluir. Confira o arquivo ou recarregue a lista.");
                publish(op.member === "InspectAddonFile"
                    ? Object.freeze({addons: addons, generation: generation, valid: valid,
                        preview: null, feedback: message, feedbackKind: "error"}) : emptyView(message), op.epoch);
            }
        }
        internal.releasing = true;
        internal.flight = null;
        if (op.mutation) mutationSettled(op.member, committed, settledGeneration);
        internal.releasing = false;
        // Read-only recovery, never a mutation retry. A newer flight/lifetime wins.
        if (available() && (!live(op) || (op.mutation && !result))) Qt.callLater(refresh);
    }
}
