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
import macos_notifications as swap  # noqa: E402
from test_menu_bar_clock import install_fake_gdbus  # noqa: E402

KDE_TRAY = {"extraItems": ["org.kde.plasma.volume", "org.kde.plasma.notifications", "org.kde.plasma.battery"],
            "hiddenItems": ["org.kde.plasma.notifications"], "shownItems": ["org.kde.plasma.volume"],
            "knownItems": ["org.kde.plasma.volume", "org.kde.plasma.notifications", "org.kde.plasma.battery"]}


def plasma(tray=None):
    return {"panels": [
        {"id": 36, "location": "top", "widgets": [
            {"id": 7, "type": "org.kde.plasma.systemtray", "config": {"General": json.loads(json.dumps(tray or KDE_TRAY))}}]},
        {"id": 32, "location": "bottom", "widgets": [{"id": 34, "type": "org.caiodock.dock", "config": {}}]}]}


class MacosNotificationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        tools = base / "bin"
        tools.mkdir()
        install_fake_gdbus(tools)
        for name in ("state", "data"):
            (base / name).mkdir()
        self.base = base
        self.env = dict(os.environ, PATH=f"{tools}{os.pathsep}{os.environ['PATH']}", XDG_STATE_HOME=str(base / "state"),
                        XDG_DATA_HOME=str(base / "data"), XDG_DATA_DIRS=str(base / "none"), QT_QPA_PLATFORM="offscreen")

    def tearDown(self):
        self.temp.cleanup()

    def publish(self, model):
        (self.base / "state/fake-plasma.json").write_text(json.dumps(model), encoding="utf-8")

    def tray(self):
        model = json.loads((self.base / "state/fake-plasma.json").read_text(encoding="utf-8"))
        return model["panels"][0]["widgets"][0]["config"]["General"]

    def install(self):
        folder = self.base / "data/plasma/plasmoids/org.orla.notifications"
        folder.mkdir(parents=True)
        (folder / "metadata.json").write_text("{}", encoding="utf-8")

    def run_swap(self, command, expect=0):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/macos_notifications.py"), command],
                                env=self.env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, expect, result.stderr)
        return json.loads(result.stdout) if expect == 0 else result.stderr

    def test_apply_replaces_kde_in_place_and_restore_brings_it_back(self):
        self.publish(plasma())
        self.assertIn("not installed", self.run_swap("apply", expect=1))
        self.assertEqual(self.tray(), KDE_TRAY)
        self.install()
        self.assertEqual(self.run_swap("status")["presenters"], {"7": swap.KDE})
        self.run_swap("apply")
        tray = self.tray()
        # Same place and the user's hidden choice; KDE's stays known, so the tray keeps it off.
        self.assertEqual(tray["extraItems"], ["org.kde.plasma.volume", swap.ORLA, "org.kde.plasma.battery"])
        self.assertEqual(tray["hiddenItems"], [swap.ORLA])
        self.assertEqual(tray["shownItems"], ["org.kde.plasma.volume"])
        self.assertIn(swap.KDE, tray["knownItems"])
        self.assertIn(swap.ORLA, tray["knownItems"])
        self.assertEqual(self.run_swap("status")["presenters"], {"7": swap.ORLA})
        saved = (self.base / "state/orla/macos-notifications.json").read_text(encoding="utf-8")
        self.run_swap("apply")  # Again: no change and the first saved lists stay.
        self.assertEqual((self.base / "state/orla/macos-notifications.json").read_text(encoding="utf-8"), saved)
        self.run_swap("restore")
        self.assertEqual(self.tray(), KDE_TRAY)
        self.assertFalse((self.base / "state/orla/macos-notifications.json").exists())
        self.assertIn("nothing saved", self.run_swap("restore", expect=1))

    def test_a_tray_without_kde_notifications_is_left_alone(self):
        self.install()
        tray = dict(KDE_TRAY, extraItems=["org.kde.plasma.volume"])
        self.publish(plasma(tray))
        self.run_swap("apply")
        self.assertEqual(self.tray(), tray)
        self.assertFalse((self.base / "state/orla/macos-notifications.json").exists())

    def test_plasma_not_answering_and_bad_replies_are_finite_errors(self):
        self.install()
        self.assertIn("not answering", self.run_swap("apply", expect=1))
        good = {"id": 7, "panel": 36, "values": KDE_TRAY}
        self.assertEqual(swap.parse_reply(repr((json.dumps({"trays": [good]}),)))["7"], KDE_TRAY)
        for bad in ({"trays": [dict(good, values=dict(KDE_TRAY, extraItems=["../x"]))]},
                    {"trays": [dict(good, values=dict(KDE_TRAY, extraItems="a,b"))]},
                    {"trays": [good, good]}, {"trays": [dict(good, extra=1)]}, []):
            with self.subTest(bad=bad), self.assertRaises(swap.SwapError):
                swap.parse_reply(repr((json.dumps(bad),)))
        with self.assertRaises(swap.SwapError):
            swap.parse_reply("not a tuple")

    def test_swapped_keeps_order_and_avoids_duplicates(self):
        values = dict(KDE_TRAY, extraItems=[swap.ORLA, swap.KDE])
        self.assertEqual(swap.swapped(values, swap.KDE, swap.ORLA)["extraItems"], [swap.ORLA])


if __name__ == "__main__":
    unittest.main()
