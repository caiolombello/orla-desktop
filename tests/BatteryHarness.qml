import QtQuick
import org.kde.plasma.workspace.dbus as DBus
import "../package/contents/ui" as DockUI

Item {
    id: harness
    property var pending: []
    property var calls: []
    function asyncCall(message, resolve, reject) {
        calls = calls.concat([message]);
        pending = pending.concat([{resolve: resolve, reject: reject}]);
    }
    function resolve(index, value) { pending[index].resolve({value: value}); }
    function reject(index) { pending[index].reject({error: {message: "private fixture error"}}); }
    function resolveNativePath(index) {
        resolve(index, new DBus.objectPath("/org/freedesktop/UPower/devices/DisplayDevice"));
    }
    function resolveNativeBattery(index) {
        resolve(index, {IsPresent: true, Type: new DBus.uint32(2), Percentage: new DBus.double(25),
            State: new DBus.uint32(2), TimeToEmpty: new DBus.int64(900)});
    }
    DockUI.SystemBattery {
        id: battery
        objectName: "batteryUnderTest"
        transport: harness
    }
}
