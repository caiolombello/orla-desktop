// Plasma 6.7.5 fixed operations. Request fields are validated Orla data.
(function () {
    const request = __ORLA_REQUEST__;
    const moduleIds = {menu:"org.orla.bar", "control-center":"org.orla.bar", "global-menu":"org.kde.plasma.appmenu",
        spacer:"org.kde.plasma.panelspacer", tray:"org.kde.plasma.systemtray", clock:"org.kde.plasma.digitalclock"};
    const controls = {network:"org.kde.plasma.networkmanagement", bluetooth:"org.kde.plasma.bluetooth",
        audio:"org.kde.plasma.volume", battery:"org.kde.plasma.battery", notifications:"org.kde.plasma.notifications"};
    function canonical(value) {
        if (Array.isArray(value)) return value.map(canonical);
        if (value !== null && typeof value === "object") {
            const sorted = {};
            Object.keys(value).sort().forEach(key => {sorted[key] = canonical(value[key]);});
            return sorted;
        }
        return value;
    }
    function equal(a,b) {return JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));}
    function marker(panel) {
        panel.currentConfigGroup = ["OrlaManaged"];
        const value = {token:panel.readConfig("token", ""), schemaVersion:panel.readConfig("schemaVersion", 0)};
        panel.currentConfigGroup = [];
        return value;
    }
    function widgets(panel) {
        return panel.widgets().map(widget => ({id:widget.id, type:widget.type, index:widget.index}))
            .sort((a,b) => a.index-b.index || a.id-b.id);
    }
    function members(panel) {
        return panel.widgets().map(widget => ({id:widget.id, type:widget.type})).sort((a,b) => a.id-b.id);
    }
    function inventory(connector) {
        const ids = [];
        desktops().concat(panels()).forEach(item => {
            if (item.screen >= 0 && ids.indexOf(item.screen) < 0) ids.push(item.screen);
        });
        ids.sort((a,b) => a-b);
        let screen = null;
        if (connector) {
            const id = screenForConnector(connector);
            if (ids.indexOf(id) >= 0) {
                const geometry = screenGeometry(id);
                screen = {id:id, connector:connector,
                    geometry:{x:geometry.x, y:geometry.y, width:geometry.width, height:geometry.height}};
            }
        }
        return {version:applicationVersion, screenIds:ids, selectedScreen:screen,
            knownWidgetTypes:knownWidgetTypes.slice().sort(),
            panels:panels().map(panel => ({id:panel.id, type:panel.type, screen:panel.screen, height:panel.height,
                widgets:widgets(panel), marker:marker(panel)})).sort((a,b) => a.id-b.id)};
    }
    function requireOwned(id, token) {
        const panel = panelById(id);
        if (!panel || panel.type !== "org.kde.panel" || marker(panel).token !== token
                || marker(panel).schemaVersion !== 1) throw new Error("managed panel identity changed");
        return panel;
    }
    if (applicationVersion !== "6.7.5") throw new Error("unsupported Plasma version");
    if (request.operation === "inspect") {
        print(JSON.stringify(inventory(request.connector)));
        return;
    }
    if (request.operation === "remove-owned") {
        if (!equal(inventory(request.connector), request.expectedInventory))
            throw new Error("post-layout inventory changed before owned removal");
        requireOwned(request.panelId, request.token).remove();
        print(JSON.stringify({removed:true}));
        return;
    }
    if (request.operation === "reorder-owned") {
        const owned = requireOwned(request.panelId, request.token);
        const selected = request.orderedWidgets.map(item => {
            const widget = owned.widgetById(item.id);
            if (!widget || widget.type !== item.type) throw new Error("managed widget identity changed");
            return widget;
        });
        if (!equal(inventory(request.connector), request.expectedInventory))
            throw new Error("post-layout inventory changed before owned reorder");
        // Plasma 6.7.5 removes the ID before clamping to order.length()-1.
        // Setting the first N-1 positions leaves the last in the remaining slot.
        selected.slice(0, -1).forEach((widget,index) => {widget.index = index;});
        print(JSON.stringify({reordered:true}));
        return;
    }
    if (request.operation === "update-owned") {
        const plan = request.updatePlan;
        const config = {showOrlaMenu:false, showApplicationName:false, showControlCenter:true};
        const validId = value => Number.isInteger(value) && value > 0 && value <= 2147483647;
        if (!plan || plan.schemaVersion !== 1 || plan.kind !== "managed-panel-update"
                || plan.operation !== "add-control-center" || typeof plan.planId !== "string"
                || !/^[0-9a-f]{64}$/.test(plan.planId) || !plan.entry
                || plan.entry.key !== "control-center" || !equal(plan.entry.config, config))
            throw new Error("invalid control-center update request");
        const prior = plan.owned;
        if (!prior || !validId(prior.panelId) || typeof prior.token !== "string"
                || !/^[0-9a-f]{64}$/.test(prior.token) || prior.nativeValidated !== false
                || !Array.isArray(prior.widgets) || !prior.widgets.length)
            throw new Error("invalid prior managed identity");
        const modules = plan.originPlan.manifest.modules.filter(module => module.enabled === true);
        const insertion = plan.insertionIndex;
        if (modules.length !== prior.widgets.length || !Number.isInteger(insertion)
                || insertion < 1 || insertion >= modules.length
                || modules[insertion - 1].key !== "tray" || modules[insertion].key !== "clock"
                || prior.token !== plan.originPlan.planId)
            throw new Error("invalid control-center insertion roles");
        const seenIds = {}, seenRoles = {};
        for (let index = 0; index < prior.widgets.length; index++) {
            const item = prior.widgets[index], key = modules[index].key;
            if (!item || !validId(item.id) || item.index !== index || seenIds[item.id]
                    || !Object.prototype.hasOwnProperty.call(moduleIds, key) || seenRoles[key]
                    || key === "control-center" || item.type !== moduleIds[key])
                throw new Error("prior managed widget identity or role changed");
            seenIds[item.id] = true; seenRoles[key] = true;
        }
        if (!equal(inventory(request.connector), plan.inventory))
            throw new Error("planned update inventory changed");
        const panel = requireOwned(prior.panelId, prior.token);
        if (panel.screen !== prior.screen || panel.height !== prior.height || !equal(widgets(panel), prior.widgets))
            throw new Error("prior managed panel structure changed");
        const existingIds = [];
        plan.inventory.panels.forEach(item => item.widgets.forEach(widget => existingIds.push(widget.id)));
        const added = panel.addWidget(moduleIds["control-center"]);
        const addedId = added ? added.id : null;
        if (!added || added.type !== moduleIds["control-center"] || !validId(addedId)
                || existingIds.indexOf(addedId) >= 0)
            throw new Error("control-center widget creation failed");
        // Persist a unique update link before the trio so a lost reply can qualify a partial entry.
        added.currentConfigGroup = ["OrlaManagedUpdate"];
        added.writeConfig("token", plan.planId);
        if (added.readConfig("token", "") !== plan.planId)
            throw new Error("control-center update marker readback failed");
        added.currentConfigGroup = ["General"];
        Object.keys(config).forEach(key => added.writeConfig(key, config[key]));
        added.reloadConfig();
        added.currentConfigGroup = ["General"];
        Object.keys(config).forEach(key => {
            if (added.readConfig(key, !config[key]) !== config[key])
                throw new Error("control-center configuration readback failed");
        });
        added.currentConfigGroup = [];
        const intended = prior.widgets.map((item, index) => ({id:item.id, type:item.type,
            index:index < insertion ? index : index + 1}));
        intended.splice(insertion, 0, {id:addedId, type:moduleIds["control-center"], index:insertion});
        if (added.id !== addedId || added.type !== moduleIds["control-center"])
            throw new Error("created control-center identity changed");
        requireOwned(prior.panelId, prior.token);
        if (!equal(members(panel), intended.map(item => ({id:item.id, type:item.type})).sort((a,b) => a.id-b.id)))
            throw new Error("updated managed panel membership changed");
        const after = inventory(request.connector);
        // Deferred indices belong to the cold reorder guard. Every other inventory fact stays exact.
        after.panels.find(item => item.id === prior.panelId).widgets = prior.widgets;
        if (!equal(after, plan.inventory)) throw new Error("update changed unrelated panel inventory");
        print(JSON.stringify({panelId:prior.panelId, token:prior.token, widgets:intended,
            screen:prior.screen, height:prior.height, nativeValidated:false}));
        return;
    }
    if (request.operation !== "apply") throw new Error("unsupported operation");
    const plan = request.plan;
    if (!equal(inventory(plan.manifest.screen.connector), plan.inventory))
        throw new Error("planned panel inventory changed");
    const panel = new Panel("org.kde.panel");
    panel.currentConfigGroup = ["OrlaManaged"];
    panel.writeConfig("token", plan.planId);
    panel.writeConfig("schemaVersion", 1);
    panel.currentConfigGroup = [];
    panel.screen = plan.screen.id;
    Object.keys(plan.manifest.panel).forEach(key => {panel[key] = plan.manifest.panel[key];});
    const moved = [];
    const created = [];
    plan.manifest.modules.filter(module => module.enabled).forEach((module,index) => {
        let widget;
        const reusedId = plan.manifest.reuseWidgetIds[module.key];
        if (reusedId !== undefined) {
            const origin = plan.selectedPanels.find(old => old.widgets.some(item => item.id === reusedId));
            const source = origin && panelById(origin.id);
            widget = source && source.widgetById(reusedId);
            if (!widget || widget.type !== moduleIds[module.key]) throw new Error("reused widget changed");
            widget = panel.addWidget(widget);
            moved.push(reusedId);
        } else {
            widget = panel.addWidget(moduleIds[module.key]);
        }
        if (!widget || widget.type !== moduleIds[module.key]) throw new Error("selected widget creation failed");
        widget.currentConfigGroup = (module.key === "global-menu" || module.key === "clock") ? ["Appearance"] : ["General"];
        if (module.key === "tray") {
            const enabled = (module.config.controls || []).map(key => controls[key]);
            const overflow = (module.config.overflow || []).map(key => controls[key]);
            const nativeIds = Object.keys(controls).map(key => controls[key]);
            const preserveApps = key => {
                const previous = widget.readConfig(key, []);
                const array = Array.isArray(previous);
                // Qt 6.11.2 returns typed native lists as V4Sequence, not Array.
                if (previous === null || typeof previous !== "object"
                        || (!array && Object.prototype.toString.call(previous) !== "[object V4Sequence]"))
                    throw new Error("invalid native tray visibility list");
                const length = previous.length;
                // This local bound refuses oversize lists; it never truncates IDs.
                if (!Number.isInteger(length) || length < 0 || length > 4096)
                    throw new Error("invalid native tray visibility list");
                const copied = [];
                for (let index = 0; index < length; index++) {
                    const id = previous[index];
                    if ((array && !Object.prototype.hasOwnProperty.call(previous, index)) || typeof id !== "string")
                        throw new Error("invalid native tray visibility list");
                    copied.push(id);
                }
                if (previous.length !== length) throw new Error("invalid native tray visibility list");
                return copied.filter(id => nativeIds.indexOf(id) < 0);
            };
            const hiddenApps = preserveApps("hiddenItems");
            const shownApps = preserveApps("shownItems");
            widget.writeConfig("extraItems", enabled);
            widget.writeConfig("hiddenItems", hiddenApps.concat(overflow));
            widget.writeConfig("shownItems", shownApps.concat(enabled.filter(id => overflow.indexOf(id) < 0)));
            widget.writeConfig("showAllItems", false);
        } else if (module.key === "spacer") {
            widget.writeConfig("expanding", true);
        } else {
            Object.keys(module.config).forEach(key => widget.writeConfig(key, module.config[key]));
        }
        widget.reloadConfig();
        widget.currentConfigGroup = [];
        created.push({id:widget.id, type:widget.type, index:index});
    });
    requireOwned(panel.id, plan.planId);
    if (panel.screen !== plan.screen.id || panel.height !== plan.manifest.panel.height
            || !equal(members(panel), created.map(item => ({id:item.id, type:item.type})).sort((a,b) => a.id-b.id)))
        throw new Error("managed panel structural readback failed");
    // Intentional moves are the only permitted difference in a displaced panel.
    plan.selectedPanels.forEach(old => {
        const source = panelById(old.id);
        const expected = old.widgets.filter(widget => moved.indexOf(widget.id) < 0)
            .map(widget => ({id:widget.id, type:widget.type}));
        const actual = source && widgets(source).map(widget => ({id:widget.id, type:widget.type}));
        if (!source || source.type !== old.type || source.screen !== old.screen
                || !equal(expected, actual))
            throw new Error("displaced panel changed beyond planned moves");
    });
    plan.selectedPanels.forEach(old => panelById(old.id).remove());
    print(JSON.stringify({panelId:panel.id, token:plan.planId, widgets:created, screen:panel.screen,
        height:panel.height, nativeValidated:false}));
})();
