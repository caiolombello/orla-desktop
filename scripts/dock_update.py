"""Update the installed Orla Dock from the official releases, and go back.

Trust (chosen by the maintainer on 25/10/2026): HTTPS from the official
repository on GitHub plus the SHA256SUMS published in the same release, the
same trust as the README install path. Artifacts are not signed yet.

  apply     download the newest release of the channel, verify it, keep the
            installed version as a .plasmoid, install, and go back on failure
  rollback  reinstall the version kept by the last apply
  status    installed version and the last update record
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

if __package__:
    from . import caiodock
else:
    import caiodock

REPOSITORY = "caiolombello/orla-desktop"
RELEASE_HOSTS = frozenset(("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"))
PLASMOID_LIMIT = 8 * 1024 * 1024
SUMS_LIMIT = 4096
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?")


class UpdateError(Exception):
    pass


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share").expanduser()


def state_dir() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state").expanduser() / "orla" / "dock-update"


def installed_dir(home: Path) -> Path:
    return home / "plasma" / "plasmoids" / caiodock.PACKAGE_ID


def installed_version(home: Path) -> str | None:
    path = installed_dir(home) / "metadata.json"
    try:
        version = json.loads(path.read_text(encoding="utf-8"))["KPlugin"]["Version"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return version if isinstance(version, str) and VERSION.fullmatch(version) else None


class _ReleaseRedirects(urllib.request.HTTPRedirectHandler):
    """GitHub serves release assets through a redirect; only its HTTPS hosts are followed."""
    def redirect_request(self, request, fp, code, message, headers, url):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in RELEASE_HOSTS:
            raise UpdateError("release download left the official hosts")
        return super().redirect_request(request, fp, code, message, headers, url)


def fetch(url: str, limit: int, timeout: float = 20.0) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in RELEASE_HOSTS:
        raise UpdateError("not an official release URL")
    opener = urllib.request.build_opener(_ReleaseRedirects())
    try:
        with opener.open(urllib.request.Request(url, headers={"User-Agent": "orla-dock-update"}), timeout=timeout) as reply:
            data = reply.read(limit + 1)
    except UpdateError:
        raise
    except Exception as exc:  # network, TLS, HTTP: one finite error, no server text
        raise UpdateError("release download failed") from exc
    if len(data) > limit:
        raise UpdateError("release file is larger than expected")
    return data


def asset_urls(version: str) -> tuple[str, str]:
    base = f"https://github.com/{REPOSITORY}/releases/download/v{version}/"
    return base + f"orla-dock-{version}.plasmoid", base + "SHA256SUMS"


def checked_sum(sums: bytes, name: str) -> str:
    try:
        text = sums.decode("ascii")
    except UnicodeError as exc:
        raise UpdateError("invalid SHA256SUMS") from exc
    found = [line.split()[0] for line in text.splitlines()
             if re.fullmatch(r"[0-9a-f]{64}  " + re.escape(name), line)]
    if len(found) != 1:
        raise UpdateError("SHA256SUMS does not list the applet exactly once")
    return found[0]


def check_available(installed: str, channel: str) -> dict:
    """The release check, in its own process like the CLI (scripts/updates.py)."""
    script = Path(__file__).resolve().with_name("updates.py")
    result = subprocess.run([sys.executable, "-I", "-B", str(script), "check", "--installed-version", installed,
                             "--channel", channel], capture_output=True, text=True, timeout=30)
    try:
        value = json.loads(result.stdout)
    except ValueError as exc:
        raise UpdateError("release check failed") from exc
    if not isinstance(value, dict) or "status" not in value:
        raise UpdateError("release check failed")
    return value


def _plasma_ok(metadata: dict, running: tuple[int, int, int] | None) -> bool:
    minimum = str(metadata.get("X-Plasma-API-Minimum-Version") or "")
    match = re.fullmatch(r"(\d+)\.(\d+)", minimum)
    if not match:
        return False
    return running is not None and running[:2] >= (int(match.group(1)), int(match.group(2)))


def keep_installed(home: Path, target: Path) -> Path:
    """The installed package as a .plasmoid, so a later install can bring it back."""
    source = installed_dir(home)
    files = sorted(path for path in source.rglob("*")
                   if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts)
    if not files:
        raise UpdateError("installed dock not found")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(source).as_posix(), (1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    caiodock._archive_metadata(temporary)
    temporary.replace(target)
    return target


def _record(record: dict) -> None:
    folder = state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / "state.tmp"
    temporary.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(folder / "state.json")


def read_record() -> dict | None:
    try:
        return json.loads((state_dir() / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def apply(channel: str = "beta", *, home: Path | None = None, check=check_available, fetcher=fetch,
          installer=caiodock.install, plasma=caiodock._plasma_version) -> dict:
    home = home or data_home()
    current = installed_version(home)
    if current is None:
        raise UpdateError("the dock is not installed for this user; install it from a release first")
    found = check(current, channel)
    if found.get("status") != "update_available":
        return {"status": found.get("status"), "installed": current}
    version = str(found.get("available_version") or "")
    if not VERSION.fullmatch(version):
        raise UpdateError("release check returned an invalid version")
    plasmoid_url, sums_url = asset_urls(version)
    expected = checked_sum(fetcher(sums_url, SUMS_LIMIT), f"orla-dock-{version}.plasmoid")
    data = fetcher(plasmoid_url, PLASMOID_LIMIT)
    if hashlib.sha256(data).hexdigest() != expected:
        raise UpdateError("the downloaded applet does not match SHA256SUMS")
    folder = state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder) as scratch:
        package = Path(scratch) / f"orla-dock-{version}.plasmoid"
        package.write_bytes(data)
        try:
            metadata, _ = caiodock._archive_metadata(package)
        except caiodock.PackageError as exc:
            raise UpdateError("the release applet is invalid") from exc
        if metadata["KPlugin"]["Version"] != version:
            raise UpdateError("the applet's version differs from the release")
        if not _plasma_ok(metadata, plasma()):
            raise UpdateError("this Plasma is older than the release requires")
        kept = keep_installed(home, folder / "kept" / f"orla-dock-{current}.plasmoid")
        record = {"phase": "installing", "from": current, "to": version, "kept": str(kept),
                  "channel": channel, "at": int(time.time())}
        _record(record)
        try:
            installer(package, home)
            if installed_version(home) != version:
                raise UpdateError("the installed version did not change")
        except Exception as exc:
            # Put the previous version back; profiles and settings live outside the package.
            try:
                installer(kept, home)
                record.update(phase="rolled_back", reason="install_failed")
            except Exception:
                record.update(phase="recovery_required", reason="install_failed")
            _record(record)
            raise UpdateError("update failed; " + ("previous version restored" if record["phase"] == "rolled_back"
                                                    else "run `orla.py update rollback`")) from exc
    record.update(phase="applied")
    _record(record)
    return {"status": "updated", "from": current, "to": version}


def rollback(*, home: Path | None = None, installer=caiodock.install) -> dict:
    home = home or data_home()
    record = read_record()
    if not record or not record.get("kept"):
        raise UpdateError("no kept version to go back to")
    kept = Path(record["kept"])
    if kept.parent != state_dir() / "kept" or not kept.is_file():
        raise UpdateError("the kept version is missing")
    caiodock._archive_metadata(kept)
    installer(kept, home)
    record.update(phase="rolled_back", reason="requested", at=int(time.time()))
    _record(record)
    return {"status": "rolled_back", "installed": installed_version(home)}


def status(*, home: Path | None = None) -> dict:
    return {"installed": installed_version(home or data_home()), "record": read_record()}
