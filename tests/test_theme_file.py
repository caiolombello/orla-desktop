"""Selected local theme files: no Qt, services or Source checkout required."""
import importlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / "package/contents/code/theme_file.py"


class ThemeFileTests(unittest.TestCase):
    def test_selected_file_cli_returns_validated_theme(self):
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory) / "Maré ?#%.json"
            selected.write_bytes((ROOT / "themes/examples/mare.json").read_bytes())
            result = subprocess.run([sys.executable, "-I", "-B", str(READER), selected.as_uri()],
                                    cwd=directory, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            response = json.loads(result.stdout)
            self.assertIs(response["valid"], True)
            self.assertEqual(response["theme"]["id"], "org.orla.example.mare")
            self.assertEqual(response["formatVersion"], "0.1-experimental")


    def reader(self):
        module = importlib.import_module("package.contents.code.theme_file")
        self.assertTrue(Path(module.__file__).is_relative_to(ROOT))
        return module

    def test_encoded_names_are_decoded_once_without_query_or_fragment_interpretation(self):
        reader = self.reader()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("Maré espaço ?#%.json", "literal%23%3F.json", "back\\slash.json"):
                path = root / name
                path.write_bytes((ROOT / "themes/examples/mare.json").read_bytes())
                self.assertEqual(reader.load_theme_url(path.as_uri())["name"], "Maré")
            # A second decode would open literal#?.json instead of the chosen file.
            (root / "literal#?.json").write_bytes(b"not a theme")
            self.assertEqual(reader.load_theme_url((root / "literal%23%3F.json").as_uri())["id"], "org.orla.example.mare")

    def test_bad_urls_are_refused_before_any_open_and_errors_never_echo_input(self):
        reader = self.reader()
        bad = (None, b"file:///tmp/a", 1, True, "", "file:/tmp/a", "file://tmp/a",
               "file://localhost/tmp/a", "file://host/tmp/a", "file://user@host/tmp/a",
               "https://host/a", "data:text/plain,x", "qrc:/x", "/tmp/a", "FILE:///tmp/a",
               "file:////host/a", "file:///%2Fhost/a", "file:///tmp/a?", "file:///tmp/a#",
               "file:///tmp/a?secret", "file:///tmp/a#secret", "file:///tmp/a b", "file:///tmp/a\\b",
               "file:///tmp/é", "file:///tmp/%", "file:///tmp/%x0", "file:///tmp/%0", "file:///tmp/%80",
               "file:///tmp/%C0%AF", "file:///tmp/%ED%A0%80", "file:///tmp/%F4%90%80%80",
               "file:///tmp/%00", "file:///tmp/%0A", "file:///tmp/%7F", "file:///tmp/%C2%80",
               "file:///tmp/\x00", "file:///tmp/\x1f", "file:///tmp/\x7f", "file:///tmp/\x85",
               "file:///tmp/\ud800", "file:///" + "a" * 16385)
        for url in bad:
            with self.subTest(url=repr(url)), mock.patch("os.open") as opened:
                with self.assertRaises(reader.ThemeError) as failure:
                    reader.load_theme_url(url)
                self.assertEqual(failure.exception.errors, [{"field": "$", "code": "file",
                    "message": "Cannot read this regular theme file."}])
                opened.assert_not_called()

    def test_url_byte_limit_is_checked_before_loader(self):
        reader = self.reader()
        for count, should_open in ((16384, True), (16385, False)):
            url = "file:///" + "a" * (count - 8)
            self.assertEqual(len(url.encode()), count)
            with mock.patch("os.open", side_effect=OSError("synthetic")) as opened:
                with self.assertRaises(reader.ThemeError):
                    reader.load_theme_url(url)
            self.assertEqual(opened.call_count, int(should_open))

    def test_regular_loader_uses_one_descriptor_and_closes_it_after_validation(self):
        reader = self.reader()
        actual_open = os.open
        observed = []
        def opened(path, flags):
            fd = actual_open(path, flags)
            observed.append((fd, flags))
            return fd
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "selected.json"
            file.write_bytes((ROOT / "themes/examples/mare.json").read_bytes())
            with mock.patch("os.open", side_effect=opened):
                self.assertEqual(reader.load_theme_url(file.as_uri())["name"], "Maré")
            self.assertEqual(len(observed), 1)
            fd, flags = observed[0]
            self.assertEqual(flags & (os.O_NONBLOCK | os.O_NOFOLLOW), os.O_NONBLOCK | os.O_NOFOLLOW)
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_real_special_missing_and_oversize_files_are_structured_errors(self):
        reader = self.reader()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = root / "valid.json"
            valid.write_bytes((ROOT / "themes/examples/mare.json").read_bytes())
            link = root / "symlink.json"; link.symlink_to(valid)
            fifo = root / "fifo"; os.mkfifo(fifo)
            oversized = root / "oversized.json"; oversized.write_bytes(b" " * 65537)
            for path, code in ((link, "file"), (fifo, "file"), (root, "file"),
                               (root / "missing.json", "file"), (oversized, "size")):
                with self.subTest(path=path.name):
                    with self.assertRaises(reader.ThemeError) as failure:
                        reader.load_theme_url(path.as_uri())
                    self.assertEqual(failure.exception.errors[0]["code"], code)

    def test_real_theme_boundary_and_invalid_data_keep_canonical_errors(self):
        reader = self.reader()
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "input.json"
            raw = (ROOT / "themes/examples/mare.json").read_bytes()
            file.write_bytes(raw + b" " * (65536 - len(raw)))
            self.assertEqual(reader.load_theme_url(file.as_uri())["id"], "org.orla.example.mare")
            for data, code in ((file.read_bytes() + b" ", "size"), (b"\xff", "utf8"),
                               (b"\xef\xbb\xbf{}", "json"), (b'{"id":1,"id":2}', "duplicate_key"),
                               (b"[" * 5, "depth"), (b'{"formatVersion":"future"}', "required"),
                               (b'{"privatePayload":"never echo"}', "unknown_key")):
                file.write_bytes(data)
                with self.assertRaises(reader.ThemeError) as failure:
                    reader.load_theme_url(file.as_uri())
                self.assertEqual(failure.exception.errors[0]["code"], code)
                self.assertNotIn("privatePayload", str(failure.exception))
                self.assertNotIn("never echo", str(failure.exception))

    def test_cli_arity_flags_and_invalid_files_are_safe_json_with_finite_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            badfile = Path(directory) / "private-secret-file.json"
            badfile.write_bytes(b'{"secret-content":true}')
            for argv, code in (([], 2), (["--unknown-secret"], 2),
                               ([badfile.as_uri(), "private-extra"], 2),
                               ([badfile.as_uri()], 1), (["file:///private-secret#x"], 1)):
                result = subprocess.run([sys.executable, "-I", "-B", str(READER), *argv], cwd=directory,
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, code)
                self.assertEqual(result.stderr, "")
                response = json.loads(result.stdout)
                self.assertEqual(set(response), {"formatVersion", "valid", "errors"})
                self.assertIs(response["valid"], False)
                self.assertLessEqual(len(result.stdout.encode()), 65536)
                for private in ("private-secret", "private-extra", "secret-content", str(badfile)):
                    self.assertNotIn(private, result.stdout)

    def test_installed_pair_runs_after_its_source_copy_is_removed_with_isolated_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source"; installed = root / "installed"
            source.mkdir(); installed.mkdir(); elsewhere = root / "elsewhere"; elsewhere.mkdir()
            for name in ("theme_format.py", "theme_file.py"):
                shutil.copy2(ROOT / "package/contents/code" / name, source / name)
                shutil.copy2(source / name, installed / name)
            shutil.rmtree(source)
            self.assertFalse(source.exists())
            self.assertEqual(sorted(x.name for x in installed.iterdir()), ["theme_file.py", "theme_format.py"])
            selected = root / "Maré ?.json"; selected.write_bytes((ROOT / "themes/examples/mare.json").read_bytes())
            env = dict(os.environ, PYTHONPATH="/absent/source/scripts:/absent/launcher")
            result = subprocess.run([sys.executable, "-I", "-B", str(installed / "theme_file.py"), selected.as_uri()],
                                    cwd=elsewhere, env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertEqual(json.loads(result.stdout)["theme"]["name"], "Maré")

    def test_existing_package_builder_includes_installed_pair_without_service(self):
        from scripts import caiodock
        self.assertTrue(Path(caiodock.__file__).is_relative_to(ROOT))
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            archive = caiodock.build(ROOT, Path(directory))
            with zipfile.ZipFile(archive) as zipped:
                names = set(zipped.namelist())
                self.assertIn("LICENSE", names)
                for name in ("contents/code/theme_format.py", "contents/code/theme_file.py"):
                    self.assertEqual(zipped.read(name), (ROOT / "package" / name).read_bytes())
                self.assertFalse(any(name.endswith(".service") for name in names))
                installed = Path(directory) / "installed"
                installed.mkdir()
                for name in ("theme_format.py", "theme_file.py"):
                    (installed / name).write_bytes(zipped.read("contents/code/" + name))
                self.assertFalse((installed / "scripts").exists())
                self.assertFalse((installed / "launcher").exists())
                selected = Path(directory) / "selected.json"
                selected.write_bytes((ROOT / "themes/examples/mare.json").read_bytes())
                result = subprocess.run([sys.executable, "-I", "-B", str(installed / "theme_file.py"),
                                         selected.as_uri()], cwd=directory, capture_output=True,
                                        text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["theme"]["name"], "Maré")


if __name__ == "__main__":
    unittest.main()
