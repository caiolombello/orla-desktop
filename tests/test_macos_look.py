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
                           ("busctl", "#!/bin/sh\necho \"$@\" >> \"$XDG_STATE_HOME/busctl.log\"\n")):
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
        self.assertEqual(kwin["org.kde.kdecoration2"]["ButtonsOnLeft"], "XIA")
        self.assertTrue(kwin["org.kde.kdecoration2"]["theme"].startswith("kwin4_decoration_qml_orla_"))
        self.assertEqual(self.ini("plasmarc")["Theme"]["name"], "orla")
        self.assertTrue((self.base / "data/plasma/desktoptheme/orla/metadata.json").exists())
        status = json.loads(self.run_script("macos_look.py", "status"))
        self.assertTrue(status["kwinApplied"])
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
