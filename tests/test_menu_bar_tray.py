import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import menu_bar_tray as tray_script  # noqa: E402
from test_menu_bar_clock import install_fake_gdbus  # noqa: E402
from test_macos_notifications import plasma  # noqa: E402

TRAY = {"extraItems": ["org.kde.plasma.volume", "org.kde.plasma.brightness", "org.kde.plasma.clipboard",
                       "org.kde.plasma.notifications"],
        "hiddenItems": ["org.kde.plasma.notifications"], "shownItems": ["org.kde.plasma.volume"],
        "knownItems": ["org.kde.plasma.volume", "org.kde.plasma.brightness", "org.kde.plasma.clipboard",
                       "org.kde.plasma.notifications"]}


class MenuBarTrayTests(unittest.TestCase):
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

    def publish(self, tray):
        (self.base / "state/fake-plasma.json").write_text(json.dumps(plasma(tray)), encoding="utf-8")

    def tray(self):
        model = json.loads((self.base / "state/fake-plasma.json").read_text(encoding="utf-8"))
        return model["panels"][0]["widgets"][0]["config"]["General"]

    def run_tray(self, command, expect=0):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/menu_bar_tray.py"), command],
                                env=self.env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, expect, result.stderr)
        return json.loads(result.stdout) if expect == 0 else result.stderr

    def test_apply_hides_duplicates_and_restore_unhides_only_those(self):
        self.publish(TRAY)
        self.run_tray("apply")
        tray = self.tray()
        self.assertEqual(tray["hiddenItems"], ["org.kde.plasma.notifications", "org.kde.plasma.brightness",
                                               "org.kde.plasma.clipboard"])
        self.assertEqual(tray["extraItems"], TRAY["extraItems"])
        self.assertEqual(self.run_tray("status")["hidden"], {"7": list(tray_script.TIDY)})
        saved = (self.base / "state/orla/menu-bar-tray.json").read_text(encoding="utf-8")
        self.run_tray("apply")
        self.assertEqual((self.base / "state/orla/menu-bar-tray.json").read_text(encoding="utf-8"), saved)
        # A later change (another presenter hidden) survives the restore.
        model = json.loads((self.base / "state/fake-plasma.json").read_text(encoding="utf-8"))
        general = model["panels"][0]["widgets"][0]["config"]["General"]
        general["hiddenItems"] = [("org.orla.notifications" if item == "org.kde.plasma.notifications" else item)
                                  for item in general["hiddenItems"]]
        (self.base / "state/fake-plasma.json").write_text(json.dumps(model), encoding="utf-8")
        self.run_tray("restore")
        self.assertEqual(self.tray()["hiddenItems"], ["org.orla.notifications"])
        self.assertFalse((self.base / "state/orla/menu-bar-tray.json").exists())
        self.assertIn("nothing saved", self.run_tray("restore", expect=1))

    def test_pinned_and_disabled_items_are_left_alone(self):
        tray = dict(TRAY, extraItems=["org.kde.plasma.volume", "org.kde.plasma.brightness"],
                    shownItems=["org.kde.plasma.volume", "org.kde.plasma.brightness"])
        self.publish(tray)
        self.run_tray("apply")
        self.assertEqual(self.tray(), tray)
        self.assertFalse((self.base / "state/orla/menu-bar-tray.json").exists())

    def test_plasma_not_answering_is_a_finite_error(self):
        self.assertIn("not answering", self.run_tray("apply", expect=1))


if __name__ == "__main__":
    unittest.main()
