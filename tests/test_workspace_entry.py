"""Public bundle entry must remain inert until an explicit action is chosen."""

from pathlib import Path
import hashlib
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class EntryTests(unittest.TestCase):
    def test_unsupported_qt_never_starts_the_composition_host(self):
        import PySide6
        from workspace import main, package
        from scripts import workspace_setup
        with mock.patch.object(package, "verify_directory", return_value={}), \
                mock.patch.object(PySide6, "__version__", "6.10.0"), \
                mock.patch.object(workspace_setup, "launch", return_value=0) as launch, \
                mock.patch.object(sys, "path", sys.path.copy()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main.main(["--service", "plasma-fixture.service"]), 1)
        launch.assert_not_called()

    def test_startup_failure_omits_private_backend_exception(self):
        from workspace import main, package
        from scripts import panel_layout, workspace_setup
        error = panel_layout.LayoutError("private path /private/person/calendar")
        output = io.StringIO()
        with mock.patch.object(package, "verify_directory", return_value={}), \
                mock.patch.object(workspace_setup, "launch", side_effect=error), \
                mock.patch.object(sys, "path", sys.path.copy()), contextlib.redirect_stderr(output):
            self.assertEqual(main.main(["--service", "plasma-fixture.service"]), 1)
        self.assertIn("startup", output.getvalue())
        self.assertNotIn("private", output.getvalue())

    def test_help_from_unrelated_directory_requires_neither_qt_nor_service(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "workspace/main.py"), "--help"],
                                    cwd=directory, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--service", result.stdout)
        self.assertIn("--diagnose", result.stdout)

    def test_invalid_service_is_rejected_before_runtime_or_bundle_import(self):
        result = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "workspace/main.py"),
                                 "--service", "../foreign.service"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("literal", result.stderr)

    def bundle(self, directory):
        from workspace import package
        temporary = Path(directory)
        archive = package.build(ROOT, temporary / "archives", commit="a" * 40)
        verified = package.verify_archive(archive.read_bytes(), expected_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                                          expected_commit="a" * 40)
        unpacked = temporary / "original"
        for name, data in verified["files"].items():
            path = unpacked / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data); path.chmod(0o644)
        with zipfile.ZipFile(archive) as source:
            (unpacked / "manifest.json").write_bytes(source.read("manifest.json"))
        (unpacked / "manifest.json").chmod(0o644)
        moved = temporary / "Moved companion ç %"
        unpacked.rename(moved)
        return moved

    def environment(self, temporary):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        for key in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "TMPDIR"):
            path = temporary / key.lower(); path.mkdir(mode=0o700)
            (path / "sentinel").write_text("owned synthetic data")
            environment[key] = str(path)
        return environment

    def test_moved_bundle_reports_version_and_loads_actual_ui_without_service(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            moved = self.bundle(directory)
            elsewhere = root / "unrelated"; elsewhere.mkdir()
            environment = self.environment(root)
            before = {str(path.relative_to(moved)): path.read_bytes() for path in moved.rglob("*") if path.is_file()}
            for action in ("--version", "--diagnose"):
                result = subprocess.run([sys.executable, "-I", "-B", str(moved / "workspace/main.py"), action],
                                        cwd=elsewhere, env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                report = json.loads(result.stdout)
                self.assertEqual(report["commit"], "a" * 40)
                if action == "--diagnose":
                    self.assertEqual(report["runtime"]["status"], "ready")
                    self.assertFalse(report["nativeValidated"])
                    self.assertFalse(report["serviceContacted"])
            self.assertEqual({str(path.relative_to(moved)): path.read_bytes() for path in moved.rglob("*") if path.is_file()}, before)
            for key in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
                self.assertEqual(list(Path(environment[key]).iterdir()), [Path(environment[key]) / "sentinel"])

    def test_diagnosis_loads_ui_with_repository_hidden(self):
        if shutil.which("bwrap") is None:
            self.skipTest("Bubblewrap absent; OS-level repository masking not available")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            moved = self.bundle(directory)
            environment = self.environment(root)
            command = ["bwrap", "--die-with-parent", "--unshare-net", "--ro-bind", "/", "/",
                       "--tmpfs", str(ROOT), "--bind", str(root), str(root), "--proc", "/proc", "--dev", "/dev",
                       "--", sys.executable, "-I", "-B", str(moved / "workspace/main.py"), "--diagnose"]
            result = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(json.loads(result.stdout)["runtime"]["status"], "ready")

    def test_missing_qt_still_allows_version_and_reports_dependency_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            moved = self.bundle(directory)
            venv.EnvBuilder(with_pip=False).create(root / "no-qt")
            python = root / "no-qt/bin/python"
            command = [str(python), "-I", "-B", str(moved / "workspace/main.py")]
            version = subprocess.run(command + ["--version"], cwd=root, capture_output=True, text=True, timeout=10)
            self.assertEqual(version.returncode, 0, version.stderr)
            result = subprocess.run(command + ["--diagnose"], cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            report = json.loads(result.stdout)
            self.assertEqual(report["runtime"]["status"], "qt_runtime_missing")
            self.assertFalse(report["serviceContacted"])
            self.assertFalse(report["nativeValidated"])

    def collision_python(self, root):
        venv.EnvBuilder(with_pip=False, system_site_packages=True).create(root / "python")
        python = root / "python/bin/python"
        location = subprocess.run([str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                                  check=True, capture_output=True, text=True, timeout=10)
        site = Path(location.stdout.strip())
        # A nested venv inherits base Python's packages, not the invoking venv's Qt.
        import PySide6
        import shiboken6
        runtime = {str(Path(module.__file__).resolve().parent.parent) for module in (PySide6, shiboken6)}
        (site / "orla-test-qt.pth").write_text("\n".join(sorted(runtime)) + "\n", encoding="utf-8")
        return python, site

    def test_collision_fixture_keeps_parent_venv_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outer = root / "parent"
            venv.EnvBuilder(with_pip=False).create(outer)
            python = outer / "bin/python"
            location = subprocess.run([str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                                      check=True, capture_output=True, text=True, timeout=10)
            for name in ("PySide6", "shiboken6"):
                stub = Path(location.stdout.strip()) / name
                stub.mkdir()
                (stub / "__init__.py").write_text("fixture_origin = 'parent-only'\n")
            child = root / "child"; child.mkdir()
            program = """import importlib.util, pathlib, subprocess, sys
spec = importlib.util.spec_from_file_location('entry_fixture', sys.argv[1])
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
python, _ = module.EntryTests().collision_python(pathlib.Path(sys.argv[2]))
raise SystemExit(subprocess.run([str(python), '-I', '-B', '-c',
    "import PySide6, shiboken6; assert PySide6.fixture_origin == shiboken6.fixture_origin == 'parent-only'"]).returncode)
"""
            result = subprocess.run([str(python), "-I", "-B", "-c", program, str(Path(__file__).resolve()), str(child)],
                                    cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_installed_packages_cannot_replace_bundle_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            moved = self.bundle(directory)
            python, location = self.collision_python(root)
            for name in ("workspace", "scripts"):
                installed = location / name
                installed.mkdir()
                (installed / "__init__.py").write_text("")
            result = subprocess.run([str(python), "-I", "-B", str(moved / "workspace/main.py"), "--diagnose"],
                                    cwd=root, env=self.environment(root), capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(json.loads(result.stdout)["runtime"]["status"], "ready")


# Installed updates qualification shares the existing Source-only suite.
# Executes the actual main/launch/QML. No composition/native object is replaced.
GUI = r'''
import copy,hashlib,json,runpy,sys
from pathlib import Path
root=Path(sys.argv[1]); mode=sys.argv[2]; helper=sys.argv[3]
sys.path.insert(0,str(root))
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import qmlContext
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
app=QGuiApplication([])
report={}; errors=[]; timer=QTimer(); ticks=0
if mode=='check':
 from scripts import updates_desktop
 def runner(root,ref,channel):
  report['captured']=ref
  return sys.executable,['-I','-B',helper]
 updates_desktop.cli_command=runner

def inspect():
 global ticks
 ticks+=1
 try:
  windows=[w for w in app.topLevelWindows() if w.objectName()=='updatesWindow']
  if not windows:
   assert ticks<100,'production updates window did not open'
   return
  window=windows[0]; host=qmlContext(window).contextProperty('updatesController')
  assert not any(n in sys.modules for n in ('scripts.workspace_setup','scripts.panel_layout','workspace.install'))
  report['reference']=host.reference
  report['label']=window.findChild(QQuickItem,'updatesReference').property('text')
  report['origin']=window.findChild(QQuickItem,'updatesReferenceOrigin').property('text')
  report['status']=window.findChild(QQuickItem,'updatesStatus').property('text')
  if mode=='check' and 'clicked' not in report:
   report['clicked']=True
   window.findChild(QQuickItem,'updatesCheck').clicked.emit()
   return
  if host.busy:return
  if mode=='passive':
   components=window.findChild(QQuickItem,'updatesComponentVersions')
   if 'disclosureRequested' not in report:
    report['scopeInitiallyVisible']=components.isVisible()
    report['recordBeforeDisclosure']=copy.deepcopy(host.state['record'])
    report['disclosureRequested']=True
    window.findChild(QQuickItem,'updatesDetails').forceActiveFocus()
    QTest.keyClick(window,Qt.Key_Space)
    return
   report['scopeVisible']=components.isVisible()
   report['components']=components.property('text')
   assert host.state['record']==report['recordBeforeDisclosure'],'disclosure changed check history'
  report['record']=host.state['record']; report['storageWarning']=host.state['storageWarning']; window.close(); timer.stop()
 except BaseException as exc:
  errors.append(repr(exc));timer.stop();app.exit(90)
timer.timeout.connect(inspect);timer.start(20)
QTimer.singleShot(5000,lambda:app.exit(91))
sys.argv=[str(root/'workspace/main.py'),'--updates']
try:runpy.run_path(sys.argv[0],run_name='__main__')
except SystemExit as exc:report['exit']=exc.code
assert not errors,errors
assert report.get('exit')==0,report
for name,module in tuple(sys.modules.items()):
 if name=='scripts' or name.startswith('scripts.') or name=='workspace' or name.startswith('workspace.'):
  if getattr(module,'__file__',None): assert Path(module.__file__).is_relative_to(root),(name,module.__file__)
print(json.dumps(report,sort_keys=True))
'''


class UpdatesEntryTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temporary=tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name)
        fixture=EntryTests()
        self.bundle=fixture.bundle(self.temporary.name)
        self.env=fixture.environment(self.base)
        self.env['HOME']=str(self.base/'home');Path(self.env['HOME']).mkdir()
        for key in ('DBUS_SESSION_BUS_ADDRESS','DBUS_SYSTEM_BUS_ADDRESS','AT_SPI_BUS_ADDRESS'):
            self.env[key]='unix:path='+str(self.base/'absent-bus')
        self.env.update(QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',QML_DISABLE_DISK_CACHE='1')

    def run_entry(self,*args,qt=True):
        return subprocess.run([sys.executable,'-I',* ([] if qt else ['-S']),'-B',str(self.bundle/'workspace/main.py'),*args],cwd=self.base,env=self.env,capture_output=True,text=True,timeout=30)

    def gui(self,mode='passive',hidden=False):
        helper=self.base/'offline.py'
        helper.write_text("import json\nprint(json.dumps("+repr(dict(status='no_release',reason=None,source='https://api.github.com/repos/caiolombello/orla-desktop/releases',installed_version='0.2.9',available_version=None,available_url=None,channel='stable',checked_at='2026-10-20T12:00:00Z'))+"))\n")
        command=[sys.executable,'-I','-B','-c',GUI,str(self.bundle),mode,str(helper)]
        if hidden:
            if not shutil.which('bwrap'):self.skipTest('Bubblewrap absent: Source-hidden qualification unavailable')
            mount=self.base/'home-mount';mount.mkdir(exist_ok=True)
            command=['bwrap','--die-with-parent','--unshare-net','--uid',str(os.getuid()),'--gid',str(os.getgid()),'--ro-bind','/','/','--bind',str(mount),'/home','--ro-bind',str(next(p for p in ROOT.parents if p.parent == Path('/home'))),str(next(p for p in ROOT.parents if p.parent == Path('/home'))),'--perms','0755','--tmpfs',str(ROOT.parents[3]),'--bind',str(self.base),str(self.base),'--proc','/proc','--dev','/dev','--',*command]
        result=subprocess.run(command,cwd=self.base,env=self.env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertNotIn('Destroyed while process',result.stderr)
        return json.loads(result.stdout)

    def test_actual_main_opens_only_updates_with_verified_manifest_reference(self):
        before={p:p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        result=self.gui()
        manifest=(self.bundle/'manifest.json').read_bytes()
        # The bundle carries the dock package's own version, whatever release this checkout is.
        version=json.loads((ROOT/'package/metadata.json').read_text())['KPlugin']['Version']
        self.assertEqual(result['reference'],dict(role='bundle',component='workspace',origin='verified-manifest',version=version,commit='a'*40,digest=hashlib.sha256(manifest).hexdigest()))
        self.assertEqual(result['label'],version)
        self.assertIn('esta cópia do Workspace',result['origin'])
        self.assertIn('bundle verificado',result['origin'])
        self.assertFalse(result['scopeInitiallyVisible'])
        self.assertTrue(result['scopeVisible'])
        # Isolated XDG data has no dock package: the bundle never stands in for it.
        self.assertEqual(result['components'],'Dock instalada: não encontrada para este usuário\nDock em execução: não verificada')
        self.assertEqual(result['record'],{})
        for path,data in before.items():self.assertEqual(path.read_bytes(),data)
        for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME'):
            self.assertEqual([p.name for p in Path(self.env[key]).iterdir()],['sentinel'])

    def test_source_hidden_moved_actual_main_checks_offline_then_reopens_history(self):
        result=self.gui('check',hidden=True)
        self.assertEqual(result['record']['result']['status'],'no_release')
        result=self.gui(hidden=True)
        self.assertIn('Resultado salvo',result['status'],result)
        self.assertEqual(result['record']['result']['status'],'no_release')

    def test_version_is_qt_free_and_flags_are_exclusive(self):
        result=self.run_entry('--version',qt=False)
        self.assertEqual(result.returncode,0,result.stderr)
        for args in (('--updates','--service','literal.service'),('--updates','--diagnose'),('--updates','--version')):
            result=self.run_entry(*args,qt=False)
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertNotIn('Traceback',result.stderr)

    def test_each_new_payload_and_isolation_marker_is_verified_before_qt(self):
        names=['workspace/Updates.qml','scripts/updates.py','scripts/updates_contract.py','scripts/updates_desktop_state.py','scripts/updates_desktop.py','scripts/__init__.py','workspace/__init__.py']
        for name in names:
            path=self.bundle/name;data=path.read_bytes()
            for missing in (False,True):
                with self.subTest(name=name,missing=missing):
                    if missing:path.unlink()
                    else:path.write_bytes(data+b'\n# drift\n')
                    result=self.run_entry('--updates',qt=False)
                    self.assertEqual(result.returncode,1,result.stderr)
                    self.assertNotIn('Qt for Python',result.stderr)
                    self.assertNotIn('Traceback',result.stderr)
                    path.write_bytes(data);path.chmod(0o644)

    def test_passive_diagnosis_loads_both_production_surfaces(self):
        result=self.run_entry('--diagnose')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)['runtime']['surfaces'],['composition','updates'])
        self.assertFalse(json.loads(result.stdout)['serviceContacted'])

    def test_reference_digest_uses_verified_canonical_manifest(self):
        path=self.bundle/'manifest.json';canonical=path.read_bytes()
        path.write_text(json.dumps(json.loads(canonical),indent=2)+'\n')
        report=self.gui()
        self.assertEqual(report['reference']['digest'],hashlib.sha256(canonical).hexdigest())


if __name__ == "__main__":
    unittest.main()
