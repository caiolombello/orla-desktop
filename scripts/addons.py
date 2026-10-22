#!/usr/bin/env python3
"""Development CLI for experimental passive addons; never starts producers."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

# Explicit trusted sibling path avoids CWD/package namespace collisions.
_spec = importlib.util.spec_from_file_location('_orla_addon_store',
    Path(__file__).absolute().parents[1] / 'package/contents/code/addon_store.py')
store = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(store)


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise store.AddonError('format')


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description='Experimental data-only addons. SHA is integrity, not publisher authentication.')
    parser.add_argument('--home')
    parser.add_argument('--data-home')
    parser.add_argument('--state-home')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('inspect', 'pack', 'install'):
        item = sub.add_parser(command)
        item.add_argument('file')
        if command == 'pack':
            item.add_argument('--output', required=True)
        if command == 'install':
            item.add_argument('--expected-sha256', required=True)
    sub.add_parser('list')
    for command in ('enable', 'disable', 'remove', 'rollback'):
        item = sub.add_parser(command)
        item.add_argument('addon_id')
        item.add_argument('--expected-current-sha256', required=True)
    snapshot = sub.add_parser('snapshot')
    snapshot.add_argument('--now-ms', type=int)
    snapshot.add_argument('--profile-hidden', action='store_true')
    snapshot.add_argument('--module', choices=('peripherals', 'quota'), default='peripherals')
    try:
        args = parser.parse_args(argv)
        if args.command == 'inspect':
            result = store.inspect_addon(file=args.file)
        elif args.command == 'pack':
            result = store.pack_addon(file=args.file, output_dir=args.output)
        else:
            paths = store.AddonPaths(home=args.home, data_home=args.data_home, state_home=args.state_home)
            if args.command == 'list':
                result = store.list_addons(paths=paths)
            elif args.command == 'install':
                result = store.install_addon(paths=paths, file=args.file,
                                             expected_sha256=args.expected_sha256)
            elif args.command == 'snapshot':
                snapshot = store.snapshot_quota if args.module == 'quota' else store.snapshot_peripherals
                result = snapshot(paths=paths, now_ms=args.now_ms, profile_enabled=not args.profile_hidden)
            else:
                operation = {'enable': store.enable_addon, 'disable': store.disable_addon,
                             'remove': store.remove_addon, 'rollback': store.rollback_addon}[args.command]
                result = operation(paths=paths, addon_id=args.addon_id,
                                   expected_current_sha256=args.expected_current_sha256)
        print(json.dumps(dict(ok=True, result=result), ensure_ascii=False, allow_nan=False))
    except store.AddonError as error:
        print(json.dumps(dict(ok=False, error=dict(code=error.code, committed=error.committed,
                                                  generation=error.generation))))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
