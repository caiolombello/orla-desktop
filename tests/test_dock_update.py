import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dock_update  # noqa: E402


def plasmoid(version, *, package_id="org.caiodock.dock", minimum="6.7"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("metadata.json", json.dumps({"KPlugin": {"Id": package_id, "Version": version},
                                                      "X-Plasma-API-Minimum-Version": minimum}))
        archive.writestr("LICENSE", "MIT\n")
        archive.writestr("contents/ui/main.qml", f"// {version}\n")
        archive.writestr("contents/code/integrations.py", "\n")
    return buffer.getvalue()


def sums(version, data):
    return f"{hashlib.sha256(data).hexdigest()}  orla-dock-{version}.plasmoid\n".encode()


class DockUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.home = base / "data"
        patcher = mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(base / "state"), "XDG_DATA_HOME": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.installs = []
        self.fail_install = False
        self.install(io.BytesIO(plasmoid("0.2.11")))
        self.files = {}
        self.publish("0.2.12", plasmoid("0.2.12"))

    def tearDown(self):
        self.temp.cleanup()

    # A stand-in for kpackagetool6: extract the archive over the installed package.
    def install(self, source, home=None):
        data = source.read() if hasattr(source, "read") else Path(source).read_bytes()
        target = (home or self.home) / "plasma/plasmoids/org.caiodock.dock"
        if self.fail_install:
            if target.exists():
                (target / "metadata.json").write_text("broken", encoding="utf-8")
            raise RuntimeError("kpackagetool6 failed")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            archive.extractall(target)
        self.installs.append(json.loads((target / "metadata.json").read_text())["KPlugin"]["Version"])

    def publish(self, version, data, checksum=None):
        plasmoid_url, sums_url = dock_update.asset_urls(version)
        self.files[plasmoid_url] = data
        self.files[sums_url] = checksum if checksum is not None else sums(version, data)
        self.available = version

    def fetcher(self, url, limit):
        data = self.files[url]
        if len(data) > limit:
            raise dock_update.UpdateError("release file is larger than expected")
        return data

    def check(self, installed, channel):
        return ({"status": "update_available", "available_version": self.available}
                if self.available != installed else {"status": "up_to_date"})

    def apply(self, plasma=(6, 7, 5)):
        return dock_update.apply("beta", home=self.home, check=self.check, fetcher=self.fetcher,
                                 installer=self.install, plasma=lambda: plasma)

    def test_apply_installs_the_verified_release_and_keeps_the_previous(self):
        self.assertEqual(self.apply(), {"status": "updated", "from": "0.2.11", "to": "0.2.12"})
        self.assertEqual(dock_update.installed_version(self.home), "0.2.12")
        record = dock_update.read_record()
        self.assertEqual((record["phase"], record["from"], record["to"]), ("applied", "0.2.11", "0.2.12"))
        kept = Path(record["kept"])
        self.assertTrue(kept.is_file())
        with zipfile.ZipFile(kept) as archive:
            self.assertEqual(json.loads(archive.read("metadata.json"))["KPlugin"]["Version"], "0.2.11")
        # Nothing new: no download and no change.
        self.files.clear()
        self.assertEqual(self.apply()["status"], "up_to_date")
        # Going back reinstalls the kept version.
        self.assertEqual(dock_update.rollback(home=self.home, installer=self.install)["installed"], "0.2.11")
        self.assertEqual(dock_update.read_record()["phase"], "rolled_back")

    def test_invalid_releases_are_refused_before_anything_changes(self):
        cases = {
            "hash": lambda: self.publish("0.2.12", plasmoid("0.2.12"), sums("0.2.12", b"other")),
            "sums_twice": lambda: self.publish("0.2.12", plasmoid("0.2.12"),
                                               sums("0.2.12", plasmoid("0.2.12")) * 2),
            "version": lambda: self.publish("0.2.12", plasmoid("0.2.13")),
            "id": lambda: self.publish("0.2.12", plasmoid("0.2.12", package_id="org.example.other")),
            "plasma": lambda: self.publish("0.2.12", plasmoid("0.2.12", minimum="6.9")),
            "not_zip": lambda: self.publish("0.2.12", b"not a zip"),
        }
        for name, prepare in cases.items():
            with self.subTest(name=name):
                prepare()
                with self.assertRaises(dock_update.UpdateError):
                    self.apply()
                self.assertEqual(dock_update.installed_version(self.home), "0.2.11")
                self.assertEqual(self.installs, ["0.2.11"])
                self.assertIsNone(dock_update.read_record())

    def test_a_failed_install_puts_the_previous_version_back(self):
        original = self.install
        calls = []

        def flaky(source, home=None):
            calls.append(source)
            self.fail_install = len(calls) == 1
            return original(source, home)
        with self.assertRaises(dock_update.UpdateError) as error:
            dock_update.apply("beta", home=self.home, check=self.check, fetcher=self.fetcher,
                              installer=flaky, plasma=lambda: (6, 7, 5))
        self.assertIn("previous version restored", str(error.exception))
        self.assertEqual(dock_update.installed_version(self.home), "0.2.11")
        self.assertEqual(dock_update.read_record()["phase"], "rolled_back")

    def test_not_installed_and_missing_kept_version_are_finite_errors(self):
        with self.assertRaises(dock_update.UpdateError):
            dock_update.apply("beta", home=Path(self.temp.name) / "empty", check=self.check, fetcher=self.fetcher,
                              installer=self.install, plasma=lambda: (6, 7, 5))
        with self.assertRaises(dock_update.UpdateError):
            dock_update.rollback(home=self.home, installer=self.install)

    def test_downloads_stay_on_official_https_hosts(self):
        for url in ("http://github.com/caiolombello/orla-desktop/releases/download/v1.0.0/SHA256SUMS",
                    "https://example.invalid/SHA256SUMS", "file:///etc/passwd"):
            with self.subTest(url=url), self.assertRaises(dock_update.UpdateError):
                dock_update.fetch(url, 10)
        handler = dock_update._ReleaseRedirects()
        with self.assertRaises(dock_update.UpdateError):
            handler.redirect_request(None, None, 302, "Found", {}, "https://example.invalid/x")
        self.assertEqual(dock_update.asset_urls("0.2.12")[0],
                         "https://github.com/caiolombello/orla-desktop/releases/download/v0.2.12/orla-dock-0.2.12.plasmoid")


if __name__ == "__main__":
    unittest.main()
