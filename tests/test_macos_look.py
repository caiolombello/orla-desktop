import configparser
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
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_menu_bar_clock import install_fake_gdbus, plasma  # noqa: E402

# Fake KDE tools: they edit INI files under XDG_CONFIG_HOME and log D-Bus calls.
FAKE_KWRITECONFIG = textwrap.dedent("""\
    #!/usr/bin/env python3
    import configparser, os, sys
    args = sys.argv[1:]
    path = os.path.join(os.environ["XDG_CONFIG_HOME"], args[args.index("--file") + 1])
    group, key = args[args.index("--group") + 1], args[args.index("--key") + 1]
    with open(os.path.join(os.environ["XDG_STATE_HOME"], "kwriteconfig.log"), "a") as log:
        log.write(" ".join(args) + "\\n")
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read(path)
    if "--delete" in args:
        if config.has_section(group):
            config.remove_option(group, key)
    else:
        if not config.has_section(group):
            config.add_section(group)
        config.set(group, key, args[-1])
    with open(path, "w") as handle:
        config.write(handle, space_around_delimiters=False)
    """)
FAKE_KREADCONFIG = textwrap.dedent("""\
    #!/usr/bin/env python3
    import configparser, os, sys
    args = sys.argv[1:]
    path = os.path.join(os.environ["XDG_CONFIG_HOME"], args[args.index("--file") + 1])
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read(path)
    group, key = args[args.index("--group") + 1], args[args.index("--key") + 1]
    print(config.get(group, key, fallback=""))
    """)
# Logs every call and answers isEffectLoaded like busctl; magiclamp loads unless
# the test leaves a "no-magiclamp" marker, as on a KWin built without it, and a
# "no-answer" marker makes the query print nothing.
FAKE_BUSCTL = textwrap.dedent("""\
    #!/bin/sh
    echo "$@" >> "$XDG_STATE_HOME/busctl.log"
    case "$*" in
        *isEffectLoaded*) [ -e "$XDG_STATE_HOME/no-answer" ] && exit 0 ;;
    esac
    case "$*" in
        *"isEffectLoaded s magiclamp"*)
            if [ -e "$XDG_STATE_HOME/no-magiclamp" ]; then echo "b false"; else echo "b true"; fi ;;
        *isEffectLoaded*) echo "b true" ;;
    esac
    """)
FAKE_APPLY_THEME = textwrap.dedent("""\
    #!/usr/bin/env python3
    import configparser, os, sys
    path = os.path.join(os.environ["XDG_CONFIG_HOME"], "plasmarc")
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read(path)
    if not config.has_section("Theme"):
        config.add_section("Theme")
    config.set("Theme", "name", sys.argv[1])
    with open(path, "w") as handle:
        config.write(handle, space_around_delimiters=False)
    """)


class MacosLookTests(unittest.TestCase):
    """apply/restore across the theme, the decoration and KWin, in a private home."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        tools = base / "bin"
        tools.mkdir()
        for name, body in (("kwriteconfig6", FAKE_KWRITECONFIG), ("kreadconfig6", FAKE_KREADCONFIG),
                           ("plasma-apply-desktoptheme", FAKE_APPLY_THEME),
                           ("busctl", FAKE_BUSCTL),
                           # No package tool here: macos_look keeps KDE's notifications.
                           ("kpackagetool6", "#!/bin/sh\nexit 1\n")):
            path = tools / name
            path.write_text(body, encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
        install_fake_gdbus(tools)
        self.env = dict(os.environ, PATH=f"{tools}{os.pathsep}{os.environ['PATH']}",
                        XDG_CONFIG_HOME=str(base / "config"), XDG_DATA_HOME=str(base / "data"),
                        XDG_STATE_HOME=str(base / "state"))
        for key in ("config", "data", "state"):
            (base / key).mkdir()
        (base / "config/kwinrc").write_text("[TabBox]\nLayoutName=thumbnail_grid\n", encoding="utf-8")
        (base / "config/plasmarc").write_text("[Theme]\nname=breeze-dark\n", encoding="utf-8")
        (base / "state/fake-plasma.json").write_text(json.dumps(plasma()), encoding="utf-8")
        self.base = base

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, name, *args, expect=0):
        result = subprocess.run([sys.executable, str(SCRIPTS / name), *args], env=self.env,
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, expect, result.stderr)
        return result.stdout

    def ini(self, name):
        config = configparser.ConfigParser(interpolation=None)
        config.optionxform = str
        config.read(self.base / "config" / name)
        return {section: dict(config[section]) for section in config.sections()}

    def test_apply_then_restore_returns_every_setting(self):
        before_kwin, before_plasma = self.ini("kwinrc"), self.ini("plasmarc")
        self.run_script("macos_look.py", "apply")
        kwin = self.ini("kwinrc")
        self.assertEqual(kwin["TabBox"], {"LayoutName": "big_icons", "ApplicationsMode": "1", "HighlightWindows": "false"})
        self.assertEqual(kwin["Plugins"], {"magiclampEnabled": "true", "squashEnabled": "false"})
        self.assertEqual(kwin["Effect-overview"], {"BorderActivate": "7"})
        self.assertEqual(kwin["ElectricBorders"], {"BottomRight": "ShowDesktop"})
        self.assertEqual(kwin["org.kde.kdecoration2"]["ButtonsOnLeft"], "XIA")
        self.assertTrue(kwin["org.kde.kdecoration2"]["theme"].startswith("kwin4_decoration_qml_orla_"))
        self.assertEqual(self.ini("plasmarc")["Theme"]["name"], "orla")
        self.assertTrue((self.base / "data/plasma/desktoptheme/orla/metadata.json").exists())
        status = json.loads(self.run_script("macos_look.py", "status"))
        self.assertTrue(status["kwinApplied"])
        self.assertEqual(status["minimize"], "magiclamp")
        self.assertTrue(status["krunnerApplied"])
        # KRunner floats like Spotlight; it was not configured before.
        self.assertEqual(self.ini("krunnerrc")["General"], {"FreeFloating": "true"})
        self.assertFalse(any("krunnerrc" in line and "--notify" not in line for line in self.writes()))
        self.assertEqual(self.top_clock()["dateFormat"], "custom")
        # Effects switch now, not only after the next login.
        log = (self.base / "state/busctl.log").read_text(encoding="utf-8")
        self.assertIn("loadEffect s magiclamp", log)
        self.assertIn("unloadEffect s squash", log)
        # A second apply keeps the original saved state.
        self.run_script("macos_look.py", "apply")
        self.run_script("macos_look.py", "restore")
        after = self.ini("kwinrc")
        # Sections left empty by the restore are harmless; their keys match.
        self.assertEqual({k: v for k, v in after.items() if v}, before_kwin)
        # FreeFloating did not exist, so restore deletes it again.
        self.assertEqual({k: v for k, v in self.ini("krunnerrc").items() if v}, {})
        self.assertEqual(self.ini("plasmarc"), before_plasma)
        self.assertFalse((self.base / "state/orla/macos-look.json").exists())
        self.assertEqual(self.top_clock(), {"showDate": False, "dateFormat": "shortDate",
                                            "customDateFormat": "ddd d", "dateDisplayFormat": 0})
        log = (self.base / "state/busctl.log").read_text(encoding="utf-8").splitlines()
        # KWin's defaults come back: Magic Lamp off, Squash on.
        self.assertIn("--user call org.kde.KWin /Effects org.kde.kwin.Effects unloadEffect s magiclamp", log[-4:])
        self.assertIn("--user call org.kde.KWin /Effects org.kde.kwin.Effects loadEffect s squash", log[-4:])
        # Restoring again changes nothing and does not fail.
        self.run_script("macos_look.py", "restore")
        self.assertEqual(self.ini("plasmarc"), before_plasma)

    def writes(self):
        path = self.base / "state/kwriteconfig.log"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    def saved(self):
        return json.loads((self.base / "state/orla/macos-look.json").read_text(encoding="utf-8"))

    def test_krunner_keeps_the_users_own_values(self):
        krunner = "[General]\nFreeFloating=false\nHistoryBehavior=Disabled\n"
        (self.base / "config/krunnerrc").write_text(krunner, encoding="utf-8")
        self.run_script("macos_look.py", "apply")
        # History stays as the user chose; only the position changes.
        self.assertEqual(self.ini("krunnerrc")["General"],
                         {"FreeFloating": "true", "HistoryBehavior": "Disabled"})
        self.assertEqual(self.saved()["krunner"], {"General/FreeFloating": "false"})
        self.run_script("macos_look.py", "apply")
        self.assertEqual(self.saved()["krunner"], {"General/FreeFloating": "false"})
        self.run_script("macos_look.py", "restore")
        self.assertEqual(self.ini("krunnerrc")["General"],
                         {"FreeFloating": "false", "HistoryBehavior": "Disabled"})

    def test_state_saved_before_krunner_restores_without_touching_it(self):
        # A state from an apply that predates KRunner has no entry for it.
        state = self.base / "state/orla/macos-look.json"
        state.parent.mkdir(parents=True)
        previous = {"TabBox/LayoutName": "thumbnail_grid"}
        state.write_text(json.dumps({"previous": previous}), encoding="utf-8")
        (self.base / "config/krunnerrc").write_text("[General]\nFreeFloating=true\n", encoding="utf-8")
        self.run_script("macos_look.py", "restore")
        self.assertEqual(self.ini("krunnerrc")["General"], {"FreeFloating": "true"})
        self.assertFalse(any("krunnerrc" in line for line in self.writes()))
        # Applying again over such a state records KRunner's value then.
        state.write_text(json.dumps({"previous": previous}), encoding="utf-8")
        (self.base / "config/krunnerrc").write_text("[General]\nFreeFloating=false\n", encoding="utf-8")
        self.run_script("macos_look.py", "apply")
        self.assertEqual(self.saved(), {"previous": previous, "minimize": "magiclamp",
                                        "krunner": {"General/FreeFloating": "false"}})

    def test_missing_magic_lamp_falls_back_to_squash(self):
        (self.base / "state/no-magiclamp").touch()
        before_kwin = self.ini("kwinrc")
        result = subprocess.run([sys.executable, str(SCRIPTS / "macos_look.py"), "apply"], env=self.env,
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Magic Lamp unavailable", result.stderr)
        kwin = self.ini("kwinrc")
        self.assertEqual(kwin["Plugins"], {"magiclampEnabled": "false", "squashEnabled": "true"})
        # The rest of the look still applies.
        self.assertEqual(kwin["TabBox"]["LayoutName"], "big_icons")
        log = (self.base / "state/busctl.log").read_text(encoding="utf-8").splitlines()
        self.assertIn("--user call org.kde.KWin /Effects org.kde.kwin.Effects loadEffect s squash", log[-2:])
        self.assertIn("--user call org.kde.KWin /Effects org.kde.kwin.Effects unloadEffect s magiclamp", log[-2:])
        status = json.loads(self.run_script("macos_look.py", "status"))
        self.assertEqual(status["minimize"], "squash")
        self.assertTrue(status["kwinApplied"])
        # The original values survive the fallback and a second apply.
        self.assertEqual(status["saved"]["previous"]["TabBox/LayoutName"], "thumbnail_grid")
        self.assertIsNone(status["saved"]["previous"]["Plugins/magiclampEnabled"])
        self.run_script("macos_look.py", "apply")
        self.assertEqual(self.saved()["previous"], status["saved"]["previous"])
        # Once KWin can load it, applying again switches to Magic Lamp.
        (self.base / "state/no-magiclamp").unlink()
        self.run_script("macos_look.py", "apply")
        self.assertEqual(self.ini("kwinrc")["Plugins"], {"magiclampEnabled": "true", "squashEnabled": "false"})
        self.assertEqual(json.loads(self.run_script("macos_look.py", "status"))["minimize"], "magiclamp")
        self.run_script("macos_look.py", "restore")
        self.assertEqual({k: v for k, v in self.ini("kwinrc").items() if v}, before_kwin)

    def test_unanswered_effect_query_switches_nothing(self):
        (self.base / "state/no-answer").touch()
        self.run_script("macos_look.py", "apply")
        # Without KWin's answer Magic Lamp stays configured, and status is honest.
        self.assertEqual(self.ini("kwinrc")["Plugins"], {"magiclampEnabled": "true", "squashEnabled": "false"})
        status = json.loads(self.run_script("macos_look.py", "status"))
        self.assertEqual(status["minimize"], "unverified")
        self.assertTrue(status["kwinApplied"])

    def top_clock(self):
        model = json.loads((self.base / "state/fake-plasma.json").read_text(encoding="utf-8"))
        return model["panels"][0]["widgets"][1]["config"]["Appearance"]

    def test_apply_without_plasma_skips_only_the_clock(self):
        (self.base / "state/fake-plasma.json").unlink()
        self.run_script("macos_look.py", "apply")
        self.assertEqual(self.ini("plasmarc")["Theme"]["name"], "orla")
        self.assertFalse((self.base / "state/orla/menu-bar-clock.json").exists())

    def test_theme_restore_without_saved_state_leaves_the_theme_alone(self):
        self.run_script("plasma_theme.py", "restore", expect=1)
        self.assertEqual(self.ini("plasmarc")["Theme"]["name"], "breeze-dark")

    def test_unknown_commands_are_refused(self):
        self.run_script("macos_look.py", expect=2)
        self.run_script("macos_look.py", "everything", expect=2)


if __name__ == "__main__":
    unittest.main()
