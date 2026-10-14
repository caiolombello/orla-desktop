"""Bounded tests with owned XDG paths and a private D-Bus daemon without service activation."""
from pathlib import Path
import argparse
import ast
import os
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import uuid


def desktop_quote(value):
    quoted = ''.join('\\' + c if c in '\\"`$' else c for c in str(value))
    return '"' + quoted.replace('\\', '\\\\').replace('%', '%%') + '"'


def verify_isolation(env, root, inherited_address):
    """Exercise only the new bus, including a service that must never be activated."""
    address = env['DBUS_SESSION_BUS_ADDRESS']
    runtime = Path(env['XDG_RUNTIME_DIR'])
    assert address != inherited_address
    assert runtime.parent == root and runtime.stat().st_uid == os.getuid()
    assert runtime.stat().st_mode & 0o777 == 0o700
    assert all(key not in env for key in ['DBUS_STARTER_ADDRESS', 'DBUS_STARTER_BUS_TYPE', 'AT_SPI_BUS_ADDRESS'])
    services = root / 'data/dbus-1/services'
    services.mkdir(parents=True)
    marker = root / 'unexpected-activation'
    executable = root / 'activation_probe.py'
    executable.write_text('from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text("activated")\n')
    service = 'org.orla.IsolationActivationProbe'
    (services / (service + '.service')).write_text(
        '[D-BUS Service]\nName=' + service + '\nExec="' + sys.executable + '" "' + str(executable) + '" "' + str(marker) + '"\n')
    result = subprocess.run(['gdbus', 'call', '--address', address, '--dest', service,
                             '--object-path', '/', '--method', 'org.freedesktop.DBus.Peer.Ping'],
                            env=env, cwd=runtime, capture_output=True, text=True, timeout=3)
    assert result.returncode != 0 and 'org.freedesktop.DBus.Error.ServiceUnknown' in result.stderr
    assert not marker.exists(), 'Private bus must not activate any service, even an owned test service'
    result = subprocess.run(['gdbus', 'call', '--address', address, '--dest', 'org.freedesktop.DBus',
                             '--object-path', '/org/freedesktop/DBus', '--method', 'org.freedesktop.DBus.GetId'],
                            env=env, cwd=runtime, capture_output=True, text=True, timeout=3, check=True)
    env['ORLA_EXPECTED_PRIVATE_BUS_ID'] = ast.literal_eval(result.stdout)[0]
    print('ORLA_ISOLATION_PASS inherited_session_bus_excluded=true runtime_owned=true service_activation_disabled=true', flush=True)



def selected_test_command(command, excluded, env, runtime):
    if not excluded:
        return command
    if len(command) != 1 or len(set(excluded)) != len(excluded):
        raise ValueError("Exclusions require one executable and distinct test names")
    listed = subprocess.run([command[0], '-functions'], env=env, cwd=runtime,
                            capture_output=True, text=True, timeout=3)
    lines = listed.stdout.splitlines()
    if listed.returncode != 0 or not lines or len(listed.stdout) > 65536:
        raise ValueError("Qt Test function enumeration failed")
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\(\)', line) for line in lines):
        raise ValueError("Invalid Qt Test function inventory")
    functions = [line[:-2] for line in lines]
    if len(set(functions)) != len(functions) or not set(excluded).issubset(functions):
        raise ValueError("Duplicate inventory or unknown excluded test")
    selected = [name for name in functions if name not in excluded]
    if not selected:
        raise ValueError("The test partition cannot exclude every function")
    print(f'ORLA_TEST_PARTITION available={len(functions)} selected={len(selected)} excluded={len(excluded)}', flush=True)
    return [command[0], *selected]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path)
    parser.add_argument('--private-path', action='store_true')
    parser.add_argument('--exclude-test', action='append', default=[])
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.command:
        parser.error('Provide a test executable and optional test-case arguments')
    if not shutil.which('dbus-daemon') or not shutil.which('gdbus'):
        parser.error('Tests require dbus-daemon and gdbus for isolation verification')
    inherited_address = os.environ.get('DBUS_SESSION_BUS_ADDRESS')
    with tempfile.TemporaryDirectory(prefix='orla-launcher-tests-', dir=os.environ.get('TMPDIR')) as directory:
        root = Path(directory)
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_ACCESSIBILITY='0')
        for key in ['DBUS_SESSION_BUS_ADDRESS', 'DBUS_SYSTEM_BUS_ADDRESS', 'DBUS_STARTER_ADDRESS', 'DBUS_STARTER_BUS_TYPE',
                    'AT_SPI_BUS_ADDRESS', 'SESSION_MANAGER', 'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
            env.pop(key, None)
        for name in ['config', 'cache', 'data', 'state']:
            (root / name).mkdir()
            env['XDG_' + name.upper() + '_HOME'] = str(root / name)
        runtime = root / 'runtime'
        runtime.mkdir(mode=0o700)
        env['XDG_RUNTIME_DIR'] = str(runtime)
        env['XDG_DATA_DIRS'] = '/usr/local/share:/usr/share'
        # Linux abstract address avoids AF_UNIX's short pathname limit in long checkout paths.
        socket_name = 'orla-test-' + uuid.uuid4().hex
        config = root / 'dbus.conf'
        config.write_text(
            '<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN" '
            '"http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">\n'
            '<busconfig><type>session</type><listen>unix:abstract=' + socket_name + '</listen>'
            '<auth>EXTERNAL</auth><policy context="default"><allow user="' + str(os.getuid()) + '"/>'
            '<allow own="*"/><allow send_destination="*"/><allow receive_sender="*"/></policy></busconfig>\n')
        # Deliberately no includes, service directories, helpers or systemd activation.
        with (root / 'dbus.log').open('w') as daemon_log:
            daemon = subprocess.Popen(['dbus-daemon', '--nofork', '--nopidfile', '--nosyslog',
                                       '--config-file=' + str(config), '--print-address=1'],
                                      env=env, cwd=runtime, stdout=subprocess.PIPE, stderr=daemon_log, text=True)
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(daemon.stdout, selectors.EVENT_READ)
                    if not selector.select(timeout=3):
                        raise TimeoutError('Owned D-Bus daemon did not become ready within 3 seconds')
                    address = daemon.stdout.readline().strip()
                if not address.startswith('unix:abstract=' + socket_name + ',') or daemon.poll() is not None:
                    raise RuntimeError('Owned D-Bus daemon failed to start')
                env['DBUS_SESSION_BUS_ADDRESS'] = address
                env['DBUS_SYSTEM_BUS_ADDRESS'] = address
                verify_isolation(env, root, inherited_address)
                if args.fixture:
                    applications = root / 'data/applications'
                    applications.mkdir()
                    receipt = root / 'owned-receipt'
                    env['ORLA_TEST_RECEIPT'] = str(receipt)
                    (applications / 'org.orla.OwnedLauncherFixture.desktop').write_text(
                        '[Desktop Entry]\nType=Application\nName=OrlaOwnedLauncherFixture\n'
                        'Exec=' + desktop_quote(args.fixture.resolve()) + ' ' + desktop_quote(receipt) + '\n'
                        'Terminal=false\nCategories=Utility;\n', encoding='utf-8')
                else:
                    env.pop('ORLA_TEST_RECEIPT', None)
                if args.private_path:
                    owned_bin = root / 'bin'
                    owned_bin.mkdir()
                    env['PATH'] = str(owned_bin)
                try:
                    command = selected_test_command(args.command, args.exclude_test, env, runtime)
                except ValueError as error:
                    parser.error(str(error))
                result = subprocess.run(command, env=env, cwd=runtime, timeout=35)
                print(f'ORLA_TEST_RESULT returncode={result.returncode}', flush=True)
                return result.returncode
            finally:
                daemon.terminate()
                try:
                    daemon.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    daemon.kill()
                    daemon.wait(timeout=3)
                daemon.stdout.close()
                print('ORLA_ISOLATION_CLEANUP owned_daemon_stopped=true', flush=True)


if __name__ == '__main__':
    sys.exit(main())
