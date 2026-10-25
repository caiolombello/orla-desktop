import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import menu_bar_clock as clock  # noqa: E402

# A fake `gdbus` that runs the real Plasma script in QJSEngine against panels
# kept in $XDG_STATE_HOME/fake-plasma.json, and prints gdbus' one-string tuple.
FAKE_GDBUS = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtQml import QJSEngine
    path = os.path.join(os.environ["XDG_STATE_HOME"], "fake-plasma.json")
    if not os.path.exists(path):
        sys.exit("plasmashell is not running")
    model = json.load(open(path))
    app = QCoreApplication.instance() or QCoreApplication([])
    engine = QJSEngine()
    prelude = '''
    var __out = "";
    function print(text) { __out += String(text); }
    var __model = %s;
    function panels() {
        return __model.panels.map(function (p) {
            return {id: p.id, location: p.location, widgets: function () {
                return p.widgets.map(function (w) {
                    return {id: w.id, type: w.type, currentConfigGroup: [],
                        readConfig: function (key, fallback) {
                            var group = w.config[this.currentConfigGroup.join("/")] || {};
                            return key in group ? group[key] : fallback;
                        },
                        writeConfig: function (key, value) {
                            var name = this.currentConfigGroup.join("/");
                            w.config[name] = w.config[name] || {};
                            w.config[name][key] = value;
                        }};
                });
            }};
        });
    }
    '''
    engine.evaluate(prelude % json.dumps(model))
    result = engine.evaluate(sys.argv[-1])
    if result.isError():
        sys.exit("script error: " + result.toString())
    state = engine.evaluate("JSON.stringify({out: __out, model: __model})").toString()
    state = json.loads(state)
    json.dump(state["model"], open(path, "w"))
    print(repr((state["out"],)))
    """)


def plasma(clock_config=None, *, with_menu=True):
    """Panels: an Orla top bar with a clock, the dock below and a plain top panel."""
    top = [{"id": 22, "type": "org.kde.plasma.digitalclock",
            "config": {"Appearance": dict(clock_config or {"showDate": False})}}]
    if with_menu:
        top.insert(0, {"id": 35, "type": "org.orla.bar", "config": {}})
    return {"panels": [
        {"id": 36, "location": "top", "widgets": top},
        {"id": 32, "location": "bottom", "widgets": [
            {"id": 34, "type": "org.caiodock.dock", "config": {}},
            {"id": 50, "type": "org.kde.plasma.digitalclock", "config": {}}]},
        {"id": 40, "location": "top", "widgets": [
            {"id": 41, "type": "org.kde.plasma.digitalclock", "config": {}}]},
    ]}


def install_fake_gdbus(tools: Path) -> None:
    path = tools / "gdbus"
    path.write_text(FAKE_GDBUS.replace("#!/usr/bin/env python3", "#!" + sys.executable, 1), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class MenuBarClockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        tools = base / "bin"
        tools.mkdir()
        install_fake_gdbus(tools)
        (base / "state").mkdir()
        self.base = base
        self.env = dict(os.environ, PATH=f"{tools}{os.pathsep}{os.environ['PATH']}",
                        XDG_STATE_HOME=str(base / "state"), QT_QPA_PLATFORM="offscreen")

    def tearDown(self):
        self.temp.cleanup()

    def publish(self, model):
        (self.base / "state/fake-plasma.json").write_text(json.dumps(model), encoding="utf-8")

    def model(self):
        return json.loads((self.base / "state/fake-plasma.json").read_text(encoding="utf-8"))

    def clock_config(self, widget_id):
        for panel in self.model()["panels"]:
            for widget in panel["widgets"]:
                if widget["id"] == widget_id:
                    return widget["config"].get("Appearance", {})
        raise KeyError(widget_id)

    def run_clock(self, command, expect=0):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/menu_bar_clock.py"), command],
                                env=self.env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, expect, result.stderr)
        return json.loads(result.stdout) if expect == 0 else result.stderr

    def test_apply_touches_only_the_clock_beside_orla_menu_and_restore_brings_it_back(self):
        self.publish(plasma())
        applied = self.run_clock("apply")
        self.assertEqual(applied, {"clocks": {"22": clock.MACOS}})
        self.assertEqual(self.clock_config(22), clock.MACOS)
        # The dock panel's clock and a top panel without Orla Menu stay as they were.
        self.assertEqual(self.clock_config(50), {})
        self.assertEqual(self.clock_config(41), {})
        saved = json.loads((self.base / "state/orla/menu-bar-clock.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["previous"]["22"], dict(clock.DEFAULTS, showDate=False))
        # Applying again keeps the first saved values.
        self.run_clock("apply")
        self.assertEqual(json.loads((self.base / "state/orla/menu-bar-clock.json").read_text(encoding="utf-8")), saved)
        status = self.run_clock("status")
        self.assertTrue(status["applied"])
        restored = self.run_clock("restore")
        self.assertEqual(restored, {"clocks": {"22": dict(clock.DEFAULTS, showDate=False)}})
        self.assertFalse(self.clock_config(22)["showDate"])
        self.assertFalse((self.base / "state/orla/menu-bar-clock.json").exists())
        self.assertIn("nothing saved", self.run_clock("restore", expect=1))

    def test_without_an_orla_top_bar_apply_changes_and_saves_nothing(self):
        self.publish(plasma(with_menu=False))
        self.assertEqual(self.run_clock("apply"), {"clocks": {}})
        self.assertEqual(self.clock_config(22), {"showDate": False})
        self.assertFalse((self.base / "state/orla/menu-bar-clock.json").exists())

    def test_plasma_not_answering_is_a_finite_error(self):
        self.assertIn("not answering", self.run_clock("apply", expect=1))
        self.assertFalse((self.base / "state/orla/menu-bar-clock.json").exists())

    def test_replies_are_validated(self):
        good = {"id": 22, "panel": 36, "values": dict(clock.MACOS)}
        self.assertEqual(clock.parse_reply(repr((json.dumps({"clocks": [good]}),))), {"22": clock.MACOS})
        # Plasma may hand back the text form of typed values.
        text_form = dict(good, values=dict(clock.MACOS, showDate="true", dateDisplayFormat="1"))
        self.assertEqual(clock.parse_reply(repr((json.dumps({"clocks": [text_form]}),))), {"22": clock.MACOS})
        bad_values = [dict(clock.MACOS, dateFormat="private"), dict(clock.MACOS, customDateFormat="ddd\n"),
                      dict(clock.MACOS, customDateFormat=""), dict(clock.MACOS, dateDisplayFormat=3),
                      dict(clock.MACOS, extra=1)]
        replies = [repr((json.dumps({"clocks": [dict(good, values=v)]}),)) for v in bad_values]
        replies += [repr((json.dumps({"clocks": [good, good]}),)), repr((json.dumps({"clocks": [dict(good, x=1)]}),)),
                    repr((json.dumps([]),)), "not a tuple", repr(("{",))]
        for reply in replies:
            with self.subTest(reply=reply), self.assertRaises(clock.ClockError):
                clock.parse_reply(reply)

    def test_unknown_commands_are_refused(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/menu_bar_clock.py"), "everything"],
                                env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
