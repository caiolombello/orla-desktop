#!/usr/bin/env python3
"""Read-only cache bridge. Never imports providers or accesses credentials."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import math
import os
from pathlib import Path
import stat

# Zen exports a percentage of a USD spending limit, not a usage allowance.
SUBSCRIPTIONS = frozenset(('codex', 'claude', 'gemini', 'grok', 'kiro', 'cursor', 'glm', 'opencode-go'))
MAX_CACHE_BYTES = 256 * 1024
MODULE_IDS = ('quota', 'peripherals', 'recording')


def _read_bounded(path, history=False):
    """Read regular cache files only, with bounded allocation and no writes."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Not a regular cache')
        offset = max(0, info.st_size - MAX_CACHE_BYTES) if history else 0
        if not history and info.st_size > MAX_CACHE_BYTES:
            raise ValueError('Oversized cache')
        handle.seek(offset)
        data = handle.read(MAX_CACHE_BYTES + 1)
        if len(data) > MAX_CACHE_BYTES:
            raise ValueError('Oversized cache')
    if history:
        if offset:
            _, separator, data = data.partition(b'\n')
            if not separator:
                raise ValueError('Oversized record')
        end = data.rfind(b'\n')
        if end < 0:
            raise ValueError('No complete record')
        data = data[:end].rsplit(b'\n', 1)[-1]
    return json.loads(data)


def _valid_snapshot(record):
    if not isinstance(record, dict) or _datetime(record.get('timestamp')) is None:
        return False
    providers = record.get('providers')
    return isinstance(providers, list) and len(providers) <= 64 and all(
        isinstance(p, dict) and isinstance(p.get('provider'), str) and all(
            p.get(k) is None or isinstance(p[k], dict) for k in ('primary', 'secondary', 'tertiary'))
        for p in providers)


def _datetime(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp if stamp.tzinfo is not None else None
    except ValueError:
        return None


_backend = None


def _addon_backend():
    global _backend
    if _backend is None:
        spec = importlib.util.spec_from_file_location('_orla_integrations_addon_store',
            Path(__file__).absolute().with_name('addon_store.py'))
        backend = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(backend)
        _backend = backend
    return _backend


def _peripherals(home, now, use_xdg):
    # Load only for an explicitly selected module, with the caller's root/clock.
    code = 'io'
    try:
        backend = _addon_backend()
    except (OSError, ImportError):
        pass
    else:
        try:
            paths = backend.AddonPaths(home=home,
                data_home=None if use_xdg else home / '.local/share',
                state_home=None if use_xdg else home / '.local/state')
            return backend.snapshot_peripherals(paths=paths, now_ms=int(now.timestamp() * 1000),
                                                profile_enabled=True)
        except backend.AddonError as error:
            code = error.code
    # Legacy callers retain their envelope; no private cache fallback or raw error.
    return dict(status='invalid', generatedAt=None, source=None, producerVersion=None,
        limited=True, devices=[], generatedAtMs=None, expiresAtMs=None, leaseMs=None,
        addon=dict(id=None, sha256=None, enabled=False, generation=None,
                   producerNamespace=None, reason='export_invalid', errorCode=code))


def _recording(state_dir, now):
    result = {'status': 'missing', 'state': 'unknown', 'elapsedSeconds': None, 'livenessVerified': False}
    try:
        record = _read_bounded(state_dir / 'recording-cli/recording-session.json')
        if (not isinstance(record, dict) or type(record.get('version')) is not int or record['version'] != 1
                or record.get('phase') not in ('starting', 'recording', 'stopped')
                or record.get('owner') not in ('manual', 'call')
                or record.get('backend') not in ('audio', 'gpu-screen-recorder', 'obs')):
            raise ValueError('Invalid recording session')
        started = _datetime(record.get('startedAt'))
        ended = _datetime(record.get('endedAt'))
        if started is None or started > now or ('endedAt' in record and (ended is None or ended < started or ended > now)):
            raise ValueError('Invalid session time')
        result['state'] = record['phase']
        result['status'] = 'ready' if record['phase'] == 'stopped' else 'unknown'
        result['elapsedSeconds'] = int(((ended or now) - started).total_seconds())
        # Session files have no PID. Never infer process liveness from stored phase.
    except FileNotFoundError:
        pass
    except (OSError, ValueError, RecursionError):
        result['status'] = 'invalid'
    return result


def _quota(home, now):
    quota = {'status': 'missing', 'updatedAt': None, 'windows': [], 'costs': []}
    path = home / '.local/share/codexbar-linux/history.jsonl'
    try:
        record = _read_bounded(path, history=True)
        if not _valid_snapshot(record):
            raise ValueError('Invalid snapshot')
    except FileNotFoundError:
        record = None
    except (OSError, ValueError, RecursionError):
        quota['status'] = 'invalid'
        record = None
    if record:
        quota['updatedAt'] = record.get('timestamp')
        for provider in record.get('providers', []):
            if provider.get('provider') not in SUBSCRIPTIONS:
                continue
            stamp = _datetime(provider.get('updated_at'))
            age = (now - stamp).total_seconds() if stamp else None
            error = provider.get('error')
            stale = (age is not None and age > 900) or (isinstance(error, str) and 'stale' in error.lower())
            confirmed = age is not None and age >= 0 and not error
            for key in ('primary', 'secondary', 'tertiary'):
                window = provider.get(key)
                if isinstance(window, dict):
                    description = window.get('reset_description', '')
                    if isinstance(description, str) and '$' in description:
                        continue  # Cursor billing budgets and other monetary dimensions.
                    value = window.get('used_percent')
                    duration = window.get('window_minutes')
                    label = key.title()
                    if type(duration) is int and 0 < duration <= 525600:
                        span = f'{duration // 1440}d' if duration % 1440 == 0 else f'{duration // 60}h' if duration % 60 == 0 else f'{duration}m'
                        label += f' ({span})'
                    quota['windows'].append({'provider': provider['provider'], 'label': label,
                        'usedPercent': float(value) if confirmed and type(value) in (int, float) and 0 <= value <= 100 and math.isfinite(value) else None,
                        'resetAt': window.get('resets_at') if _datetime(window.get('resets_at')) else None,
                        'resetDescription': window.get('reset_description', '')[:120] if isinstance(window.get('reset_description', ''), str) else '', 'stale': stale})
        quota['status'] = 'ready' if any(w['usedPercent'] is not None and not w['stale'] for w in quota['windows']) else 'stale' if any(w['stale'] for w in quota['windows']) else 'unknown'
    return quota


def _collect_modules(modules, home, now):
    use_xdg = home is None
    home = Path.home() if home is None else Path(home)
    now = datetime.now(timezone.utc) if now is None else now
    configured_state = os.environ.get('XDG_STATE_HOME', '') if use_xdg else ''
    state_dir = Path(configured_state) if configured_state and Path(configured_state).is_absolute() else home / '.local/state'
    result = {}
    if 'quota' in modules:
        result['quota'] = _quota(home, now)
    if 'peripherals' in modules:
        result['peripherals'] = _peripherals(home, now, use_xdg)
    if 'recording' in modules:
        result['recording'] = _recording(state_dir, now)
    return result


def collect_snapshot(home=None, now=None):
    """Legacy schema 1: preserve the complete snapshot for existing callers."""
    return {'schemaVersion': 1, **_collect_modules(MODULE_IDS, home, now)}


def collect_selected_snapshot(modules, home=None, now=None):
    """Schema 2: validate the finite selection before touching any cache."""
    if (not isinstance(modules, list) or len(modules) > len(MODULE_IDS)
            or any(type(module) is not str or module not in MODULE_IDS for module in modules)
            or len(set(modules)) != len(modules)):
        raise ValueError('Invalid modules')
    selected = [module for module in MODULE_IDS if module in modules]
    if not selected:
        return {'schemaVersion': 2, 'modules': []}
    return {'schemaVersion': 2, 'modules': selected, **_collect_modules(selected, home, now)}


def _selected_snapshot_json(modules):
    try:
        result = collect_selected_snapshot(modules)
    except ValueError:
        result = {'schemaVersion': 2, 'error': 'invalid-modules'}
    return json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _snapshot_json():
    return json.dumps(collect_snapshot(), ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _source_fingerprint():
    try:
        info = Path(__file__).stat()
        return info.st_mtime_ns, info.st_size, info.st_ino
    except OSError:
        return None


def serve():
    from PySide6.QtCore import ClassInfo, QCoreApplication, QObject, QTimer, Slot
    from PySide6.QtDBus import QDBusConnection

    app = QCoreApplication([])
    source_fingerprint = _source_fingerprint()

    @ClassInfo({'D-Bus Interface': 'org.caiodock.Integrations1'})
    class CacheBridge(QObject):
        def __init__(self):
            super().__init__()
            self.idle = QTimer(self)
            self.idle.setSingleShot(True)
            self.idle.setInterval(300_000)
            self.idle.timeout.connect(app.quit)
            self.idle.start()

        @Slot(result=str)
        def Snapshot(self):
            self.idle.start()
            return _snapshot_json()

        @Slot('QStringList', result=str)
        def SnapshotFor(self, modules):
            self.idle.start()
            return _selected_snapshot_json(modules)

    bridge = CacheBridge()
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return 1
    if not bus.registerObject('/org/caiodock/Integrations', bridge, QDBusConnection.RegisterOption.ExportAllSlots):
        return 1
    if not bus.registerService('org.caiodock.Integrations'):
        return 1
    connection_watch = QTimer(bridge)
    connection_watch.setInterval(5000)
    connection_watch.timeout.connect(
        lambda: None if bus.isConnected() and _source_fingerprint() == source_fingerprint else app.quit())
    connection_watch.start()
    return app.exec()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--snapshot', action='store_true')
    mode.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    if args.snapshot:
        print(_snapshot_json())
        return 0
    try:
        return serve()
    except ImportError:
        parser.exit(1, 'Orla Dock integration service requires PySide6 QtDBus.\n')


if __name__ == '__main__':
    raise SystemExit(main())
