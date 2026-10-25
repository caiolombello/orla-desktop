import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami
import "../code/Style.js" as Style

Controls.Control {
    id: root
    required property var actions
    required property var player
    required property var battery
    required property var audio
    // Optional: hosts without a brightness state show no display card.
    property var brightness: null
    // Optional: hosts without a Do Not Disturb state show no focus card.
    property var doNotDisturb: null
    // Optional: hosts without a microphone state show no microphone card.
    property var microphone: null
    // Optional: hosts without a power-profile state show no profile choice.
    property var powerProfile: null
    // Optional: hosts without a Wi-Fi state show no Wi-Fi card.
    property var wifi: null
    // Optional: hosts without a Bluetooth state show no Bluetooth card.
    property var bluetooth: null
    property color foreground: palette.windowText
    property color muted: palette.windowText
    property bool playing: false
    property string soundError: ""
    property string powerError: ""
    property string networkError: ""
    property string bluetoothError: ""
    property string allError: ""
    // "main" shows the modules; "wifi" the networks in range, as macOS does.
    property string page: "main"
    // Two columns of modules, as in macOS, once both fit their toggle and name.
    readonly property bool wide: width >= 300
    implicitWidth: 310
    // Tall enough to show every module without scrolling, as macOS does, on a
    // 1080p screen; the popup budget caps shorter screens, which then scroll.
    implicitHeight: Math.min(body.implicitHeight + topPadding + bottomPadding, 900)
    Layout.fillHeight: true
    Layout.minimumHeight: 1
    Accessible.role: Accessible.Pane
    Accessible.name: qsTr("Central de Controle")

    function boundedText(value, maximum) {
        return String(value || "").slice(0, maximum).replace(/\s+/g, " ").trim();
    }
    function outputIndex(id) {
        for (let index = 0; index < audio.outputs.length; ++index) {
            if (audio.outputs[index].id === id) return index;
        }
        return -1;
    }
    function request(kind) {
        const dispatched = actions && actions.open(kind);
        const message = dispatched ? "" : qsTr("Não foi possível encaminhar esta ação ao KDE. Tente novamente.");
        if (kind === "sound") soundError = message;
        else if (kind === "power") powerError = message;
        else if (kind === "network") networkError = message;
        else if (kind === "bluetooth") bluetoothError = message;
        else if (kind === "all") allError = message;
        return Boolean(dispatched);
    }
    function microphoneText() {
        const mic = root.microphone;
        if (!mic) return "";
        if (mic.status === "unavailable") return qsTr("Serviço de áudio indisponível");
        if (mic.status === "loading") return qsTr("Conectando ao áudio…");
        if (mic.status === "absent") return qsTr("Nenhum microfone disponível");
        if (mic.pending) return mic.desired ? qsTr("Silenciando…") : qsTr("Ativando…");
        const name = boundedText(mic.label, 128);
        return mic.muted ? qsTr("Mudo · %1").arg(name) : qsTr("Ligado · %1").arg(name);
    }
    function powerProfileLabel(id) {
        if (id === "power-saver") return qsTr("Economia de energia");
        if (id === "balanced") return qsTr("Equilibrado");
        if (id === "performance") return qsTr("Desempenho");
        return qsTr("Perfil desconhecido");
    }
    function syncPowerProfile() {
        if (root.powerProfile) profileSelector.currentIndex = root.powerProfile.profiles.indexOf(root.powerProfile.presentation);
    }
    function powerProfileText() {
        const power = root.powerProfile;
        if (!power) return "";
        if (power.error) return power.error;
        if (power.status === "loading") return qsTr("Lendo o perfil de energia…");
        if (power.status === "absent") return qsTr("Este sistema não oferece perfis de energia.");
        if (power.status === "unavailable") return qsTr("Serviço de energia indisponível");
        if (power.pending) return qsTr("Aplicando %1…").arg(powerProfileLabel(power.desired));
        const held = power.holds.filter(hold => hold.profile === power.current && hold.application.length > 0);
        if (held.length > 0)
            return qsTr("Mantido por %1").arg(boundedText(held.map(hold => hold.application).join(", "), 128));
        if (power.inhibitedReason === "lap-detected")
            return qsTr("Desempenho indisponível: o computador pode estar no colo.");
        if (power.inhibitedReason === "high-operating-temperature")
            return qsTr("Desempenho indisponível: o computador está muito quente.");
        if (power.inhibitedReason) return qsTr("Desempenho indisponível no momento.");
        if (power.current === "performance" && power.degradedReason)
            return qsTr("O desempenho pode estar reduzido para conter o aquecimento.");
        return "";
    }
    // Focus follows the page; the ring shows only when the keyboard opened it.
    function showWifi() { showPage("wifi", wifiDetails.action, wifiPage); if (wifi) wifi.scan(); }
    function showBluetooth() { showPage("bluetooth", bluetoothDetails.action, bluetoothPage); }
    function showPage(name, opener, loader) {
        const reason = opener.visualFocus ? Qt.TabFocusReason : Qt.OtherFocusReason;
        page = name;
        Qt.callLater(() => { if (loader.item) loader.item.backButton.forceActiveFocus(reason); });
    }
    function showMain() {
        const from = page;
        const loader = from === "wifi" ? wifiPage : from === "bluetooth" ? bluetoothPage : null;
        const reason = loader && loader.item && loader.item.backButton.visualFocus ? Qt.TabFocusReason : Qt.OtherFocusReason;
        page = "main";
        const opener = from === "wifi" ? wifiDetails.action : from === "bluetooth" ? bluetoothDetails.action : null;
        if (opener) Qt.callLater(() => opener.forceActiveFocus(reason));
    }
    function wifiText() {
        const radio = root.wifi;
        if (!radio) return "";
        // A cable keeps the computer online even with Wi-Fi off or missing; say so.
        const cable = Boolean(radio.wired && radio.wired.connected);
        if (radio.joining) return qsTr("Conectando a %1…").arg(boundedText(radio.joiningName, 64));
        if (radio.status === "loading") return qsTr("Lendo o Wi-Fi…");
        if (radio.status === "absent") return cable ? qsTr("Conectado por cabo") : qsTr("Nenhum adaptador Wi-Fi disponível");
        if (radio.status === "unavailable") return qsTr("Serviço de rede indisponível");
        if (radio.pending) return radio.desired ? qsTr("Ligando…") : qsTr("Desligando…");
        if (!radio.enabled) {
            const off = radio.hardwareEnabled ? qsTr("Desligado") : qsTr("Desligado por uma chave do computador");
            return cable ? qsTr("%1 · conectado por cabo").arg(off) : off;
        }
        if (radio.network)
            return cable ? qsTr("Conectado a %1 · cabo").arg(boundedText(radio.network, 64))
                         : qsTr("Conectado a %1").arg(boundedText(radio.network, 64));
        return cable ? qsTr("Conectado por cabo") : qsTr("Ligado · sem conexão");
    }
    function bluetoothText() {
        const radio = root.bluetooth;
        if (!radio) return "";
        if (radio.status === "loading") return qsTr("Lendo o Bluetooth…");
        if (radio.status === "absent") return qsTr("Nenhum adaptador Bluetooth disponível");
        if (radio.status === "unavailable") return qsTr("Serviço de Bluetooth indisponível");
        if (radio.pending) return radio.desired ? qsTr("Ligando…") : qsTr("Desligando…");
        if (!radio.enabled) return qsTr("Desligado");
        if (radio.busyDevice) return radio.busyWantsConnected ? qsTr("Conectando %1…").arg(boundedText(radio.busyName, 64))
                                                              : qsTr("Desconectando %1…").arg(boundedText(radio.busyName, 64));
        if (radio.connected.length === 1) return qsTr("Conectado a %1").arg(boundedText(radio.connected[0], 64));
        if (radio.connected.length > 1) return qsTr("%1 dispositivos conectados").arg(radio.connected.length);
        return qsTr("Ligado · nenhum dispositivo conectado");
    }
    function doNotDisturbText() {
        const mode = root.doNotDisturb;
        if (!mode) return "";
        if (mode.status === "unavailable") return qsTr("As notificações do KDE estão indisponíveis.");
        if (mode.status === "loading") return qsTr("Lendo o estado das notificações…");
        if (mode.pending) return mode.desired ? qsTr("Ativando…") : qsTr("Desativando…");
        if (!mode.inhibited) return qsTr("Desativado");
        const now = Date.now();
        if (mode.until > now) {
            if (mode.until - now > 300 * 86400000) return qsTr("Ativado até você desativar");
            return qsTr("Ativado até %1").arg(new Date(mode.until).toLocaleString(Qt.locale(), Locale.ShortFormat));
        }
        if (mode.byApplication && mode.applications.length > 0)
            return qsTr("Ativado por %1").arg(boundedText(mode.applications.join(", "), 128));
        return qsTr("Ativado por uma regra do KDE");
    }

    function reveal(control) {
        const viewport = scroll.contentItem;
        if (!control || !control.activeFocus || !viewport || viewport.contentY === undefined) return;
        const point = control.mapToItem(viewport, 0, 0);
        let offset = viewport.contentY;
        if (point.y < 0) offset += point.y;
        else if (point.y + control.height > viewport.height)
            offset += point.y + control.height - viewport.height;
        viewport.contentY = Math.max(0, Math.min(offset, Math.max(0, viewport.contentHeight - viewport.height)));
    }
    // A child's `visible` follows its parent, so module visibility reads the states.
    readonly property bool wifiShown: wifi !== null && wifi.status !== "inactive"
    readonly property bool bluetoothShown: bluetooth !== null && bluetooth.status !== "inactive"
    function contains(item) {
        for (let node = item; node; node = node.parent) if (node === body) return true;
        return false;
    }
    // Keep whatever gains keyboard focus inside the modules in view, as Tab moves.
    readonly property Item focusedItem: Window.activeFocusItem
    onFocusedItemChanged: if (contains(focusedItem)) reveal(focusedItem)

    component ModuleTitle: Controls.Label {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        elide: Text.ElideRight
        font.weight: Style.weight.demiBold
        color: root.foreground
    }
    component ErrorLabel: Controls.Label {
        Layout.fillWidth: true
        visible: text.length > 0
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: root.foreground
        Accessible.role: Accessible.AlertMessage
    }

    contentItem: Controls.ScrollView {
        id: scroll
        objectName: "controlCenterScroll"
        implicitWidth: root.implicitWidth
        contentWidth: availableWidth
        contentHeight: body.implicitHeight
        clip: true
        // Keep the scrollbar off the cards' edges.
        rightPadding: Controls.ScrollBar.vertical.visible ? Controls.ScrollBar.vertical.width + Style.space.xs : 0
        Controls.ScrollBar.horizontal.policy: Controls.ScrollBar.AlwaysOff
        ColumnLayout {
            id: body
            width: scroll.availableWidth
            spacing: Style.space.sm

            // The list pages exist only while shown: hidden, they would still
            // cost items and accessibility nodes.
            Loader {
                id: wifiPage
                Layout.fillWidth: true
                active: root.page === "wifi" && root.wifi !== null
                visible: active
                sourceComponent: ControlCenterWifiPage {
                    objectName: "controlCenterWifiPage"
                    wifi: root.wifi
                    foreground: root.foreground
                    muted: root.muted
                    actionError: root.networkError
                    onBackRequested: root.showMain()
                    onSettingsRequested: root.request("network")
                }
            }
            Loader {
                id: bluetoothPage
                Layout.fillWidth: true
                active: root.page === "bluetooth" && root.bluetooth !== null
                visible: active
                sourceComponent: ControlCenterBluetoothPage {
                    objectName: "controlCenterBluetoothPage"
                    bluetooth: root.bluetooth
                    foreground: root.foreground
                    muted: root.muted
                    actionError: root.bluetoothError
                    onBackRequested: root.showMain()
                    onSettingsRequested: root.request("bluetooth")
                }
            }

            GridLayout {
                id: tiles
                objectName: "controlCenterTiles"
                visible: root.page === "main"
                readonly property real half: (width - columnSpacing) / 2
                Layout.fillWidth: true
                columns: root.wide ? 2 : 1
                columnSpacing: Style.space.sm
                rowSpacing: Style.space.sm

                // Connectivity: the radios share one module, macOS style.
                Card {
                    objectName: "controlCenterConnectivityCard"
                    visible: root.wifiShown || root.bluetoothShown
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: root.wide ? tiles.half : tiles.width
                    radius: Style.radius.module
                    padding: Style.space.sm
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Style.space.xs
                        Item { Layout.fillHeight: true }
                        ColumnLayout {
                            id: wifiSection
                            objectName: "controlCenterWifiCard"
                            visible: root.wifiShown
                            Layout.fillWidth: true
                            spacing: Style.space.xxs
                            ControlCenterToggle {
                                id: wifiDetails
                                Layout.fillWidth: true
                                foreground: root.foreground
                                muted: root.muted
                                title: qsTr("Wi-Fi")
                                status: root.wifiText()
                                actionText: qsTr("Mostrar redes Wi-Fi")
                                // Stays enabled while confirming: disabling would drop keyboard focus.
                                // The state ignores a second request until the first one settles.
                                toggle.objectName: "controlCenterWifiToggle"
                                toggle.enabled: !!root.wifi && root.wifi.status === "ready"
                                toggle.checked: !!root.wifi && root.wifi.presentation
                                toggle.iconName: toggle.checked ? "network-wireless-symbolic" : "network-wireless-disconnected-symbolic"
                                toggle.text: toggle.checked ? qsTr("Desligar Wi-Fi") : qsTr("Ligar Wi-Fi")
                                statusLabel.objectName: "controlCenterWifiStatus"
                                action.objectName: "controlCenterWifiDetails"
                                onToggled: root.wifi.request(!root.wifi.enabled)
                                onActionTriggered: root.showWifi()
                            }
                            ErrorLabel {
                                objectName: "controlCenterWifiError"
                                text: root.wifi ? root.wifi.error : ""
                            }
                        }
                        Item { Layout.fillHeight: true }
                        ColumnLayout {
                            id: bluetoothSection
                            objectName: "controlCenterBluetoothCard"
                            visible: root.bluetoothShown
                            Layout.fillWidth: true
                            spacing: Style.space.xxs
                            ControlCenterToggle {
                                id: bluetoothDetails
                                Layout.fillWidth: true
                                foreground: root.foreground
                                muted: root.muted
                                title: qsTr("Bluetooth")
                                status: root.bluetoothText()
                                actionText: qsTr("Mostrar aparelhos Bluetooth")
                                toggle.objectName: "controlCenterBluetoothToggle"
                                toggle.enabled: !!root.bluetooth && root.bluetooth.status === "ready"
                                toggle.checked: !!root.bluetooth && root.bluetooth.presentation
                                toggle.iconName: toggle.checked ? "network-bluetooth-symbolic" : "network-bluetooth-inactive-symbolic"
                                toggle.text: toggle.checked ? qsTr("Desligar Bluetooth") : qsTr("Ligar Bluetooth")
                                statusLabel.objectName: "controlCenterBluetoothStatus"
                                action.objectName: "controlCenterBluetoothDetails"
                                onToggled: root.bluetooth.request(!root.bluetooth.enabled)
                                onActionTriggered: root.showBluetooth()
                            }
                            ErrorLabel {
                                objectName: "controlCenterBluetoothError"
                                text: root.bluetooth ? root.bluetooth.error : ""
                            }
                        }
                        Item { Layout.fillHeight: true }
                    }
                }

                // Now playing: the same live artwork as the dock's music icon.
                Card {
                    objectName: "controlCenterMediaCard"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: root.wide ? tiles.half : tiles.width
                    radius: Style.radius.module
                    RowLayout {
                        anchors.fill: parent
                        spacing: Style.space.sm
                        LiveIcon {
                            Layout.preferredWidth: Style.size.control
                            Layout.preferredHeight: Style.size.control
                            Layout.alignment: Qt.AlignTop
                            kind: "music"
                            live: Boolean(root.player)
                            info: ({art: root.player ? root.player.artUrl || "" : "", active: root.playing})
                            animationDuration: 0
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignTop
                            spacing: 0
                            Controls.Label {
                                objectName: "controlCenterMediaTitle"
                                Layout.fillWidth: true
                                text: root.player ? root.boundedText(root.player.track || root.player.identity, 256) || qsTr("Player sem título")
                                                  : qsTr("Nada tocando")
                                textFormat: Text.PlainText
                                wrapMode: Text.WordWrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                font.weight: Style.weight.demiBold
                                color: root.foreground
                            }
                            Controls.Label {
                                objectName: "controlCenterMediaDetail"
                                Layout.fillWidth: true
                                text: root.player ? root.boundedText(root.player.artist || root.player.identity, 256)
                                                  : qsTr("Nenhum player aberto")
                                textFormat: Text.PlainText
                                font.pixelSize: Style.type.caption
                                wrapMode: Text.WordWrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                color: root.muted
                            }
                        }
                    }
                }

                Card {
                    id: doNotDisturbCard
                    objectName: "controlCenterDoNotDisturbCard"
                    visible: root.doNotDisturb !== null && root.doNotDisturb.status !== "inactive"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: root.wide ? tiles.half : tiles.width
                    radius: Style.radius.module
                    padding: Style.space.sm
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Style.space.xxs
                        ControlCenterToggle {
                            Layout.fillWidth: true
                            foreground: root.foreground
                            muted: root.muted
                            title: qsTr("Não perturbe")
                            status: root.doNotDisturbText()
                            toggle.objectName: "controlCenterDoNotDisturb"
                            toggle.enabled: !!root.doNotDisturb && root.doNotDisturb.status === "ready"
                            toggle.checked: !!root.doNotDisturb && root.doNotDisturb.presentation
                            toggle.iconName: "weather-clear-night-symbolic"
                            toggle.text: toggle.checked ? qsTr("Desativar Não perturbe") : qsTr("Ativar Não perturbe")
                            statusLabel.objectName: "controlCenterDoNotDisturbStatus"
                            statusLabel.maximumLineCount: 3
                            onToggled: root.doNotDisturb.request(!root.doNotDisturb.inhibited)
                        }
                        ErrorLabel {
                            objectName: "controlCenterDoNotDisturbError"
                            text: root.doNotDisturb ? root.doNotDisturb.error : ""
                        }
                        Item { Layout.fillHeight: true }
                    }
                }

                Card {
                    objectName: "controlCenterMicrophoneCard"
                    visible: root.microphone !== null && root.microphone.status !== "inactive"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: root.wide ? tiles.half : tiles.width
                    radius: Style.radius.module
                    padding: Style.space.sm
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Style.space.xxs
                        ControlCenterToggle {
                            Layout.fillWidth: true
                            foreground: root.foreground
                            muted: root.muted
                            title: qsTr("Microfone")
                            status: root.microphoneText()
                            // Stays enabled while confirming: disabling would drop keyboard focus.
                            // The state ignores a second request until the first one settles.
                            toggle.objectName: "controlCenterMicrophoneMute"
                            toggle.enabled: !!root.microphone && root.microphone.status === "ready" && root.microphone.writable
                            toggle.checked: !!root.microphone && root.microphone.presentation
                            toggle.iconName: toggle.checked ? "microphone-sensitivity-muted-symbolic" : "audio-input-microphone-symbolic"
                            toggle.text: toggle.checked ? qsTr("Ativar microfone") : qsTr("Silenciar microfone")
                            statusLabel.objectName: "controlCenterMicrophoneStatus"
                            onToggled: root.microphone.request(!root.microphone.muted)
                        }
                        ErrorLabel {
                            objectName: "controlCenterMicrophoneError"
                            text: root.microphone ? root.microphone.error : ""
                        }
                        Item { Layout.fillHeight: true }
                    }
                }

                Card {
                    objectName: "controlCenterBrightnessCard"
                    visible: root.brightness !== null && root.brightness.status !== "inactive"
                    Layout.fillWidth: true
                    Layout.columnSpan: tiles.columns
                    radius: Style.radius.module
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Style.space.sm
                        ModuleTitle {
                            objectName: "controlCenterBrightnessHeading"
                            text: qsTr("Tela")
                        }
                        Repeater {
                            model: root.brightness ? root.brightness.displayIds : []
                            delegate: ColumnLayout {
                                id: displayRow
                                required property string modelData
                                readonly property var display: root.brightness.displayById(modelData) || ({label: ""})
                                Layout.fillWidth: true
                                spacing: Style.space.xxs
                                Controls.Label {
                                    Layout.fillWidth: true
                                    // A name only helps once there is more than one screen.
                                    visible: root.brightness.displayIds.length > 1
                                    text: displayRow.display.label || qsTr("Tela sem nome")
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                    color: root.muted
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Style.space.sm
                                    Controls.Slider {
                                        id: brightnessSlider
                                        objectName: "controlCenterBrightness"
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: 40
                                        padding: Style.space.xs
                                        from: 1
                                        to: 100
                                        stepSize: 1
                                        enabled: root.brightness.status === "ready"
                                        opacity: enabled ? 1 : 1 - Style.state.disabled
                                        Accessible.name: root.brightness.displayIds.length > 1
                                            ? qsTr("Brilho de %1").arg(displayRow.display.label || qsTr("tela sem nome")) : qsTr("Brilho da tela")
                                        onMoved: if (!root.brightness.request(displayRow.modelData, value))
                                            value = root.brightness.presentationPercent(displayRow.modelData)
                                        background: Rectangle {
                                            x: brightnessSlider.leftPadding
                                            y: brightnessSlider.topPadding + (brightnessSlider.availableHeight - height) / 2
                                            width: brightnessSlider.availableWidth
                                            height: Style.size.iconButton
                                            radius: height / 2
                                            color: Style.alpha(brightnessSlider.palette.windowText, Style.state.pressed)
                                            Rectangle {
                                                width: Math.max(parent.height, brightnessSlider.visualPosition * parent.width)
                                                height: parent.height
                                                radius: height / 2
                                                color: brightnessSlider.palette.highlight
                                            }
                                            Kirigami.Icon {
                                                x: Style.space.sm
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: Style.size.iconSm
                                                height: width
                                                source: "brightness-high-symbolic"
                                                isMask: true
                                                color: brightnessSlider.palette.highlightedText
                                            }
                                            Rectangle {
                                                objectName: "controlCenterBrightnessFocus"
                                                anchors.fill: parent
                                                anchors.margins: -Style.space.xs
                                                radius: height / 2
                                                color: "transparent"
                                                visible: brightnessSlider.visualFocus
                                                border.width: 2
                                                border.color: brightnessSlider.palette.highlight
                                            }
                                        }
                                        handle: Rectangle {
                                            x: brightnessSlider.leftPadding + brightnessSlider.visualPosition * (brightnessSlider.availableWidth - width)
                                            y: brightnessSlider.topPadding + (brightnessSlider.availableHeight - height) / 2
                                            width: Style.size.iconButton - Style.space.xs
                                            height: width
                                            radius: width / 2
                                            color: Style.glass.highlight
                                            border.width: 1
                                            border.color: Style.alpha(Style.glass.shade, 0.18)
                                            visible: brightnessSlider.enabled
                                        }
                                    }
                                    Binding {
                                        target: brightnessSlider
                                        property: "value"
                                        value: root.brightness.presentationPercent(displayRow.modelData)
                                        when: !brightnessSlider.pressed
                                        restoreMode: Binding.RestoreNone
                                    }
                                    Controls.Label {
                                        objectName: "controlCenterBrightnessPercent"
                                        Layout.minimumWidth: Style.size.control
                                        horizontalAlignment: Text.AlignRight
                                        text: qsTr("%1%").arg(Math.round(brightnessSlider.value))
                                        textFormat: Text.PlainText
                                        font.features: {"tnum": 1}
                                        color: root.foreground
                                    }
                                }
                            }
                        }
                        Controls.Label {
                            objectName: "controlCenterBrightnessStatus"
                            Layout.fillWidth: true
                            visible: text.length > 0
                            text: !root.brightness ? ""
                                : root.brightness.error.length > 0 ? root.brightness.error
                                : root.brightness.status === "absent" ? qsTr("Nenhuma tela com brilho ajustável.")
                                : root.brightness.status === "unavailable" ? qsTr("O controle de brilho do KDE está indisponível.")
                                : root.brightness.status === "loading" ? qsTr("Lendo o brilho das telas…") : ""
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                            color: root.foreground
                            Accessible.role: root.brightness && root.brightness.error.length > 0 ? Accessible.AlertMessage : Accessible.StaticText
                        }
                    }
                }

                Card {
                    objectName: "controlCenterSoundCard"
                    Layout.fillWidth: true
                    Layout.columnSpan: tiles.columns
                    radius: Style.radius.module
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Style.space.sm
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.topMargin: -Style.space.xs
                            Layout.bottomMargin: -Style.space.xs
                            spacing: Style.space.sm
                            ModuleTitle {
                                objectName: "controlCenterSoundHeading"
                                text: qsTr("Som")
                            }
                            OrlaIconButton {
                                id: soundAction
                                objectName: "controlCenterSoundAction"
                                flat: true
                                iconName: "go-next-symbolic"
                                text: qsTr("Abrir Som no KDE")
                                onClicked: root.request("sound")
                            }
                        }
                        // Volume: a thick capsule with the speaker inside, macOS style.
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Style.space.sm
                            Controls.Slider {
                                id: audioVolume
                                objectName: "controlCenterAudioVolume"
                                Layout.fillWidth: true
                                Layout.minimumHeight: 40
                                padding: Style.space.xs
                                from: 0
                                to: 100
                                stepSize: 1
                                enabled: root.audio.status === "ready" && root.audio.writable
                                    && (root.audio.pendingKind === "" || (root.audio.pendingKind === "volume"
                                        && root.audio.volumeGestureActive))
                                opacity: enabled ? 1 : 1 - Style.state.disabled
                                Accessible.name: qsTr("Volume da saída padrão")
                                onPressedChanged: {
                                    if (pressed) root.audio.beginVolumeGesture();
                                    else root.audio.endVolumeGesture();
                                }
                                onMoved: {
                                    const accepted = pressed ? root.audio.requestGestureVolume(value)
                                                             : root.audio.requestVolume(value);
                                    if (!accepted)
                                        value = root.audio.presentationVolume;
                                }
                                background: Rectangle {
                                    x: audioVolume.leftPadding
                                    y: audioVolume.topPadding + (audioVolume.availableHeight - height) / 2
                                    width: audioVolume.availableWidth
                                    height: Style.size.iconButton
                                    radius: height / 2
                                    color: Style.alpha(audioVolume.palette.windowText, Style.state.pressed)
                                    Rectangle {
                                        width: Math.max(parent.height, audioVolume.visualPosition * parent.width)
                                        height: parent.height
                                        radius: height / 2
                                        color: audioVolume.palette.highlight
                                    }
                                    Kirigami.Icon {
                                        x: Style.space.sm
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: Style.size.iconSm
                                        height: width
                                        source: root.audio.muted ? "audio-volume-muted-symbolic" : "audio-volume-high-symbolic"
                                        isMask: true
                                        color: audioVolume.palette.highlightedText
                                    }
                                    Rectangle {
                                        objectName: "controlCenterAudioVolumeFocus"
                                        // Leave a gap so focus remains distinct from a full accent track.
                                        anchors.fill: parent
                                        anchors.margins: -Style.space.xs
                                        radius: height / 2
                                        color: "transparent"
                                        visible: audioVolume.visualFocus
                                        border.width: 2
                                        border.color: audioVolume.palette.highlight
                                    }
                                }
                                handle: Rectangle {
                                    x: audioVolume.leftPadding + audioVolume.visualPosition * (audioVolume.availableWidth - width)
                                    y: audioVolume.topPadding + (audioVolume.availableHeight - height) / 2
                                    width: Style.size.iconButton - Style.space.xs
                                    height: width
                                    radius: width / 2
                                    color: Style.glass.highlight
                                    border.width: 1
                                    border.color: Style.alpha(Style.glass.shade, 0.18)
                                    visible: audioVolume.enabled
                                }
                            }
                            Binding {
                                target: audioVolume
                                property: "value"
                                value: root.audio.presentationVolume
                                when: !audioVolume.pressed || root.audio.volumeGestureBlocked
                                restoreMode: Binding.RestoreNone
                            }
                            Controls.Label {
                                objectName: "controlCenterAudioPercent"
                                Layout.minimumWidth: Style.size.control
                                horizontalAlignment: Text.AlignRight
                                text: qsTr("%1%").arg(Math.round(audioVolume.value))
                                textFormat: Text.PlainText
                                font.features: {"tnum": 1}
                                color: root.foreground
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Style.space.sm
                            OrlaIconButton {
                                id: muteAction
                                objectName: "controlCenterAudioMute"
                                enabled: root.audio.status === "ready" && root.audio.writable
                                    && root.audio.pendingKind === "" && !root.audio.volumeGestureActive
                                checked: root.audio.muted
                                iconName: root.audio.muted ? "audio-volume-muted-symbolic" : "audio-volume-high-symbolic"
                                text: root.audio.muted ? qsTr("Ativar som") : qsTr("Silenciar")
                                onClicked: root.audio.requestMute(!root.audio.muted)
                            }
                            Controls.ComboBox {
                                id: outputSelector
                                objectName: "controlCenterOutputSelector"
                                Layout.fillWidth: true
                                Layout.minimumHeight: 40
                                model: root.audio.outputs
                                textRole: "label"
                                enabled: root.audio.status === "ready" && root.audio.outputs.length > 0
                                    && root.audio.pendingKind === "" && !root.audio.volumeGestureActive
                                displayText: currentIndex >= 0
                                    ? root.boundedText(root.audio.outputs[currentIndex].label, 128)
                                    : qsTr("Nenhuma saída")
                                delegate: Controls.ItemDelegate {
                                    required property var modelData
                                    width: outputSelector.width
                                    text: root.boundedText(modelData.label, 128)
                                    contentItem: Text {
                                        text: parent.text
                                        textFormat: Text.PlainText
                                        elide: Text.ElideRight
                                        verticalAlignment: Text.AlignVCenter
                                        color: parent.palette.buttonText
                                        font: parent.font
                                    }
                                }
                                Accessible.name: qsTr("Saída de áudio padrão")
                                onActivated: index => {
                                    if (index >= 0 && index < root.audio.outputs.length)
                                        root.audio.requestDefaultOutput(root.audio.outputs[index].id);
                                }
                            }
                            Binding {
                                target: outputSelector
                                property: "currentIndex"
                                value: root.outputIndex(root.audio.presentationOutputId)
                                when: true
                                restoreMode: Binding.RestoreNone
                            }
                        }
                        Controls.Label {
                            objectName: "controlCenterAudioStatus"
                            Layout.fillWidth: true
                            visible: text.length > 0
                            text: root.audio.error ? root.audio.error
                                : root.audio.pendingKind ? qsTr("Aplicando…")
                                : root.audio.status === "loading" ? qsTr("Conectando ao áudio…")
                                : root.audio.status === "absent" ? qsTr("Nenhuma saída de áudio disponível")
                                : root.audio.status === "unavailable" ? qsTr("Serviço de áudio indisponível") : ""
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                            color: root.audio.error ? root.foreground : root.muted
                            Accessible.role: root.audio.error ? Accessible.AlertMessage : Accessible.StaticText
                        }
                        OrlaButton {
                            id: audioRetry
                            objectName: "controlCenterAudioRetry"
                            Layout.fillWidth: true
                            Layout.minimumHeight: 40
                            visible: root.audio.status === "unavailable"
                            enabled: root.audio.pendingKind === "" && !root.audio.volumeGestureActive
                            text: qsTr("Tentar reconectar o áudio")
                            onClicked: root.audio.retry()
                        }
                        Controls.Label {
                            objectName: "controlCenterSoundError"
                            Layout.fillWidth: true
                            visible: root.soundError.length > 0
                            text: root.soundError
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                            color: root.foreground
                            Accessible.role: Accessible.AlertMessage
                        }
                    }
                }

                Card {
                    objectName: "controlCenterPowerCard"
                    Layout.fillWidth: true
                    Layout.columnSpan: tiles.columns
                    radius: Style.radius.module
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Style.space.sm
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.topMargin: -Style.space.xs
                            Layout.bottomMargin: -Style.space.xs
                            spacing: Style.space.sm
                            ModuleTitle {
                                objectName: "controlCenterPowerHeading"
                                text: qsTr("Energia")
                            }
                            OrlaIconButton {
                                objectName: "controlCenterPowerAction"
                                flat: true
                                iconName: "go-next-symbolic"
                                text: qsTr("Abrir Energia no KDE")
                                onClicked: root.request("power")
                            }
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            // Wide: ring, battery text and profile on one line; narrow: profile below.
                            columns: root.wide ? 3 : 2
                            columnSpacing: Style.space.md
                            rowSpacing: Style.space.sm
                            Item {
                                Layout.preferredWidth: Style.size.target + Style.space.xs
                                Layout.preferredHeight: Style.size.target + Style.space.xs
                                Layout.alignment: Qt.AlignTop
                                ProgressRing {
                                    anchors.fill: parent
                                    lineWidth: Style.space.xs
                                    progress: root.battery && root.battery.percentKnown ? root.battery.percent / 100 : 0
                                    color: root.palette.highlight
                                    trackColor: Style.alpha(root.foreground, 0.12)
                                    animationDuration: 0
                                }
                                Kirigami.Icon {
                                    anchors.centerIn: parent
                                    width: Style.size.iconMd
                                    height: width
                                    source: root.battery && root.battery.charging ? "battery-full-charging-symbolic" : "battery-100-symbolic"
                                    isMask: true
                                    color: root.foreground
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                Controls.Label {
                                    objectName: "controlCenterPowerTitle"
                                    Layout.fillWidth: true
                                    text: root.battery ? root.battery.summary : qsTr("Bateria indisponível")
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                    font.weight: Style.weight.demiBold
                                    color: root.foreground
                                }
                                Controls.Label {
                                    objectName: "controlCenterPowerDetail"
                                    Layout.fillWidth: true
                                    text: root.battery ? root.battery.subtitle : qsTr("Serviço de energia indisponível")
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                    color: root.muted
                                }
                            }
                            Controls.ComboBox {
                                id: profileSelector
                                objectName: "controlCenterPowerProfile"
                                visible: root.powerProfile !== null && root.powerProfile.status === "ready"
                                Layout.columnSpan: root.wide ? 1 : 2
                                Layout.fillWidth: !root.wide
                                Layout.preferredWidth: root.wide ? Style.size.target * 3 + Style.space.xs : -1
                                Layout.minimumHeight: 40
                                model: root.powerProfile ? root.powerProfile.profiles : []
                                // Stays enabled while confirming: disabling would drop keyboard focus.
                                // The state ignores a second request until the first one settles.
                                enabled: !!root.powerProfile && root.powerProfile.status === "ready"
                                // The label follows the state, not currentIndex: ComboBox resets
                                // its index on its own when the list of profiles changes.
                                displayText: root.powerProfileLabel(root.powerProfile ? root.powerProfile.presentation : "")
                                onCountChanged: Qt.callLater(root.syncPowerProfile)
                                delegate: Controls.ItemDelegate {
                                    required property var modelData
                                    width: profileSelector.width
                                    enabled: root.powerProfile.selectable(modelData)
                                    text: root.powerProfileLabel(modelData)
                                    contentItem: Text {
                                        text: parent.text
                                        textFormat: Text.PlainText
                                        elide: Text.ElideRight
                                        verticalAlignment: Text.AlignVCenter
                                        color: parent.palette.buttonText
                                        opacity: parent.enabled ? 1 : 0.5
                                        font: parent.font
                                    }
                                }
                                Accessible.name: qsTr("Perfil de energia")
                                onActivated: index => {
                                    if (index >= 0 && index < root.powerProfile.profiles.length)
                                        root.powerProfile.request(root.powerProfile.profiles[index]);
                                    // An ignored or refused choice must not stay selected.
                                    root.syncPowerProfile();
                                }
                            }
                            Binding {
                                target: profileSelector
                                property: "currentIndex"
                                value: root.powerProfile ? root.powerProfile.profiles.indexOf(root.powerProfile.presentation) : -1
                                when: true
                                restoreMode: Binding.RestoreNone
                            }
                        }
                        Controls.Label {
                            objectName: "controlCenterPowerProfileStatus"
                            Layout.fillWidth: true
                            visible: root.powerProfile !== null && root.powerProfile.status !== "inactive" && text.length > 0
                            text: root.powerProfileText()
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                            color: root.powerProfile && root.powerProfile.error ? root.foreground : root.muted
                            Accessible.role: root.powerProfile && root.powerProfile.error ? Accessible.AlertMessage : Accessible.StaticText
                        }
                        ErrorLabel {
                            objectName: "controlCenterPowerError"
                            text: root.powerError
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                visible: root.page === "main"
                spacing: Style.space.xs
                OrlaButton {
                    objectName: "controlCenterAllAction"
                    variant: "ghost"
                    Layout.fillWidth: true
                    Layout.minimumHeight: 40
                    text: qsTr("Ajustes do sistema…")
                    Accessible.name: qsTr("Todos os ajustes do sistema")
                    onClicked: root.request("all")
                }
                ErrorLabel {
                    objectName: "controlCenterAllError"
                    text: root.allError
                }
            }
        }
    }
}
