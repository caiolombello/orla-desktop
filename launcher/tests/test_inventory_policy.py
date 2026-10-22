import copy
import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "inventory_policy.py"
SPEC = importlib.util.spec_from_file_location("orla_launcher_inventory_policy", MODULE_PATH)
policy = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(policy)


class CatalogPolicyTracerTests(unittest.TestCase):
    def test_required_root_duplicate_occurrences_share_one_child(self):
        roots = [{"id": "staged_launcher", "path": "/synthetic-stage/bin/orla-launcher", "required": True}]
        main = {"type": "shared_object", "interpreter": "/lib64/ld-linux-x86-64.so.2",
                "needed": ["libSynthetic.so.1", "libSynthetic.so.1"],
                "rpath": [], "runpath": [], "flags": [], "unsupportedMechanisms": []}
        child = {"type": "shared_object", "interpreter": None, "needed": [],
                 "rpath": [], "runpath": [], "flags": [], "unsupportedMechanisms": []}
        objects = {"/synthetic-stage/bin/orla-launcher": main,
                   "/usr/lib64/libSynthetic.so.1.0": child}
        paths = {"/usr/lib64/libSynthetic.so.1": {
            "state": "object", "canonical": "/usr/lib64/libSynthetic.so.1.0"}}
        frozen = copy.deepcopy((roots, objects, paths))

        # The baseline public seam raises NotImplementedError("missing_policy").
        result = policy.resolve_catalog(roots, objects, paths)

        self.assertEqual(result["schema"], "orla-launcher-catalog-graph-0.1")
        self.assertEqual(result["policy"], "fedora44-usr-lib64-catalog-0.1")
        self.assertEqual(result["status"], "complete_for_supplied_catalog_policy")
        self.assertEqual(result["roots"], [{"id": "staged_launcher",
                         "path": "/synthetic-stage/bin/orla-launcher", "required": True, "status": "complete"}])
        self.assertEqual([node["path"] for node in result["nodes"]],
                         ["/synthetic-stage/bin/orla-launcher", "/usr/lib64/libSynthetic.so.1.0"])
        self.assertEqual([(edge["source"], edge["occurrence"], edge["name"], edge["candidate"], edge["target"], edge["state"])
                          for edge in result["edges"]], [
            ("/synthetic-stage/bin/orla-launcher", 0, "libSynthetic.so.1", "/usr/lib64/libSynthetic.so.1", "/usr/lib64/libSynthetic.so.1.0", "object"),
            ("/synthetic-stage/bin/orla-launcher", 1, "libSynthetic.so.1", "/usr/lib64/libSynthetic.so.1", "/usr/lib64/libSynthetic.so.1.0", "object"),
        ])
        self.assertEqual(result["coverage"], {"actualHost": "UNRUN", "loader": "UNRUN", "abi": "UNRUN", "lifecycle": "UNRUN"})
        self.assertEqual((roots, objects, paths), frozen)



class CatalogPolicyBasicsTests(unittest.TestCase):
    root_path = "/synthetic-stage/bin/orla-launcher"
    child_path = "/usr/lib64/libSynthetic.so.1.0"
    candidate = "/usr/lib64/libSynthetic.so.1"

    @staticmethod
    def tags(needed=(), **changes):
        value = {"type": "shared_object", "interpreter": None, "needed": list(needed),
                 "rpath": [], "runpath": [], "flags": [], "unsupportedMechanisms": []}
        value.update(changes)
        return value

    def fixture(self):
        return ([{"id": "staged_launcher", "path": self.root_path, "required": True}],
                {self.root_path: self.tags(["libSynthetic.so.1"], interpreter="/lib64/ld-linux-x86-64.so.2"),
                 self.child_path: self.tags()},
                {self.candidate: {"state": "object", "canonical": self.child_path}})

    def resolve_unchanged(self, roots, objects, paths, **kwargs):
        before = copy.deepcopy((roots, objects, paths, kwargs))
        result = policy.resolve_catalog(roots, objects, paths, **kwargs)
        self.assertEqual((roots, objects, paths, kwargs), before)
        self.assertEqual(result["coverage"], {"actualHost": "UNRUN", "loader": "UNRUN", "abi": "UNRUN", "lifecycle": "UNRUN"})
        return result

    def test_relative_two_hop_alias_chain_resolves_shared_canonical_child(self):
        roots, objects, paths = self.fixture()
        intermediate = "/usr/lib64/links/libSynthetic.so.1"
        paths = {self.candidate: {"state": "alias", "target": "links/libSynthetic.so.1"},
                 intermediate: {"state": "alias", "target": "../libSynthetic.so.1.0"},
                 self.child_path: {"state": "object", "canonical": self.child_path}}
        result = self.resolve_unchanged(roots, objects, paths)
        self.assertEqual(result["status"], "complete_for_supplied_catalog_policy")
        self.assertEqual([node["path"] for node in result["nodes"]], [self.root_path, self.child_path])
        edge = result["edges"][0]
        self.assertEqual((edge["state"], edge["catalogState"], edge["target"]), ("object", "object", self.child_path))
        self.assertEqual(edge["occurrence"], 0)

    def test_unprovided_candidate_is_unknown_not_known_catalog_absence(self):
        roots, objects, _paths = self.fixture()
        result = self.resolve_unchanged(roots, objects, {})
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["roots"][0]["status"], "unknown")
        edge = result["edges"][0]
        self.assertEqual((edge["state"], edge["catalogState"], edge["target"]), ("unknown", "unknown", None))
        self.assertEqual(edge["contexts"], [{"root": "staged_launcher", "state": "unknown", "reasons": ["candidate_unprovided"]}])
        self.assertEqual([node["path"] for node in result["nodes"]], [self.root_path])

    def test_explicit_catalog_absence_has_distinct_root_and_aggregate_state(self):
        roots, objects, _paths = self.fixture()
        result = self.resolve_unchanged(roots, objects, {self.candidate: {"state": "absent_in_catalog"}})
        self.assertEqual(result["status"], "absent_in_catalog")
        self.assertEqual(result["roots"][0]["status"], "absent_in_catalog")
        edge = result["edges"][0]
        self.assertEqual((edge["state"], edge["catalogState"], edge["target"]), ("absent_in_catalog", "absent_in_catalog", None))

    def test_explicit_unknown_candidate_and_missing_endpoint_data_remain_unknown(self):
        for observation, include_child in (({"state": "unknown"}, True),
                                           ({"state": "object", "canonical": self.child_path}, False)):
            with self.subTest(observation=observation, include_child=include_child):
                roots, objects, _paths = self.fixture()
                if not include_child: del objects[self.child_path]
                result = self.resolve_unchanged(roots, objects, {self.candidate: observation})
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(result["edges"][0]["catalogState"], "unknown")
                self.assertIsNone(result["edges"][0]["target"])

    def test_cycle_shared_child_and_duplicate_edges_keep_deterministic_bfs_order(self):
        roots, _objects, _paths = self.fixture()
        a, b, shared = ("/usr/lib64/" + name for name in ("libA.so", "libB.so", "libShared.so"))
        objects = {self.root_path: self.tags(["libA.so", "libB.so", "libA.so"]),
                   a: self.tags(["libShared.so"]), b: self.tags(["libShared.so"]),
                   shared: self.tags(["libA.so"])}
        paths = {path: {"state": "object", "canonical": path} for path in (a, b, shared)}
        result = self.resolve_unchanged(roots, objects, paths)
        reversed_result = self.resolve_unchanged(roots, dict(reversed(list(objects.items()))), dict(reversed(list(paths.items()))))
        self.assertEqual(result, reversed_result)
        self.assertEqual(result["status"], "complete_for_supplied_catalog_policy")
        self.assertEqual([node["path"] for node in result["nodes"]], [self.root_path, a, b, shared])
        self.assertEqual([(edge["source"], edge["occurrence"], edge["target"]) for edge in result["edges"]],
                         [(self.root_path, 0, a), (self.root_path, 1, b), (self.root_path, 2, a),
                          (a, 0, shared), (b, 0, shared), (shared, 0, a)])

    def test_own_path_flags_and_unsupported_mechanism_keep_known_candidate_identity(self):
        blockers = [("rpath", ["$ORIGIN"], "own_rpath"),
                    ("runpath", ["/synthetic/alternate"], "own_runpath"),
                    ("flags", [{"tag": 30, "value": 8}], "nonzero_dynamic_flags"),
                    ("unsupportedMechanisms", [{"tag": 0x7fffffff, "value": 1}], "unsupported_mechanism")]
        for key, value, reason in blockers:
            with self.subTest(key=key):
                roots, objects, paths = self.fixture()
                objects[self.root_path][key] = value
                result = self.resolve_unchanged(roots, objects, paths)
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(result["roots"][0]["status"], "unknown")
                edge = result["edges"][0]
                self.assertEqual((edge["state"], edge["catalogState"], edge["target"]), ("object", "object", self.child_path))
                self.assertEqual(edge["contexts"], [{"root": "staged_launcher", "state": "unknown", "reasons": [reason]}])
                self.assertIn(self.child_path, [node["path"] for node in result["nodes"]])

    def test_malformed_records_and_input_caps_are_rejected_without_mutation(self):
        cases = []
        roots, objects, paths = self.fixture()
        bad_roots = copy.deepcopy(roots); bad_roots[0]["required"] = 1
        cases.append((bad_roots, objects, paths, {}, "policy_roots"))
        cases.append(([{"id": "root" + str(i), "path": self.root_path, "required": True} for i in range(17)],
                      objects, paths, {}, "policy_roots"))
        bad_objects = copy.deepcopy(objects); bad_objects[self.root_path]["provenance"] = "invented"
        cases.append((roots, bad_objects, paths, {}, "policy_objects"))
        bad_objects = copy.deepcopy(objects); bad_objects[self.root_path]["needed"] = ["../unsafe.so"]
        cases.append((roots, bad_objects, paths, {}, "policy_objects"))
        bad_objects = copy.deepcopy(objects); bad_objects[self.root_path]["needed"] = ["libRepeated.so"] * 257
        cases.append((roots, bad_objects, paths, {}, "policy_objects"))
        bad_objects = {"/usr/lib64/lib" + str(i) + ".so": self.tags() for i in range(257)}
        cases.append((roots, bad_objects, paths, {}, "policy_objects"))
        cases.append((roots, objects, {self.candidate: {"state": "unknown", "canonical": self.child_path}}, {}, "policy_paths"))
        bad_paths = {"/usr/lib64/lib" + str(i) + ".so": {"state": "unknown"} for i in range(4097)}
        cases.append((roots, objects, bad_paths, {}, "policy_paths"))
        for limits in ({"nodes": True}, {"roots": 0}, {"edges": 4097}, {"aliasHops": 17}, {"mystery": 1}):
            cases.append((roots, objects, paths, {"limits": limits}, "policy_limits"))
        for selected_roots, selected_objects, selected_paths, kwargs, code in cases:
            with self.subTest(code=code, kwargs=kwargs, objects=len(selected_objects), paths=len(selected_paths)):
                before = copy.deepcopy((selected_roots, selected_objects, selected_paths, kwargs))
                with self.assertRaises(ValueError) as raised:
                    policy.resolve_catalog(selected_roots, selected_objects, selected_paths, **kwargs)
                self.assertEqual(type(raised.exception).__name__, "PolicyError")
                self.assertEqual(raised.exception.code, code)
                self.assertEqual((selected_roots, selected_objects, selected_paths, kwargs), before)



class CatalogPolicyContextTests(unittest.TestCase):
    def test_late_inherited_rpath_reaches_shared_descendant_in_both_branch_orders(self):
        root_path = "/synthetic-stage/bin/orla-launcher"
        a, b, shared, child = ("/usr/lib64/" + name for name in
                               ("libA.so", "libB.so", "libShared.so", "libChild.so"))
        effective = []
        for order in (("libA.so", "libB.so"), ("libB.so", "libA.so")):
            with self.subTest(order=order):
                roots = [{"id": "staged_launcher", "path": root_path, "required": True}]
                tags = CatalogPolicyBasicsTests.tags
                objects = {root_path: tags(order, interpreter="/lib64/ld-linux-x86-64.so.2"),
                           a: tags(["libShared.so"]),
                           b: tags(["libShared.so"], rpath=["$ORIGIN"]),
                           shared: tags(["libChild.so"]), child: tags()}
                paths = {path: {"state": "object", "canonical": path} for path in (a, b, shared, child)}
                before = copy.deepcopy((roots, objects, paths))
                result = policy.resolve_catalog(roots, objects, paths)
                self.assertEqual((roots, objects, paths), before)
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(result["roots"][0]["status"], "unknown")
                edge = next(edge for edge in result["edges"] if edge["source"] == shared)
                # Catalog identity stays known when a later search context blocks
                # this already-discovered shared object's dependent occurrence.
                self.assertEqual((edge["occurrence"], edge["name"], edge["candidate"], edge["target"],
                                  edge["state"], edge["catalogState"]),
                                 (0, "libChild.so", child, child, "object", "object"))
                effective.append(copy.deepcopy(edge["contexts"]))
                self.assertEqual(edge["contexts"], [{"root": "staged_launcher", "state": "unknown",
                                                     "reasons": ["inherited_rpath"]}])
                for node in result["nodes"]:
                    self.assertNotIn("state", node)
                    self.assertNotIn("blocked", node)
                self.assertEqual(result["coverage"], {"actualHost": "UNRUN", "loader": "UNRUN",
                                                       "abi": "UNRUN", "lifecycle": "UNRUN"})
        self.assertEqual(effective[0], effective[1])



class CatalogPolicyMultiRootTests(unittest.TestCase):
    def test_required_priority_optional_context_isolation_and_exact_budget_frontier(self):
        optional = "/synthetic-stage/bin/optional-root"
        required = "/synthetic-stage/bin/orla-launcher"
        shared, child = "/usr/lib64/libShared.so", "/usr/lib64/libChild.so"
        roots = [{"id": "optional_root", "path": optional, "required": False},
                 {"id": "staged_launcher", "path": required, "required": True}]
        tags = CatalogPolicyBasicsTests.tags
        objects = {optional: tags(["libShared.so"], rpath=["$ORIGIN"]),
                   required: tags(["libShared.so"]), shared: tags(["libChild.so"]), child: tags()}
        paths = {path: {"state": "object", "canonical": path} for path in (shared, child)}
        before = copy.deepcopy((roots, objects, paths))

        result = policy.resolve_catalog(roots, objects, paths)
        self.assertEqual((roots, objects, paths), before)
        self.assertEqual(result["status"], "complete_for_supplied_catalog_policy")
        self.assertEqual([(item["id"], item["status"]) for item in result["roots"]],
                         [("optional_root", "unknown"), ("staged_launcher", "complete")])
        self.assertEqual([node["path"] for node in result["nodes"]], [required, shared, child, optional])
        edge = next(edge for edge in result["edges"] if edge["source"] == shared)
        self.assertEqual((edge["target"], edge["state"], edge["catalogState"]), (child, "object", "object"))
        self.assertEqual(edge["contexts"], [
            {"root": "staged_launcher", "state": "complete", "reasons": []},
            {"root": "optional_root", "state": "unknown", "reasons": ["inherited_rpath"]},
        ])
        self.assertEqual(result["coverage"], {"actualHost": "UNRUN", "loader": "UNRUN", "abi": "UNRUN", "lifecycle": "UNRUN"})

        limited = policy.resolve_catalog(roots, objects, paths, limits={"nodes": 3, "edges": 2})
        self.assertEqual((roots, objects, paths), before)
        self.assertEqual(limited["status"], "complete_for_supplied_catalog_policy")
        self.assertEqual([(item["id"], item["status"]) for item in limited["roots"]],
                         [("optional_root", "unknown"), ("staged_launcher", "complete")])
        self.assertEqual([node["path"] for node in limited["nodes"]], [required, shared, child])
        self.assertEqual(len(limited["edges"]), 2)
        self.assertLessEqual(len(limited["nodes"]), 3)
        self.assertLessEqual(len(limited["edges"]), 2)
        self.assertTrue(any(item["root"] == "optional_root" and item["reason"] == "node_limit"
                            for item in limited["incomplete"]))
        shared_edge = next(edge for edge in limited["edges"] if edge["source"] == shared)
        self.assertEqual(shared_edge["contexts"], [{"root": "staged_launcher", "state": "complete", "reasons": []}])
        self.assertEqual(limited["coverage"], result["coverage"])

        with self.assertRaises(ValueError) as raised:
            policy.resolve_catalog(roots, objects, paths, limits={"roots": 1})
        self.assertEqual(type(raised.exception).__name__, "PolicyError")
        self.assertEqual(raised.exception.code, "policy_roots")
        self.assertEqual((roots, objects, paths), before)



class CatalogPolicyAdversarialTests(unittest.TestCase):
    root_path = "/synthetic-stage/bin/orla-launcher"
    candidate = "/usr/lib64/libSynthetic.so.1"
    child_path = "/usr/lib64/libSynthetic.so.1.0"

    def fixture(self):
        return CatalogPolicyBasicsTests().fixture()

    def resolve_unchanged(self, roots, objects, paths, **kwargs):
        before = copy.deepcopy((roots, objects, paths, kwargs))
        result = policy.resolve_catalog(roots, objects, paths, **kwargs)
        self.assertEqual((roots, objects, paths, kwargs), before)
        return result

    def test_canonical_endpoint_conflict_is_unknown_even_with_declared_object_tags(self):
        for conflict in ({"state": "absent_in_catalog"}, {"state": "unknown"},
                         {"state": "alias", "target": "libOther.so"},
                         {"state": "object", "canonical": "/usr/lib64/libOther.so"}):
            with self.subTest(conflict=conflict):
                roots, objects, paths = self.fixture()
                objects["/usr/lib64/libOther.so"] = CatalogPolicyBasicsTests.tags()
                paths[self.child_path] = conflict
                paths["/usr/lib64/libOther.so"] = {"state": "object", "canonical": "/usr/lib64/libOther.so"}
                result = self.resolve_unchanged(roots, objects, paths)
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(result["roots"][0]["status"], "unknown")
                edge = result["edges"][0]
                self.assertEqual(edge["catalogState"], "unknown")
                self.assertIsNone(edge["target"])
                self.assertIn("canonical_conflict", edge["contexts"][0]["reasons"])

    def test_alias_loop_escape_and_incomplete_chain_are_unknown(self):
        cases = [({self.candidate: {"state": "alias", "target": "libLoop.so"},
                   "/usr/lib64/libLoop.so": {"state": "alias", "target": "libSynthetic.so.1"}}, "alias_cycle"),
                 ({self.candidate: {"state": "alias", "target": "../../etc/synthetic.so"}}, "alias_escape"),
                 ({self.candidate: {"state": "alias", "target": "missing-synthetic.so"}}, "candidate_unprovided")]
        for paths, reason in cases:
            with self.subTest(reason=reason):
                roots, objects, _paths = self.fixture()
                result = self.resolve_unchanged(roots, objects, paths)
                self.assertEqual(result["status"], "unknown")
                self.assertIsNone(result["edges"][0]["target"])
                self.assertIn(reason, result["edges"][0]["contexts"][0]["reasons"])

    def test_exact_sixteen_alias_hops_complete_seventeen_refuse(self):
        for count, expected in ((16, "complete_for_supplied_catalog_policy"), (17, "unknown")):
            with self.subTest(count=count):
                roots, objects, _paths = self.fixture()
                chain = [self.candidate] + ["/usr/lib64/synthetic-hop-" + str(i) + ".so" for i in range(1, count)] + [self.child_path]
                paths = {source: {"state": "alias", "target": target.rsplit("/", 1)[1]}
                         for source, target in zip(chain, chain[1:])}
                paths[self.child_path] = {"state": "object", "canonical": self.child_path}
                result = self.resolve_unchanged(roots, objects, paths)
                self.assertEqual(result["status"], expected)
                if count == 16:
                    self.assertEqual(result["edges"][0]["target"], self.child_path)
                else:
                    self.assertIn("alias_hop_limit", result["edges"][0]["contexts"][0]["reasons"])

    def test_runpath_blocks_own_edge_but_is_not_inherited(self):
        roots, objects, paths = self.fixture()
        leaf = "/usr/lib64/libLeaf.so"
        objects[self.root_path]["runpath"] = ["$ORIGIN"]
        objects[self.child_path]["needed"] = ["libLeaf.so"]
        objects[leaf] = CatalogPolicyBasicsTests.tags()
        paths[leaf] = {"state": "object", "canonical": leaf}
        result = self.resolve_unchanged(roots, objects, paths)
        self.assertEqual(result["status"], "unknown")
        root_edge = next(edge for edge in result["edges"] if edge["source"] == self.root_path)
        child_edge = next(edge for edge in result["edges"] if edge["source"] == self.child_path)
        self.assertEqual(root_edge["contexts"][0]["reasons"], ["own_runpath"])
        self.assertEqual(child_edge["contexts"], [{"root": "staged_launcher", "state": "complete", "reasons": []}])

    def test_shared_cycle_propagates_inherited_rpath_to_fixed_point(self):
        roots, _objects, _paths = self.fixture()
        a, b, leaf = "/usr/lib64/libA.so", "/usr/lib64/libB.so", "/usr/lib64/libLeaf.so"
        tags = CatalogPolicyBasicsTests.tags
        objects = {self.root_path: tags(["libA.so"]), a: tags(["libB.so", "libLeaf.so"]),
                   b: tags(["libA.so"], rpath=["$ORIGIN"]), leaf: tags()}
        paths = {path: {"state": "object", "canonical": path} for path in (a, b, leaf)}
        result = self.resolve_unchanged(roots, objects, paths)
        self.assertEqual(result["status"], "unknown")
        leaf_edge = next(edge for edge in result["edges"] if edge["source"] == a and edge["target"] == leaf)
        self.assertEqual(leaf_edge["contexts"], [{"root": "staged_launcher", "state": "unknown", "reasons": ["inherited_rpath"]}])
        self.assertEqual(len(result["nodes"]), 4)
        self.assertEqual(len(result["edges"]), 4)

    def test_required_exact_node_edge_boundaries_and_exhaustion_frontiers(self):
        roots, objects, paths = self.fixture()
        for limits, expected, reason in (({"nodes": 2, "edges": 1}, "complete_for_supplied_catalog_policy", None),
                                         ({"nodes": 1, "edges": 1}, "unknown", "node_limit")):
            with self.subTest(limits=limits):
                result = self.resolve_unchanged(roots, objects, paths, limits=limits)
                self.assertEqual(result["status"], expected)
                self.assertLessEqual(len(result["nodes"]), limits["nodes"])
                self.assertLessEqual(len(result["edges"]), limits["edges"])
                if reason:
                    self.assertTrue(any(item["root"] == "staged_launcher" and item["reason"] == reason for item in result["incomplete"]))
                    self.assertEqual(result["edges"][0]["catalogState"], "object")
        objects[self.root_path]["needed"] *= 2
        exact = self.resolve_unchanged(roots, objects, paths, limits={"nodes": 2, "edges": 2})
        limited = self.resolve_unchanged(roots, objects, paths, limits={"nodes": 2, "edges": 1})
        self.assertEqual(exact["status"], "complete_for_supplied_catalog_policy")
        self.assertEqual([edge["occurrence"] for edge in exact["edges"]], [0, 1])
        self.assertEqual(limited["status"], "unknown")
        self.assertEqual(len(limited["edges"]), 1)
        self.assertTrue(any(item["root"] == "staged_launcher" and item["reason"] == "edge_limit"
                            and item["occurrence"] == 1 for item in limited["incomplete"]))

    def test_missing_root_is_unknown_duplicate_ids_and_unsafe_records_reject(self):
        roots, objects, paths = self.fixture()
        missing = copy.deepcopy(objects); del missing[self.root_path]
        self.assertEqual(self.resolve_unchanged(roots, missing, paths)["status"], "unknown")
        cases = []
        cases.append((roots * 2, objects, paths, "policy_roots"))
        unsafe_roots = copy.deepcopy(roots); unsafe_roots[0]["path"] = "/synthetic-stage/../unsafe"
        cases.append((unsafe_roots, objects, paths, "policy_roots"))
        long_roots = copy.deepcopy(roots); long_roots[0]["id"] = "x" * 65
        cases.append((long_roots, objects, paths, "policy_roots"))
        unsafe_objects = copy.deepcopy(objects); unsafe_objects["/usr/lib64/../unsafe.so"] = CatalogPolicyBasicsTests.tags()
        cases.append((roots, unsafe_objects, paths, "policy_objects"))
        for flags in ([{"tag": True, "value": 0}], [{"tag": 30, "value": True}]):
            values = copy.deepcopy(objects); values[self.root_path]["flags"] = flags
            cases.append((roots, values, paths, "policy_objects"))
        for changes in ({"rpath": ["x" * 4097]}, {"needed": ["x" * 256]}, {"interpreter": "relative/python"}, {"type": []}):
            values = copy.deepcopy(objects); values[self.root_path].update(changes)
            cases.append((roots, values, paths, "policy_objects"))
        cases.append((roots, objects, {"/usr/lib64//unsafe.so": {"state": "unknown"}}, "policy_paths"))
        cases.append((roots, objects, {self.candidate: {"state": "alias", "target": "x" * 4097}}, "policy_paths"))
        for selected_roots, selected_objects, selected_paths, code in cases:
            with self.subTest(code=code):
                before = copy.deepcopy((selected_roots, selected_objects, selected_paths))
                with self.assertRaises(ValueError) as raised:
                    policy.resolve_catalog(selected_roots, selected_objects, selected_paths)
                self.assertEqual(type(raised.exception).__name__, "PolicyError")
                self.assertEqual(raised.exception.code, code)
                self.assertEqual((selected_roots, selected_objects, selected_paths), before)

    def test_optional_catalog_absence_does_not_override_required_unknown(self):
        optional = "/synthetic-stage/bin/optional-root"
        roots = [{"id": "optional_root", "path": optional, "required": False},
                 {"id": "staged_launcher", "path": self.root_path, "required": True}]
        tags = CatalogPolicyBasicsTests.tags
        objects = {optional: tags(["libAbsent.so"]), self.root_path: tags(["libUnprovided.so"])}
        paths = {"/usr/lib64/libAbsent.so": {"state": "absent_in_catalog"}}
        result = self.resolve_unchanged(roots, objects, paths)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual([(item["id"], item["status"]) for item in result["roots"]],
                         [("optional_root", "absent_in_catalog"), ("staged_launcher", "unknown")])
        self.assertEqual([node["path"] for node in result["nodes"]], [self.root_path, optional])

    def test_public_call_performs_no_filesystem_or_process_access(self):
        # The module was imported above, before applying strict call-boundary guards.
        import builtins
        from contextlib import ExitStack
        import os
        import subprocess
        from unittest import mock
        roots, objects, paths = self.fixture()
        operations = [(builtins, "open"), (os, "open"), (os, "stat"), (os, "lstat"),
                      (os, "scandir"), (os, "listdir"), (os, "readlink"), (os, "read"),
                      (os, "system"), (subprocess, "Popen"), (subprocess, "run")]
        with ExitStack() as guards:
            for owner, name in operations:
                guards.enter_context(mock.patch.object(owner, name, side_effect=AssertionError("forbidden boundary access: " + name)))
            result = policy.resolve_catalog(roots, objects, paths)
        self.assertEqual(result["status"], "complete_for_supplied_catalog_policy")
        self.assertEqual(result["coverage"], {"actualHost": "UNRUN", "loader": "UNRUN", "abi": "UNRUN", "lifecycle": "UNRUN"})

    def test_result_mutation_does_not_change_inputs_or_later_results(self):
        roots, objects, paths = self.fixture()
        before = copy.deepcopy((roots, objects, paths))
        result = policy.resolve_catalog(roots, objects, paths)
        pristine = copy.deepcopy(result)
        result["roots"][0]["id"] = "mutated-output"
        result["nodes"][0]["path"] = "/mutated-output"
        result["edges"][0]["contexts"][0]["reasons"].append("mutated-output")
        result["incomplete"].append({"root": "mutated-output"})
        self.assertEqual((roots, objects, paths), before)
        self.assertEqual(policy.resolve_catalog(roots, objects, paths), pristine)


    def test_explicit_library_root_canonical_conflicts_are_unknown_without_following(self):
        path, other = "/usr/lib64/libRoot.so", "/usr/lib64/libOther.so"
        roots = [{"id": "library_root", "path": path, "required": True}]
        objects = {path: CatalogPolicyBasicsTests.tags(), other: CatalogPolicyBasicsTests.tags()}
        for conflict in ({"state": "absent_in_catalog"}, {"state": "unknown"},
                         {"state": "alias", "target": "libOther.so"},
                         {"state": "object", "canonical": other}):
            with self.subTest(conflict=conflict):
                result = self.resolve_unchanged(roots, objects, {path: conflict})
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(result["roots"][0]["status"], "unknown")
                self.assertEqual(result["nodes"], [])
                self.assertEqual(result["edges"], [])
                self.assertTrue(any(item["root"] == "library_root" and item["reason"] == "canonical_conflict"
                                    for item in result["incomplete"]))
        # Omission retains the explicit supplied-object root, including libraries.
        self.assertEqual(self.resolve_unchanged(roots, objects, {})["status"], "complete_for_supplied_catalog_policy")

    def test_root_diagnostics_explain_missing_data_and_leaf_own_blockers(self):
        roots, objects, paths = self.fixture()
        missing = copy.deepcopy(objects); del missing[self.root_path]
        result = self.resolve_unchanged(roots, missing, paths)
        self.assertEqual(result["rootDiagnostics"], [{"root": "staged_launcher", "reasons": ["root_unprovided"]}])
        for changes, reason in (({"rpath": ["$ORIGIN"]}, "own_rpath"),
                                ({"runpath": ["$ORIGIN"]}, "own_runpath"),
                                ({"flags": [{"tag": 30, "value": 1}]}, "nonzero_dynamic_flags"),
                                ({"unsupportedMechanisms": [{"tag": 0x7fffffff, "value": 1}]}, "unsupported_mechanism")):
            with self.subTest(reason=reason):
                roots, objects, _paths = self.fixture()
                objects[self.root_path] = CatalogPolicyBasicsTests.tags(**changes)
                result = self.resolve_unchanged(roots, objects, {})
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(result["rootDiagnostics"], [{"root": "staged_launcher", "reasons": [reason]}])
                self.assertEqual(result["edges"], [])


if __name__ == "__main__":
    unittest.main()
