import QtQml
import org.kde.kcmutils as KCMUtils

// Plasma 6.7.5 modules; KCMLauncher API provided by KF 6.30.0 locally.
QtObject {
    function openSystemSettings(name) {
        KCMUtils.KCMLauncher.openSystemSettings(name);
    }
}
