#!/usr/bin/env python3
"""Build, install, and privately preview Orla Dock (legacy compatible module)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

PACKAGE_ID = "org.caiodock.dock"
SERVICE_NAME = "org.caiodock.Integrations.service"
SERVICE_MARKER = "# Managed by CaioDock\n"
MINIMUM_PLASMA = (6, 7)
OPTIONAL_INTEGRATION_DEPENDENCIES = {"busctl", "PySide6.QtDBus", "sessão D-Bus do usuário"}


class PackageError(Exception):
    pass


def project_root(argument: str | None) -> Path:
    return Path(argument).expanduser().resolve() if argument else Path(__file__).resolve().parents[1]


def package_inputs(root: Path) -> tuple[Path, str]:
    source = root / "package"
    metadata_file = source / "metadata.json"
    entrypoint = source / "contents" / "ui" / "main.qml"
    license_file = root / "LICENSE"
    for path in (metadata_file, entrypoint, license_file):
        if not path.is_file() or path.is_symlink():
            raise PackageError(f"required regular file is missing: {path}")
    try:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        plugin = metadata["KPlugin"]
        package_id = plugin["Id"]
        version = plugin["Version"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PackageError(f"invalid package metadata: {exc}") from exc
    if package_id != PACKAGE_ID:
        raise PackageError(f"unexpected KPlugin.Id: {package_id!r}")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", version):
        raise PackageError("KPlugin.Version must use a safe semantic version")
    return source, version


def build(root: Path, output_dir: Path | None = None) -> Path:
    source, version = package_inputs(root)
    destination_dir = output_dir or root / "dist"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"orla-dock-{version}.plasmoid"
    def add_file(archive: zipfile.ZipFile, path: Path, archive_name: str) -> None:
        info = zipfile.ZipInfo(archive_name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(info, path.read_bytes())

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        add_file(archive, source / "metadata.json", "metadata.json")
        contents = source / "contents"
        for current, dirs, files in os.walk(contents, followlinks=False):
            current_path = Path(current)
            dirs[:] = sorted(d for d in dirs if d != "__pycache__" and not (current_path / d).is_symlink())
            for name in sorted(files):
                path = current_path / name
                if not path.is_symlink() and path.suffix not in (".pyc", ".pyo"):
                    add_file(archive, path, path.relative_to(source).as_posix())
        add_file(archive, root / "LICENSE", "LICENSE")
    return destination


def environment_with(**updates: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(updates)
    return env


def require_tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise PackageError(f"required executable not found: {name}")
    return executable


def _service_path(data_home: Path) -> Path:
    return data_home / "dbus-1/services" / SERVICE_NAME


def _check_service_path(data_home: Path) -> Path:
    service = _service_path(data_home)
    if service.is_symlink():
        raise PackageError(f"refusing to replace a symbolic-link service: {service}")
    if service.exists() and not service.read_text(encoding="utf-8").startswith(SERVICE_MARKER):
        raise PackageError(f"preserving an existing service not managed by Orla Dock: {service}")
    return service


def _archive_metadata(package: Path) -> tuple[dict, set[str]]:
    if package.is_symlink() or not package.is_file():
        raise PackageError(f"package archive must be a regular file: {package}")
    try:
        with zipfile.ZipFile(package) as archive:
            names: set[str] = set()
            for info in archive.infolist():
                name = Path(info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if name.is_absolute() or ".." in name.parts or mode == 0o120000:
                    raise PackageError(f"unsafe path in package archive: {info.filename}")
                names.add(info.filename)
            required = {"metadata.json", "LICENSE", "contents/ui/main.qml", "contents/code/integrations.py"}
            if not required.issubset(names):
                raise PackageError("package archive is missing required runtime files")
            metadata = json.loads(archive.read("metadata.json"))
    except (OSError, ValueError, zipfile.BadZipFile, KeyError) as exc:
        if isinstance(exc, PackageError):
            raise
        raise PackageError(f"invalid package archive: {exc}") from exc
    try:
        plugin = metadata["KPlugin"]
        package_id = plugin["Id"]
        version = plugin["Version"]
    except (TypeError, KeyError) as exc:
        raise PackageError(f"invalid package metadata: {exc}") from exc
    if package_id != PACKAGE_ID:
        raise PackageError(f"unexpected KPlugin.Id: {package_id!r}")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", version):
        raise PackageError("KPlugin.Version must use a safe semantic version")
    return metadata, names


def _plasma_version() -> tuple[int, int, int] | None:
    executable = shutil.which("plasmashell")
    if not executable:
        return None
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"(?:Plasma|plasmashell)\s+(\d+)\.(\d+)(?:\.(\d+))?", result.stdout + result.stderr, re.IGNORECASE)
    return tuple(int(part or 0) for part in match.groups()) if result.returncode == 0 and match else None


def _session_bus_available() -> bool:
    if not (os.environ.get("DBUS_SESSION_BUS_ADDRESS") or os.environ.get("XDG_RUNTIME_DIR")):
        return False
    executable = shutil.which("busctl")
    if not executable:
        return False
    try:
        result = subprocess.run([executable, "--user", "status"], capture_output=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def dependency_status(*, include_integrations: bool = True) -> dict[str, bool]:
    statuses = {
        "Python 3": sys.version_info >= (3, 10),
        "kpackagetool6": shutil.which("kpackagetool6") is not None,
    }
    if not include_integrations:
        return statuses
    try:
        qtdbus = importlib.util.find_spec("PySide6.QtDBus") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        qtdbus = False
    statuses.update({
        "busctl": shutil.which("busctl") is not None,
        "PySide6.QtDBus": qtdbus,
        "sessão D-Bus do usuário": _session_bus_available(),
    })
    return statuses


def _require_install_runtime(*, with_integrations: bool = False) -> bool:
    statuses = dependency_status(include_integrations=with_integrations)
    missing = [name for name, available in statuses.items() if not available and name not in OPTIONAL_INTEGRATION_DEPENDENCIES]
    if missing:
        raise PackageError("missing install/runtime dependencies: " + ", ".join(missing))
    version = _plasma_version()
    if version is not None and version[:2] < MINIMUM_PLASMA:
        raise PackageError(f"Plasma 6.7 or newer is required; detected {'.'.join(map(str, version))}")
    if not with_integrations:
        return False
    optional_missing = [name for name, available in statuses.items() if not available and name in OPTIONAL_INTEGRATION_DEPENDENCIES]
    if optional_missing:
        print("orla: integrações locais indisponíveis (opcionais): " + ", ".join(optional_missing)
              + "; instalação do dock continua. Execute doctor após instalar as dependências e reinstale com --with-integrations para ativar as integrações.", file=sys.stderr)
    return not optional_missing


def run_checked(command: list[str], env: dict[str, str] | None = None) -> None:
    result = subprocess.run(command, env=env, check=False)
    if result.returncode:
        raise PackageError(f"command failed with exit status {result.returncode}: {command[0]}")


def install(package: Path, data_home: Path | None = None, *, with_integrations: bool = False) -> str:
    _archive_metadata(package)
    home = data_home or Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")).expanduser()
    _check_service_path(home)
    integrations_available = _require_install_runtime(with_integrations=with_integrations)
    installed = home / "plasma" / "plasmoids" / PACKAGE_ID
    action = "--upgrade" if installed.exists() else "--install"
    env = environment_with(XDG_DATA_HOME=str(home))
    run_checked([require_tool("kpackagetool6"), "--type", "Plasma/Applet", action, str(package.resolve())], env)
    if integrations_available and (installed / "contents/code/integrations.py").is_file():
        enable_integrations(home)
        # dbus-broker may not watch a services directory that did not exist
        # when the login session started. Reloading discovers the new mapping.
        busctl = require_tool("busctl")
        try:
            result = subprocess.run([busctl, "--user", "--timeout=8s", "call", "org.freedesktop.DBus", "/org/freedesktop/DBus",
                                     "org.freedesktop.DBus", "ReloadConfig"], env=env, capture_output=True, timeout=10)
            refreshed = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            refreshed = False
        if not refreshed:
            print("orla: dock instalado; a sessão D-Bus não atualizou as integrações locais opcionais. "
                  "O serviço foi preservado. Execute doctor na sessão KDE e reinstale com --with-integrations para tentar ativar as integrações novamente.", file=sys.stderr)
    return action


def enable_integrations(data_home: Path) -> Path:
    """Register lazy activation on this user's session bus, without starting apps."""
    bridge = data_home.resolve() / "plasma/plasmoids" / PACKAGE_ID / "contents/code/integrations.py"
    if not bridge.is_file() or bridge.is_symlink():
        raise PackageError(f"installed integration bridge is missing: {bridge}")
    if any(character in str(bridge) for character in ("\n", "\r", "\x00")):
        raise PackageError("integration path contains unsupported characters")
    service = _check_service_path(data_home)
    service.parent.mkdir(parents=True, exist_ok=True)
    command = shlex.join([sys.executable, str(bridge), "--serve"])
    service.write_text(SERVICE_MARKER + "[D-BUS Service]\nName=org.caiodock.Integrations\nExec=" + command + "\n", encoding="utf-8")
    return service


def uninstall(data_home: Path | None = None) -> bool:
    home = data_home or Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")).expanduser()
    service = _check_service_path(home)
    installed = home / "plasma" / "plasmoids" / PACKAGE_ID
    tool = require_tool("kpackagetool6") if installed.exists() else None
    if tool:
        env = environment_with(XDG_DATA_HOME=str(home))
        run_checked([tool, "--type", "Plasma/Applet", "--remove", PACKAGE_ID], env)
    if service.exists():
        service.unlink()
    # Do not remove Plasma configuration or any project cache/state.
    return tool is not None


def doctor() -> int:
    statuses = dependency_status()
    for name, available in statuses.items():
        label = "OK" if available else "OPCIONAL AUSENTE" if name in OPTIONAL_INTEGRATION_DEPENDENCIES else "AUSENTE"
        print(f"{label}  {name}")
    version = _plasma_version()
    if version is None:
        print("NÃO DETECTADO  Plasma (requisito do pacote: 6.7+)")
        statuses["Plasma 6.7+"] = False
    else:
        label = ".".join(map(str, version))
        available = version[:2] >= MINIMUM_PLASMA
        print(f"{'OK' if available else 'INCOMPATÍVEL'}  Plasma {label} (mínimo 6.7)")
        statuses["Plasma 6.7+"] = available
    return 0 if all(available for name, available in statuses.items() if name not in OPTIONAL_INTEGRATION_DEPENDENCIES) else 1


def preview(root: Path, timeout: float | None = None) -> None:
    package_inputs(root)
    # Use the same package layout/build checks without leaving a dist/ artifact.
    with tempfile.TemporaryDirectory(prefix="caiodock-preview-") as temporary:
        temp = Path(temporary)
        archive = build(root, temp)
        data_home = temp / "data"
        config_home = temp / "config"
        cache_home = temp / "cache"
        for path in (data_home, config_home, cache_home):
            path.mkdir()
        env = environment_with(
            XDG_DATA_HOME=str(data_home),
            XDG_CONFIG_HOME=str(config_home),
            XDG_CACHE_HOME=str(cache_home),
        )
        run_checked([require_tool("kpackagetool6"), "--type", "Plasma/Applet", "--install", str(archive)], env)
        command = [require_tool("plasmawindowed"), PACKAGE_ID]
        try:
            result = subprocess.run(command, env=env, check=False, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise PackageError(f"preview exceeded timeout ({timeout}s)") from exc
        if result.returncode:
            raise PackageError(f"command failed with exit status {result.returncode}: {command[0]}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog=Path(sys.argv[0]).stem, description="Package, install, and preview the Orla Dock Plasma widget")
    subparsers = result.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="check runtime dependencies without installing anything")
    subparsers.add_parser("uninstall", help="remove the dock and its owned D-Bus service; keep settings and project caches")
    build_parser = subparsers.add_parser("build", help="create dist/orla-dock-VERSION.plasmoid")
    build_parser.add_argument("--project-root")
    install_parser = subparsers.add_parser("install", help="install or upgrade this widget for the current user")
    install_parser.add_argument("package", type=Path)
    install_parser.add_argument("--with-integrations", action="store_true", help="opt in to the bundled local integration bridge")
    install_parser.add_argument("--data-home", type=Path, help=argparse.SUPPRESS)
    preview_parser = subparsers.add_parser("preview", help="run plasmawindowed with temporary XDG user directories")
    preview_parser.add_argument("--project-root")
    preview_parser.add_argument("--timeout", type=float, help="stop the preview after this many seconds")
    if __package__:
        from . import panel_layout
    else:
        import panel_layout
    panel_layout.add_parser(subparsers)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "build":
            print(build(project_root(args.project_root)))
        elif args.command == "install":
            action = install(args.package, args.data_home, with_integrations=args.with_integrations)
            print(f"Orla Dock {'atualizado' if action == '--upgrade' else 'instalado'} para este usuário")
        elif args.command == "uninstall":
            removed = uninstall()
            print("Orla Dock desinstalado; configurações e caches dos projetos foram preservados" if removed else "Serviço próprio removido; pacote não estava instalado")
        elif args.command == "doctor":
            return doctor()
        elif args.command == "layout":
            if __package__:
                from . import panel_layout
            else:
                import panel_layout
            try:
                return panel_layout.cli(args)
            except panel_layout.LayoutError as exc:
                raise PackageError(str(exc)) from exc
        else:
            if args.timeout is not None and args.timeout <= 0:
                raise PackageError("--timeout must be greater than zero")
            preview(project_root(args.project_root), args.timeout)
        return 0
    except (PackageError, OSError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        print(f"orla: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
