import os
from pathlib import Path
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlContext, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem


class SharedControlCenterRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engines = []
        self.components = []
        self.contexts = []
        self.roots = []
        self.warnings = []
        self.engine = self.new_engine()
        self.window, self.context = self.create(Path(__file__).with_name("SharedControlCenterRegistryHarness.qml"), self.engine)
        self.registry = self.window.property("registry")
        self.client_a = self.window.property("clientA")
        self.client_b = self.window.property("clientB")
        self.host = self.window.property("host")
        self.anchor = self.window.property("anchor")
        self.app.processEvents()

    def new_engine(self):
        engine = QQmlEngine()
        engine.warnings.connect(lambda rows: self.warnings.extend(row.toString() for row in rows))
        self.engines.append(engine)
        return engine

    def create(self, path, engine):
        context = QQmlContext(engine.rootContext())
        self.contexts.append(context)
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(path.resolve())))
        self.components.append(component)
        self.assertFalse(component.isError(), [error.toString() for error in component.errors()])
        root = component.create(context)
        self.assertIsNotNone(root, [error.toString() for error in component.errors()])
        self.roots.append(root)
        return root, context

    def evaluate(self, source, target=None, context=None):
        expression = QQmlExpression(context or self.context, target or self.window, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def drain(self):
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def tearDown(self):
        for roots in (self.roots, self.components, self.contexts, self.engines):
            for root in reversed(roots):
                if shiboken6.isValid(root):
                    root.deleteLater()
            self.drain()
        self.assertEqual(self.warnings, [])

    def owner(self, slot="a"):
        self.assertTrue(self.evaluate("makeOwner('%s')" % slot))
        return self.window.property("ownerA" if slot == "a" else "ownerB")

    def open_a(self):
        return self.evaluate("clientA.open(host, anchor)")

    def test_zero_late_one_two_owners_do_not_elect_or_construct_hardware(self):
        self.assertEqual(self.registry.property("status"), "unavailable")
        self.assertEqual(self.registry.property("ownerCount"), 0)
        self.assertFalse(self.open_a())
        self.assertTrue(self.client_a.property("error"))
        owner = self.owner()
        self.assertEqual(self.registry.property("status"), "ready")
        self.assertTrue(self.open_a())
        self.assertEqual(owner.property("requestCount"), 1)
        self.assertEqual(owner.property("lastHost"), self.host)
        self.assertEqual(owner.property("lastAnchor"), self.anchor)
        second = self.owner("b")
        self.assertEqual(self.registry.property("status"), "ambiguous")
        self.assertEqual(self.registry.property("ownerCount"), 2)
        self.assertIsNone(self.registry.property("owner"))
        self.assertEqual(owner.property("releaseCount"), 1)
        self.assertFalse(self.open_a())
        self.assertEqual(second.property("requestCount"), 0)
        self.assertEqual(self.window.property("hardwareFactories"), 0)

    def test_versions_objects_and_host_windows_are_validated_without_coercion(self):
        owner = self.owner()
        generation = self.registry.property("generation")
        for version in ("'1'", "true", "new Number(1)", "NaN", "2", "null", "undefined"):
            self.assertFalse(self.evaluate("registry.registerOwner(ownerA, %s)" % version))
            self.assertFalse(self.evaluate("registry.requestOpen(clientA, host, anchor, %s)" % version))
        self.assertEqual(self.registry.property("generation"), generation)
        self.assertFalse(self.evaluate("registry.registerOwner(({requestControlCenter:function(){}}), 1)"))
        for args in ("null, host, anchor", "clientA, null, anchor", "clientA, host, null",
                     "clientA, host, otherAnchor", "clientA, ownerA, anchor",
                     "clientA, ({Window:{window:otherWindow}}), anchor"):
            self.assertFalse(self.evaluate("registry.requestOpen(%s, 1)" % args))
        self.assertFalse(self.evaluate("clientA.open(host, otherAnchor)"))
        self.assertEqual(owner.property("requestCount"), 0)
        self.assertLessEqual(len(self.client_a.property("error")), 256)

    def test_duplicate_and_explicit_unregister_have_one_generation_each(self):
        owner = self.owner()
        generation = self.registry.property("generation")
        self.assertFalse(self.evaluate("registry.registerOwner(ownerA, 1)"))
        self.assertEqual(self.registry.property("generation"), generation)
        self.assertTrue(self.evaluate("registry.unregisterOwner(ownerA)"))
        self.assertEqual(self.registry.property("generation"), generation + 1)
        self.assertEqual(self.registry.property("ownerCount"), 0)
        self.assertFalse(self.evaluate("registry.unregisterOwner(ownerA)"))
        self.assertEqual(self.registry.property("generation"), generation + 1)
        self.assertTrue(shiboken6.isValid(owner))

    def test_owner_destruction_without_unregister_advances_generation_and_cancels(self):
        owner = self.owner()
        self.assertTrue(self.open_a())
        generation = self.registry.property("generation")
        owner.deleteLater()
        self.drain()
        self.assertFalse(shiboken6.isValid(owner))
        self.assertEqual(self.registry.property("generation"), generation + 1)
        self.assertEqual(self.registry.property("status"), "unavailable")
        self.assertFalse(self.client_a.property("isOpen"))
        self.assertFalse(self.open_a())
        replacement = self.owner("b")
        self.assertTrue(self.open_a())
        self.assertEqual(replacement.property("requestCount"), 1)

    def test_two_clients_release_only_the_owner_and_surface_they_dispatched(self):
        owner = self.owner()
        self.assertTrue(self.open_a())
        self.drain()
        self.assertTrue(self.client_a.property("isOpen"))
        self.assertFalse(self.client_b.property("isOpen"))
        self.assertTrue(self.evaluate("clientB.open(host, anchor)"))
        self.drain()
        self.assertFalse(self.client_a.property("isOpen"))
        self.assertTrue(self.client_b.property("isOpen"))
        self.evaluate("clientA.release()")
        self.assertEqual(owner.property("lastReleasedClient"), self.client_a)
        self.assertTrue(self.client_b.property("isOpen"))
        self.evaluate("clientB.release()")
        self.assertFalse(self.client_b.property("isOpen"))

    def test_changed_registry_releases_exact_old_owner_never_new_unique_owner(self):
        old = self.owner()
        self.assertTrue(self.open_a())
        self.assertTrue(self.evaluate("registry.unregisterOwner(ownerA)"))
        self.assertEqual(old.property("releaseCount"), 1)
        new = self.owner("b")
        self.evaluate("clientA.release()")
        self.assertEqual(new.property("releaseCount"), 0)
        self.assertEqual(old.property("releaseCount"), 1)
        self.assertTrue(self.open_a())
        self.assertEqual(new.property("requestCount"), 1)

    def test_release_before_queued_open_prevents_stale_visible_surface(self):
        owner = self.owner()
        self.assertTrue(self.open_a())
        self.assertFalse(self.client_a.property("isOpen"))
        self.evaluate("clientA.release()")
        self.drain()
        self.assertIsNone(owner.property("currentClient"))
        self.assertIsNone(owner.property("pendingClient"))
        self.assertFalse(self.client_a.property("isOpen"))
        self.assertEqual(owner.property("releaseCount"), 1)

    def test_ambiguity_during_acceptance_cancels_exact_prepared_owner(self):
        owner = self.owner()
        self.evaluate("ownerA.requestHook=function(){makeOwner('b')}")
        self.assertFalse(self.open_a())
        self.drain()
        self.assertEqual(owner.property("releaseCount"), 1)
        self.assertIsNone(owner.property("currentClient"))
        self.assertFalse(self.client_a.property("isOpen"))

    def test_non_boolean_or_throwing_acceptance_releases_and_bounds_error(self):
        owner = self.owner()
        for value in ("'true'", "1", "false"):
            self.evaluate("ownerA.acceptedValue=%s" % value)
            self.assertFalse(self.open_a())
            self.drain()
            self.assertIsNone(owner.property("currentClient"))
        self.evaluate("ownerA.requestHook=function(){throw new Error('<b>'+ 'X'.repeat(1000))}")
        self.assertFalse(self.open_a())
        self.drain()
        self.assertLessEqual(len(self.client_a.property("error")), 256)
        self.assertNotIn("<b>", self.client_a.property("error"))
        self.assertFalse(self.client_a.property("isOpen"))

    def test_superseded_acceptance_cannot_release_a_reentrant_successor(self):
        owner = self.owner()
        self.evaluate("ownerA.requestHook=function(){ownerA.requestHook=null; clientA.open(host,anchor)}")
        self.assertFalse(self.open_a())
        self.drain()
        self.assertTrue(self.client_a.property("isOpen"))
        self.assertEqual(owner.property("requestCount"), 2)
        self.assertEqual(owner.property("releaseCount"), 1)
        self.assertEqual(self.client_a.property("error"), "")

    def test_open_during_owner_release_refuses_without_inner_callback_or_state_changes(self):
        owner = self.owner()
        self.assertTrue(self.open_a())
        self.drain()
        self.assertTrue(self.client_a.property("isOpen"))
        self.evaluate("ownerA.releaseHook=function(){ownerA.releaseHook=null;"
                      "reentrantAccepted=clientA.open(host,newAnchor);"
                      "requestsDuringReentry=ownerA.requestCount}")
        self.assertTrue(self.open_a())
        facts = {"innerAccepted": self.window.property("reentrantAccepted"),
                 "requestsDuringReentry": self.window.property("requestsDuringReentry"),
                 "finalRequests": owner.property("requestCount"),
                 "finalReleases": owner.property("releaseCount")}
        self.assertFalse(facts["innerAccepted"], facts)
        self.assertEqual(facts["requestsDuringReentry"], 1)
        self.assertEqual(facts["finalRequests"], 2)
        self.assertEqual(facts["finalReleases"], 1)
        self.assertEqual(owner.property("lastAnchor"), self.anchor)
        self.assertEqual(self.client_a.property("error"), "")
        self.drain()
        self.assertTrue(self.client_a.property("isOpen"))

    def test_async_owner_error_is_bounded_and_visible_only_to_accepted_client(self):
        owner = self.owner()
        self.assertTrue(self.open_a())
        owner.setProperty("transactionError", "Não foi possível abrir a Central de Controle.")
        self.assertEqual(self.client_a.property("error"), "Não foi possível abrir a Central de Controle.")
        self.assertEqual(self.client_b.property("error"), "")
        self.assertTrue(self.evaluate("clientB.open(host, anchor)"))
        owner.setProperty("transactionError", "Falha sintética " * 40)
        self.assertEqual(self.client_a.property("error"), "")
        self.assertEqual(len(self.client_b.property("error")), 256)
        self.evaluate("clientB.release()")
        self.assertEqual(self.client_b.property("error"), "")

    def test_client_disposal_releases_pending_owner(self):
        owner = self.owner()
        self.assertTrue(self.open_a())
        self.client_a.deleteLater()
        self.drain()
        self.assertEqual(owner.property("releaseCount"), 1)
        self.assertIsNone(owner.property("currentClient"))
        self.assertFalse(shiboken6.isValid(self.client_a))

    def test_anchor_destruction_and_window_loss_release_pending_owner(self):
        owner = self.owner()
        self.assertTrue(self.open_a())
        self.anchor.deleteLater()
        self.drain()
        self.assertEqual(owner.property("releaseCount"), 1)
        self.assertIsNone(owner.property("currentClient"))

    def test_host_detach_or_hidden_window_cancels_without_new_dispatch(self):
        owner = self.owner()
        self.assertTrue(self.open_a())
        self.host.setParentItem(None)
        self.assertEqual(owner.property("releaseCount"), 1)
        self.drain()
        self.assertFalse(self.client_a.property("isOpen"))
        self.assertEqual(owner.property("requestCount"), 1)

    def test_host_destruction_releases_pending_client_once(self):
        owner = self.owner()
        self.assertTrue(self.open_a())
        self.host.deleteLater()
        self.drain()
        self.assertEqual(owner.property("releaseCount"), 1)
        self.assertIsNone(owner.property("currentClient"))
        self.assertFalse(self.client_a.property("isOpen"))

    def test_anchor_moving_to_another_window_cancels_its_original_owner(self):
        owner = self.owner()
        self.assertTrue(self.open_a())
        self.evaluate("anchor.parent = otherAnchor.parent")
        self.assertEqual(owner.property("releaseCount"), 1)
        self.drain()
        self.assertFalse(self.client_a.property("isOpen"))
        self.assertIsNone(owner.property("currentClient"))

    def test_hidden_window_cancels_visible_client_and_opening_while_hidden_refuses(self):
        owner = self.owner()
        self.assertTrue(self.open_a())
        self.drain()
        self.window.setVisible(False)
        self.assertEqual(owner.property("releaseCount"), 1)
        self.assertFalse(self.open_a())
        self.assertEqual(owner.property("requestCount"), 1)

    def test_same_canonical_registry_has_object_identity_across_context_roots(self):
        second, _ = self.create(Path(__file__).with_name("SharedControlCenterRegistryHarness.qml"), self.engine)
        first_pointer = shiboken6.getCppPointer(self.registry)[0]
        second_pointer = shiboken6.getCppPointer(second.property("registry"))[0]
        self.assertEqual(first_pointer, second_pointer)
        self.owner()
        self.assertTrue(second.property("clientA").property("available"))

    def test_separate_engines_and_package_urls_keep_independent_registries(self):
        other, _ = self.create(Path(__file__).with_name("SharedControlCenterRegistryHarness.qml"), self.new_engine())
        self.assertNotEqual(shiboken6.getCppPointer(self.registry)[0],
                            shiboken6.getCppPointer(other.property("registry"))[0])
        self.owner()
        self.assertFalse(other.property("clientA").property("available"))
        with tempfile.TemporaryDirectory(prefix="orla-registry-fixture-") as directory:
            copied = Path(directory)
            source = Path(__file__).resolve().parents[1]
            (copied / "tests").mkdir()
            shutil.copyfile(Path(__file__), copied / "tests/test_shared_control_center_registry.py")
            shutil.copyfile(Path(__file__).with_name("SharedControlCenterRegistryHarness.qml"),
                            copied / "tests/SharedControlCenterRegistryHarness.qml")
            (copied / "package/contents/ui").mkdir(parents=True)
            shutil.copyfile(source / "package/contents/ui/ControlCenterEntry.qml",
                            copied / "package/contents/ui/ControlCenterEntry.qml")
            shutil.copytree(source / "package/contents/controlcenter", copied / "package/contents/controlcenter")
            split, _ = self.create(copied / "tests/SharedControlCenterRegistryHarness.qml", self.engine)
            self.assertNotEqual(shiboken6.getCppPointer(self.registry)[0],
                                shiboken6.getCppPointer(split.property("registry"))[0])
            self.assertFalse(split.property("clientA").property("available"))


if __name__ == "__main__":
    unittest.main()
