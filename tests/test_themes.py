import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import themes


def example():
    return {
        "formatVersion": "0.1-experimental",
        "id": "org.orla.essential",
        "name": "Essencial",
        "author": "Orla contributors",
        "license": "MIT",
        "version": "1.0.0",
        "tokens": {
            "foreground": "#EEEEEE", "muted": "#AAbBcC",
            "accent": "#66BBFF", "surface": "#111111", "border": "#444444",
            "radius": 12, "spacing": 4, "opacity": 1,
            "iconSize": 36, "reducedMotion": True,
        },
    }


class ThemeTests(unittest.TestCase):
    def assert_error(self, data, code, field=None):
        with self.assertRaises(themes.ThemeError) as failure:
            themes.parse_theme(data)
        self.assertEqual(failure.exception.errors[0]["code"], code)
        if field is not None:
            self.assertEqual(failure.exception.errors[0]["field"], field)

    def test_author_can_validate_data_and_receives_normalized_colors(self):
        source = example()
        result = themes.parse_theme(json.dumps(source).encode("utf-8"))
        self.assertEqual(result["tokens"]["muted"], "#aabbcc")
        self.assertEqual(result["tokens"]["foreground"], "#eeeeee")
        self.assertIs(result["tokens"]["reducedMotion"], True)
        self.assertEqual(source["tokens"]["foreground"], "#EEEEEE")

    def test_untrusted_json_has_limits_and_unambiguous_keys(self):
        self.assert_error(b" " * 65537, "size")
        self.assert_error(b'"\xff"', "utf8")
        self.assert_error(b"\xef\xbb\xbf{}", "json")
        self.assert_error(b"{" , "json")
        self.assert_error(b"[" * 2000 + b"0" + b"]" * 2000, "depth")
        self.assert_error(b'{"id":"a.b","id":"c.d"}', "duplicate_key", "$/id")
        source = json.dumps(example()).replace('"radius": 12', '"radius": 12, "radius": 3')
        self.assert_error(source.encode(), "duplicate_key", "$/tokens/radius")
        for value in ("NaN", "Infinity", "-Infinity", "1e9999"):
            source = json.dumps(example()).replace('"radius": 12', '"radius": ' + value)
            self.assert_error(source.encode(), "nonfinite")

    def test_size_boundary_and_numeric_endpoints_remain_usable(self):
        encoded = json.dumps(example()).encode("utf-8")
        padded = encoded + b" " * (65536 - len(encoded))
        self.assertEqual(themes.parse_theme(padded)["id"], "org.orla.essential")
        self.assert_error(padded + b" ", "size")
        for radius, spacing, opacity, icon in ((0, 0, 0.4, 24), (32, 16, 1, 64),
                                              (1.5, 2.5, 0.75, 42.5)):
            with self.subTest(radius=radius):
                source = example()
                source["tokens"].update(radius=radius, spacing=spacing, opacity=opacity, iconSize=icon)
                result = themes.parse_theme(json.dumps(source).encode())
                self.assertEqual(result["tokens"]["iconSize"], icon)
                self.assertEqual(result["tokens"]["opacity"], opacity)
        source = example()
        source["name"] = "Maré"
        self.assertIn(b'Mar\xc3\xa9', themes.canonical_bytes(source))

    def test_file_reads_are_bounded_and_special_files_do_not_block(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            oversized = root / "oversized.json"
            with oversized.open("wb") as stream:
                stream.truncate(65537)
            with self.assertRaises(themes.ThemeError) as error:
                themes.load_theme(oversized)
            self.assertEqual(error.exception.errors[0]["code"], "size")
            fifo = root / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(themes.ThemeError) as error:
                themes.load_theme(fifo)
            self.assertEqual(error.exception.errors[0]["code"], "file")
            with self.assertRaises(themes.ThemeError):
                themes.load_theme(root)
            with self.assertRaises(themes.ThemeError):
                themes.load_theme(root / "missing")

    def test_community_examples_are_valid_and_pack_offline(self):
        examples = Path(__file__).resolve().parents[1] / "themes/examples"
        with tempfile.TemporaryDirectory() as temporary:
            outputs = []
            for source in sorted(examples.glob("*.json")):
                with self.subTest(source=source.name):
                    theme = themes.load_theme(source)
                    self.assertEqual(theme["license"], "MIT")
                    outputs.append(themes.pack_theme(source, Path(temporary)))
            self.assertEqual(len(outputs), 2)
            self.assertEqual({themes.load_theme(path)["name"] for path in outputs}, {"Essencial", "Maré"})

    def test_invalid_data_cannot_smuggle_code_assets_or_paths(self):
        for key, value, code in (
            ("id", "../../escape", "format"),
            ("id", "org.Orla.theme", "format"),
            ("version", "../../escape", "format"),
            ("formatVersion", "0.1", "format_version"),
            ("name", "<script>alert(1)</script>", "format"),
            ("author", "eval(1)", "format"),
            ("license", "https://example.org", "format"),
            ("name", "A\u0000B", "format"),
            ("author", "A\ud800B", "format"),
            ("name", " ", "format"),
            ("name", "x" * 121, "length"),
            ("assets", {"icon": "../../private"}, "unknown_key"),
            ("imports", ["QtQuick"], "unknown_key"),
            ("qml", "Item {}", "unknown_key"),
        ):
            with self.subTest(key=key, value=value):
                source = example()
                source[key] = value
                self.assert_error(json.dumps(source).encode(), code)

    def test_tokens_are_complete_and_strictly_typed_with_finite_bounds(self):
        for key, value, code in (
            ("radius", True, "type"), ("opacity", False, "type"),
            ("radius", -1, "range"), ("radius", 33, "range"),
            ("spacing", 17, "range"), ("spacing", -1, "range"),
            ("opacity", 0.39, "range"), ("opacity", 1.01, "range"),
            ("iconSize", 23, "range"), ("iconSize", 65, "range"),
            ("reducedMotion", 1, "type"), ("reducedMotion", "true", "type"),
            ("accent", "#fff", "format"), ("surface", "#11223344", "length"),
            ("foreground", "Qt.rgba(1,1,1,1)", "length"),
            ("font", "https://example.org/font.ttf", "unknown_key"),
        ):
            with self.subTest(key=key, value=value):
                source = example()
                source["tokens"][key] = value
                self.assert_error(json.dumps(source).encode(), code)
        source = example()
        del source["tokens"]["accent"]
        self.assert_error(json.dumps(source).encode(), "required", "$/tokens/accent")
        self.assert_error(b"null", "type", "$")
        self.assert_error(b"[]", "type", "$")

    def test_packed_theme_is_reproducible_without_overwriting_other_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            source.write_text(json.dumps(example()), encoding="utf-8")
            first = themes.pack_theme(source, root / "one")
            self.assertEqual(first.name, "org.orla.essential-1.0.0.orla-theme.json")
            expected = (
                '{"author":"Orla contributors","formatVersion":"0.1-experimental",'
                '"id":"org.orla.essential","license":"MIT","name":"Essencial",'
                '"tokens":{"accent":"#66bbff","border":"#444444","foreground":"#eeeeee",'
                '"iconSize":36,"muted":"#aabbcc","opacity":1,"radius":12,"reducedMotion":true,'
                '"spacing":4,"surface":"#111111"},"version":"1.0.0"}\n'
            ).encode("utf-8")
            self.assertEqual(first.read_bytes(), expected)
            alternate = example()
            alternate["tokens"]["radius"] = 12.0
            alternate["tokens"]["opacity"] = 1.0
            alternate["tokens"]["spacing"] = 4.0
            alternate["tokens"]["muted"] = "#aabbcc"
            source.write_text(json.dumps(dict(reversed(list(alternate.items())))), encoding="utf-8")
            second = themes.pack_theme(source, root / "two")
            self.assertEqual(second.read_bytes(), expected)
            first.write_bytes(b"existing user data")
            with self.assertRaises(themes.ThemeError) as error:
                themes.pack_theme(source, root / "one")
            self.assertEqual(error.exception.errors[0]["code"], "exists")
            self.assertEqual(first.read_bytes(), b"existing user data")
            self.assertEqual(list(first.parent.iterdir()), [first])

    def test_failed_pack_does_not_create_output_or_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            source.write_bytes(b'{}')
            with self.assertRaises(themes.ThemeError):
                themes.pack_theme(source, root / "absent")
            self.assertFalse((root / "absent").exists())
            source.write_text(json.dumps(example()), encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(source)
            with self.assertRaises(themes.ThemeError) as error:
                themes.load_theme(link)
            self.assertEqual(error.exception.errors[0]["code"], "file")
            output = root / "output"
            output.mkdir()
            victim = root / "victim"
            victim.write_bytes(b"preserve")
            (output / "org.orla.essential-1.0.0.orla-theme.json").symlink_to(victim)
            with self.assertRaises(themes.ThemeError):
                themes.pack_theme(source, output)
            self.assertEqual(victim.read_bytes(), b"preserve")
            self.assertEqual(len(list(output.iterdir())), 1)
            directory_link = root / "directory-link"
            directory_link.symlink_to(output, target_is_directory=True)
            with self.assertRaises(themes.ThemeError):
                themes.pack_theme(source, directory_link)

    def test_failed_os_write_leaves_no_artifact_and_retry_succeeds(self):
        child = """
import json
from pathlib import Path
import resource
import signal
import sys
from scripts import themes

source, output = map(Path, sys.argv[1:])
original = resource.getrlimit(resource.RLIMIT_FSIZE)
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE, (150, original[1]))
code = None
try:
    themes.pack_theme(source, output)
except themes.ThemeError as error:
    code = error.errors[0]["code"]
finally:
    resource.setrlimit(resource.RLIMIT_FSIZE, original)
after_failure = sorted(path.name for path in output.iterdir())
retry = themes.pack_theme(source, output)
print(json.dumps({"code": code, "afterFailure": after_failure,
                  "afterRetry": sorted(path.name for path in output.iterdir()),
                  "themeId": themes.load_theme(retry)["id"], "bytes": retry.stat().st_size}))
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.json"
            source.write_text(json.dumps(example()), encoding="utf-8")
            result = subprocess.run([sys.executable, "-B", "-c", child, str(source), str(root / "output")],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = json.loads(result.stdout)
            self.assertEqual(result["code"], "output")
            self.assertEqual(result["afterFailure"], [])
            self.assertEqual(result["afterRetry"], ["org.orla.essential-1.0.0.orla-theme.json"])
            self.assertEqual(result["themeId"], "org.orla.essential")
            self.assertGreater(result["bytes"], 150)

    def test_malformed_paths_are_structured_io_errors_without_hiding_type_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.json"
            source.write_text(json.dumps(example()), encoding="utf-8")
            for value in ("bad\x00path", "bad\ud800path"):
                with self.subTest(value=repr(value)):
                    with self.assertRaises(themes.ThemeError) as error:
                        themes.load_theme(Path(value))
                    self.assertEqual(error.exception.errors[0]["code"], "file")
                    with self.assertRaises(themes.ThemeError) as error:
                        themes.pack_theme(source, root / value)
                    self.assertEqual(error.exception.errors[0]["code"], "output")
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        self.assertEqual(themes.main(["validate", value, "--json"]), 1)
                        self.assertEqual(themes.main(["pack", str(source), "--output", value]), 1)
                    self.assertEqual(json.loads(stdout.getvalue())["errors"][0]["code"], "file")
                    self.assertNotIn("Traceback", stderr.getvalue())
            with self.assertRaises(TypeError):
                themes.load_theme(None)
            with self.assertRaises(TypeError):
                themes.pack_theme(source, None)

    def test_cli_returns_structured_errors_and_packs_a_real_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.json"
            source.write_bytes(b'{"tokens":{"radius":NaN}}')
            command = [sys.executable, "-B", "scripts/themes.py", "validate", str(source), "--json"]
            invalid = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(invalid.returncode, 1)
            error = json.loads(invalid.stdout)
            self.assertIs(error["valid"], False)
            self.assertEqual(error["errors"][0]["code"], "nonfinite")
            self.assertNotIn("Traceback", invalid.stderr)
            source.write_text(json.dumps(example()), encoding="utf-8")
            valid = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertIs(json.loads(valid.stdout)["valid"], True)
            pack = subprocess.run([sys.executable, "-B", "scripts/themes.py", "pack", str(source),
                                   "--output", str(root / "packed")], capture_output=True, text=True)
            self.assertEqual(pack.returncode, 0, pack.stderr)
            packed = root / "packed" / "org.orla.essential-1.0.0.orla-theme.json"
            self.assertTrue(packed.is_file())
            self.assertEqual(themes.load_theme(packed)["id"], "org.orla.essential")


if __name__ == "__main__":
    unittest.main()
