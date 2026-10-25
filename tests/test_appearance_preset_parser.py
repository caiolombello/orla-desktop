"""Preset contract through real QML imports; no native desktop claims."""
import copy
import json
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
from PySide6.QtCore import QUrl, QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine, QQmlComponent, QQmlExpression

ROOT = Path(__file__).resolve().parents[1]
IDS = ["clock", "pomodoro", "music", "systemBattery", "quota", "peripherals", "recording"]

def preset():
    return {"formatVersion": "0.1-experimental", "kind": "orla-appearance-preset",
            "appearance": {"formatVersion": "0.1-experimental", "baseTheme": "paper",
                           "tokens": {"foreground": "#252B35", "muted": "#606c79",
                                      "accent": "#167361", "surface": "#f4f0e8", "border": "#cec9bf",
                                      "radius": 21, "spacing": 5, "opacity": 1,
                                      "iconSize": 42, "reducedMotion": False}},
            "widgets": [{"id": widget, "visible": index % 2 == 0} for index, widget in enumerate(reversed(IDS))]}

class AppearancePresetParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlEngine()
        self.component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(Path(__file__).with_name("AppearancePresetParserHarness.qml"))))
        self.root = self.component.create()
        self.assertIsNotNone(self.root, [e.toString() for e in self.component.errors()])

    def tearDown(self):
        if self.root is not None:
            self.root.deleteLater()
        self.component.deleteLater()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def call(self, method, *args):
        expression = QQmlExpression(self.engine.rootContext(), self.root,
                                   method + "(" + ",".join(json.dumps(a) for a in args) + ")")
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value if method == "serialized" else json.loads(value)

    def test_roundtrip_normalizes_colors_and_preserves_widget_order(self):
        value = preset()
        expected = copy.deepcopy(value)
        expected["appearance"]["tokens"]["foreground"] = "#252b35"
        captured = self.call("captureResult", value["appearance"], value["widgets"])
        self.assertEqual(captured, {"value": expected, "error": "", "errors": []})
        serialized = self.call("serialized", value)
        self.assertEqual(serialized, json.dumps(expected, separators=(",", ":")))
        self.assertEqual(self.call("parseResult", serialized), captured)

    def catalog(self, expression):
        component = QQmlComponent(self.engine)
        component.setData(b'import QtQuick\nimport "../package/contents/code/AppearancePresetCatalog.js" as Catalog\nQtObject {}',
                          QUrl.fromLocalFile(str(ROOT / 'tests/CatalogInline.qml')))
        owner = component.create()
        self.assertIsNotNone(owner, component.errorString())
        try:
            call = QQmlExpression(QQmlEngine.contextForObject(owner), owner, expression)
            value, _ = call.evaluate()
            self.assertFalse(call.hasError(), call.error().toString())
            return json.loads(value)
        finally:
            owner.deleteLater()
            component.deleteLater()

    def test_builtin_catalog_payloads_match_the_reviewed_choices_and_roundtrip(self):
        entries = self.catalog('JSON.stringify(Catalog.entries())')
        # ROADMAP C1 asks for an editable macOS-inspired composition alongside the four presets.
        self.assertEqual([entry['id'] for entry in entries], ['essencial', 'mare', 'estudio', 'jogo', 'macos'])
        essentials = json.loads((ROOT / 'themes/examples/essential.json').read_text())['tokens']
        jogo = json.loads((ROOT / 'themes/examples/mare.json').read_text())['tokens']
        jogo['reducedMotion'] = False
        dark = {'foreground': '#edf1f9', 'muted': '#9da9bf', 'accent': '#69d7c2', 'surface': '#111923',
                'border': '#3c4b65', 'radius': 18, 'spacing': 8, 'opacity': 1, 'iconSize': 42, 'reducedMotion': True}
        mare = dict(dark, surface='#283542', radius=20, spacing=5, opacity=219 / 255, reducedMotion=False)
        expected = [('paper', essentials, ['clock', 'systemBattery', 'music', 'pomodoro'], 2),
                    ('glass', mare, ['clock', 'music', 'systemBattery', 'pomodoro'], 3),
                    ('midnight', dark, ['pomodoro', 'music', 'clock', 'systemBattery'], 4),
                    ('midnight', jogo, ['music', 'clock', 'systemBattery', 'pomodoro'], 3),
                    ('glass', dict(mare, spacing=4, iconSize=48), ['music', 'clock', 'systemBattery', 'pomodoro'], 0)]
        for entry, (base, tokens, order, visible) in zip(entries, expected):
            with self.subTest(id=entry['id']):
                payload = {'formatVersion': '0.1-experimental', 'kind': 'orla-appearance-preset',
                           'appearance': {'formatVersion': '0.1-experimental', 'baseTheme': base, 'tokens': tokens},
                           'widgets': [{'id': widget, 'visible': index < visible}
                                       for index, widget in enumerate(order + ['quota', 'peripherals', 'recording'])]}
                self.assertEqual(set(entry), {'id', 'payload'})
                self.assertEqual(entry['payload'], payload)
                serialized = self.call('serialized', payload)
                self.assertEqual(self.call('parseResult', serialized)['value'], payload)
                self.assertEqual(set(json.loads(serialized)), {'formatVersion', 'kind', 'appearance', 'widgets'})

    def test_catalog_returns_independent_copies_without_metadata_or_profile_dependency(self):
        value = self.catalog('var a=Catalog.entries(); a[0].payload.widgets[0].visible=false; a[0].payload.appearance.tokens.radius=0; a[0].id="changed";'
                             'var b=Catalog.payload("essencial"); b.widgets.pop(); JSON.stringify(Catalog.entries())')
        self.assertEqual(value, self.catalog('JSON.stringify(Catalog.entries())'))
        self.assertIsNone(self.catalog('JSON.stringify(Catalog.payload("unknown"))'))

    def test_unknown_metadata_and_invalid_widgets_never_export(self):
        for key in ("profile", "paths", "launchers", "calendar", "context", "timer", "audio", "author", "__proto__"):
            value = preset()
            value[key] = "rejected-secret"
            result = self.call("validateResult", value)
            self.assertNotIn("value", result)
            self.assertNotIn("rejected-secret", json.dumps(result))
            self.assertEqual(self.call("serialized", value), "")
        for change in ("extra", "missing", "duplicate", "unknown", "nonboolean", "entry_extra"):
            value = preset()
            if change == "extra":
                value["widgets"].append({"id": "clock", "visible": True})
            elif change == "missing":
                value["widgets"].pop()
            elif change == "duplicate":
                value["widgets"][0]["id"] = value["widgets"][1]["id"]
            elif change == "unknown":
                value["widgets"][0]["id"] = "rejected-secret"
            elif change == "nonboolean":
                value["widgets"][0]["visible"] = 1
            else:
                value["widgets"][0]["name"] = "rejected-secret"
            with self.subTest(change=change):
                result = self.call("parseResult", json.dumps(value))
                self.assertNotIn("value", result)
                self.assertNotIn("rejected-secret", json.dumps(result))
        value = preset()
        value["appearance"]["author"] = "rejected-secret"
        self.assertNotIn("value", self.call("captureResult", value["appearance"], value["widgets"]))

    def test_required_envelopes_tokens_and_numeric_types_are_strict(self):
        original = preset()
        for group in ((), ("appearance",), ("appearance", "tokens")):
            target = original
            for key in group:
                target = target[key]
            for key in target:
                value = copy.deepcopy(original)
                changed = value
                for segment in group:
                    changed = changed[segment]
                del changed[key]
                with self.subTest(group=group, missing=key):
                    self.assertNotIn("value", self.call("validateResult", value))
        for path, replacement in ((("formatVersion",), "future"), (("kind",), "theme"),
                                  (("appearance", "baseTheme"), "unknown"),
                                  (("appearance", "tokens", "opacity"), 0.39),
                                  (("appearance", "tokens", "radius"), True),
                                  (("appearance", "tokens", "accent"), "#abcdef\n"),
                                  (("appearance", "tokens", "reducedMotion"), 0)):
            value = preset()
            changed = value
            for key in path[:-1]:
                changed = changed[key]
            changed[path[-1]] = replacement
            self.assertNotIn("value", self.call("validateResult", value))

    def test_strict_lexical_scanner_rejects_duplicates_bom_overflow_and_depth(self):
        raw = json.dumps(preset())
        samples = ["\ufeff" + raw, raw + " true", raw[:-1] + ",}", "[[[[[0]]]]]",
                   '{"widgets":1,"\\u0077idgets":2}', '{"unknown":1,"unknown":2}',
                   raw.replace('"radius": 21', '"radius": 1e999'),
                   raw.replace('"radius": 21', '"radius": NaN'),
                   raw.replace('"radius": 21', '"radius": -Infinity'),
                   raw.replace('"baseTheme": "paper"', '"baseTheme": "\\ud800"'),
                   raw.replace('"baseTheme": "paper"', '"baseTheme": "\\udfff"')]
        for text in samples:
            with self.subTest(text=text[:40]):
                self.assertNotIn("value", self.call("parseResult", text))
        self.assertEqual(self.call("parseResult", '{"widgets":1,"\\u0077idgets":2}')["errors"][0]["code"], "duplicate_key")
        self.assertEqual(self.call("parseResult", "[[[[[0]]]]]")["errors"][0]["code"], "depth")
        for unit in ("\ud800", "\udfff"):
            self.assertEqual(self.call("parseResult", unit)["errors"][0]["code"], "utf8")

    def test_utf8_byte_limit_and_underflow_preserve_existing_scanner_semantics(self):
        raw = json.dumps(preset())
        self.assertIn("value", self.call("parseResult", raw + " " * (65536 - len(raw.encode()))))
        self.assertEqual(self.call("parseResult", raw + " " * (65537 - len(raw.encode())))["errors"][0]["code"], "size")
        for character, count in (("é", 32762), ("😀", 16381)):
            text = '{"name":"' + character * count + '"}'
            self.assertEqual(len(text.encode()), 65535)
            self.assertEqual(self.call("parseResult", text + "  ")["errors"][0]["code"], "size")
            self.assertNotEqual(self.call("parseResult", text + " ")["errors"][0]["code"], "size")
        for number in ("1e-999", "-1e-999", "0." + "0" * 350 + "1"):
            result = self.call("parseResult", raw.replace('"radius": 21', '"radius": ' + number))
            self.assertEqual(result["value"]["appearance"]["tokens"]["radius"], 0)

    def test_schema_declares_closed_preset_appearance_and_unique_known_widgets(self):
        schema = json.loads((ROOT / "themes/schema/appearance-preset-0.1-experimental.schema.json").read_text())
        self.assertEqual((schema["x-maxBytes"], schema["x-maxDepth"]), (65536, 4))
        properties = schema["properties"]
        self.assertEqual(properties["formatVersion"]["const"], "0.1-experimental")
        self.assertEqual(properties["kind"]["const"], "orla-appearance-preset")
        appearance = properties["appearance"]
        self.assertEqual(appearance["properties"]["formatVersion"]["const"], "0.1-experimental")
        self.assertEqual(appearance["properties"]["baseTheme"]["enum"], ["glass", "midnight", "paper"])
        tokens = appearance["properties"]["tokens"]
        widgets = properties["widgets"]
        item = widgets["items"]
        for node, keys in ((schema, ["formatVersion", "kind", "appearance", "widgets"]),
                           (appearance, ["formatVersion", "baseTheme", "tokens"]),
                           (tokens, ["foreground", "muted", "accent", "surface", "border",
                                     "radius", "spacing", "opacity", "iconSize", "reducedMotion"]),
                           (item, ["id", "visible"])):
            self.assertEqual(node["type"], "object")
            self.assertIs(node["additionalProperties"], False)
            self.assertEqual(node["required"], keys)
            self.assertEqual(set(node["properties"]), set(keys))
        self.assertEqual((widgets["type"], widgets["minItems"], widgets["maxItems"]), ("array", 7, 7))
        self.assertEqual(item["properties"]["id"]["enum"], IDS)
        self.assertEqual(item["properties"]["visible"]["type"], "boolean")
        self.assertEqual([constraint["contains"]["properties"]["id"]["const"]
                          for constraint in widgets["allOf"]], IDS)
        for constraint in widgets["allOf"]:
            self.assertEqual(constraint["contains"]["type"], "object")
            self.assertEqual(constraint["contains"]["required"], ["id"])
            self.assertEqual((constraint["minContains"], constraint["maxContains"]), (1, 1))
        token_properties = tokens["properties"]
        for key, bounds in (("radius", (0, 32)), ("spacing", (0, 16)),
                            ("opacity", (0.4, 1)), ("iconSize", (24, 64))):
            self.assertEqual(token_properties[key], {"type": "number", "minimum": bounds[0], "maximum": bounds[1]})
        self.assertEqual(token_properties["reducedMotion"], {"type": "boolean"})
        for key in ("foreground", "muted", "accent", "surface", "border"):
            self.assertEqual(token_properties[key], {"$ref": "#/$defs/color"})
        self.assertEqual(schema["$defs"]["color"],
                         {"type": "string", "minLength": 1, "maxLength": 7,
                          "pattern": "^#[0-9A-Fa-f]{6}(?![\\s\\S])"})
