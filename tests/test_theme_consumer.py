"""Experimental QML JS consumer, checked against the independent Python format."""
import importlib.util
import json
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QJSEngine

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("theme_format", ROOT / "scripts/themes.py")
python_theme = importlib.util.module_from_spec(spec)
spec.loader.exec_module(python_theme)

class ThemeConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QJSEngine()
        code = ROOT / "package/contents/code"
        appearance = (code / "Appearance.js").read_text().replace(".pragma library", "")
        theme = (code / "Theme.js").read_text().replace(".pragma library", "").replace('.import "Appearance.js" as Appearance', "")
        result = self.engine.evaluate("var Appearance = (function(){" + appearance + ";return {formatVersion:formatVersion,validateTokens:validateTokens};})();" + theme)
        self.assertFalse(result.isError(), result.toString())

    def parse(self, text):
        result = self.engine.evaluate("JSON.stringify(parse(" + json.dumps(text) + "))")
        self.assertFalse(result.isError(), result.toString())
        return json.loads(result.toString())

    def test_both_external_examples_produce_canonical_tokens(self):
        for path in sorted((ROOT / "themes/examples").glob("*.json")):
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                self.assertEqual(self.parse(raw.decode())["value"], python_theme.parse_theme(raw))

    def differential(self, text, compare_error=True):
        actual = self.parse(text)
        try:
            expected = python_theme.parse_theme(text.encode("utf-8"))
        except python_theme.ThemeError as error:
            self.assertNotIn("value", actual, text[:160])
            if compare_error:
                self.assertEqual([(e["field"], e["code"]) for e in actual["errors"]],
                                 [(e["field"], e["code"]) for e in error.errors], text[:160])
        else:
            self.assertEqual(actual["value"], expected)
        return actual

    def example(self):
        return json.loads(next((ROOT / "themes/examples").glob("*.json")).read_text())

    def test_contract_corpus_matches_python_acceptance_and_canonicalization(self):
        base = self.example()
        for key in python_theme.ROOT_FIELDS:
            value = dict(base); del value[key]
            self.differential(json.dumps(value))
        for key in python_theme.TOKEN_FIELDS:
            value = self.example(); del value["tokens"][key]
            self.differential(json.dumps(value))
        root_changes = [("formatVersion", "future"), ("name", "João Açúcar"), ("author", "Müller"),
                        ("name", " A"), ("name", "A "), ("name", "A\n"), ("name", "<b>A</b>"),
                        ("name", "https://example.org"), ("name", "A" * 121), ("name", ""),
                        ("author", 1), ("license", "A" * 81), ("version", "01.2.3"),
                        ("version", "1.2.3\n"), ("version", "1.2.3-beta"), ("id", "Org.test"),
                        ("id", "org.test\n"), ("id", "__proto__"), ("assets", "file:///tmp/x"),
                        ("fonts", []), ("qml", "Qt.createQmlObject('')"), ("__proto__", {})]
        for key, replacement in root_changes:
            with self.subTest(root=key, value=replacement):
                value = dict(base); value[key] = replacement
                self.differential(json.dumps(value, ensure_ascii=False))
        token_changes = [("accent", "#ABCDEF"), ("accent", "#abc"), ("accent", "#abcdef\n"),
                         ("accent", 1), ("accent", "#gggggg"), ("iconSize", 23), ("iconSize", 64),
                         ("radius", 0), ("radius", 32), ("radius", 32.1), ("spacing", 16),
                         ("spacing", -1), ("spacing", 2.5), ("opacity", 0.4), ("opacity", 1),
                         ("opacity", 0.39), ("opacity", True), ("opacity", "0.5"),
                         ("reducedMotion", 1), ("reducedMotion", False), ("font", "sans")]
        for key, replacement in token_changes:
            with self.subTest(token=key, value=replacement):
                value = self.example(); value["tokens"][key] = replacement
                self.differential(json.dumps(value))

    def test_lexical_limits_duplicates_and_unicode(self):
        raw = json.dumps(self.example(), ensure_ascii=False)
        for text in ("\ufeff" + raw, raw + " true", raw[:-1] + ",}", '{"bad": "brace { \\\" }"}',
                     "[1,2,3]", "null", '[[[[]]]]', '[[[[[]]]]]', '{"__proto__":1,"__proto__":2}',
                     '{"id":"org.a","\\u0069d":"org.b"}', '{"x":{"tokens":{"accent":1,"accent":2}}}',
                     raw.replace('"radius": ' + str(self.example()["tokens"]["radius"]), '"radius": 1e999'),
                     raw.replace('"radius": ' + str(self.example()["tokens"]["radius"]), '"radius": NaN'),
                     raw.replace('"radius": ' + str(self.example()["tokens"]["radius"]), '"radius": -Infinity'),
                     raw.replace('"name":', '"name":', 1), " \t\r\n" + raw,
                     raw.replace('"author":', '"author":', 1)):
            self.differential(text)
        # Exact valid UTF-8 size uses JSON whitespace; one byte more must reject.
        self.differential(raw + " " * (65536 - len(raw.encode("utf-8"))))
        self.assertEqual(self.differential(raw + " " * (65537 - len(raw.encode("utf-8"))))["errors"][0]["code"], "size")
        # Multibyte byte counting reaches size before metadata validation.
        multi = '{"name":"' + "é" * 32762 + '"}'
        self.assertEqual(len(multi.encode()), 65535)
        self.differential(multi + " ")
        self.assertEqual(self.differential(multi + "  ")["errors"][0]["code"], "size")
        supplementary = '{"name":"' + "😀" * 16381 + '"}'
        self.assertEqual(len(supplementary.encode()), 65535)
        self.differential(supplementary + " ")
        self.assertEqual(self.differential(supplementary + "  ")["errors"][0]["code"], "size")
        for text in ('{"name":"\\ud800"}', '{"name":"\\ud83d\\ude00"}', '{"name":"😀"}'):
            self.differential(text)
        # Literal isolated UTF-16 units cannot originate in strict UTF-8 files.
        for unit in ("\ud800", "\udfff"):
            self.assertEqual(self.parse(unit)["errors"][0]["code"], "utf8")
        self.assertEqual(self.parse("a" * 1000000)["errors"][0]["code"], "size")

    def test_finite_underflow_numbers_match_python_zero(self):
        for key in python_theme.RANGES:
            value = self.example()
            value["tokens"][key] = 20
            text = json.dumps(value)
            for number in ("1e-999", "-1e-999", "1e-324", "-1e-324", "5e-324",
                           "0." + "0" * 350 + "1"):
                with self.subTest(token=key, number=number[:30]):
                    self.differential(text.replace('"' + key + '": 20', '"' + key + '": ' + number))
        for key, number in (("radius", "3.2e1"), ("spacing", "1.6e1"), ("opacity", "4e-1"), ("iconSize", "6.4e1")):
            value = self.example(); value["tokens"][key] = 20
            text = json.dumps(value)
            self.differential(text.replace('"' + key + '": 20', '"' + key + '": ' + number))
        text = json.dumps(self.example())
        text = text.replace('"author": "' + self.example()["author"] + '"', '"author": 1e999')
        self.assertEqual(self.differential(text)["errors"][0]["code"], "nonfinite")

    def test_external_document_is_not_an_internal_appearance_snapshot(self):
        raw = json.dumps(self.example())
        result = self.engine.evaluate("JSON.stringify((function(){" +
            (ROOT / "package/contents/code/Appearance.js").read_text().replace(".pragma library", "") +
            ";return parse(" + json.dumps(raw) + ");})())")
        self.assertFalse(result.isError(), result.toString())
        self.assertNotIn("value", json.loads(result.toString()))
