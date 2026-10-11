"""Offline contract tests for the explicit AI provider helper."""

from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ai.py"


def elf64_header(*, elf_type: int, machine: int, entry: int, phnum: int) -> bytes:
    ident = b"\x7fELF\x02\x01\x01" + b"\x00" * 9
    return ident + struct.pack(
        "<HHIQQQIHHHHHH", elf_type, machine, 1, entry, 64, 0, 0,
        64, 56, phnum, 0, 0, 0,
    )


def elf64_program_header(kind: int, flags: int, file_offset: int, virtual: int,
                         file_size: int, memory_size: int | None = None,
                         alignment: int = 1) -> bytes:
    return struct.pack(
        "<IIQQQQQQ", kind, flags, file_offset, virtual, virtual,
        file_size, file_size if memory_size is None else memory_size, alignment,
    )


class AiHelperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.install_bwrap()
        self.runner = self.base / "helper-runner.py"
        self.runner.write_text(textwrap.dedent(f"""
            import importlib.util
            from pathlib import Path
            import sys
            spec = importlib.util.spec_from_file_location("orla_ai_fixture_target", {str(HELPER)!r})
            target = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = target
            spec.loader.exec_module(target)
            target._safe_system_bwrap = lambda path, home, codex_home: path
            raise SystemExit(target.main(sys.argv[1:]))
        """), encoding="utf-8")

    def install_bwrap(self):
        self.executable("bwrap", """
            import json
            import os
            from pathlib import Path
            import sys
            argv = sys.argv[1:]
            Path(__file__).with_name("bwrap-last.json").write_text(json.dumps(argv))
            bindings = {}
            index = 0
            while index < len(argv):
                if argv[index] in ("--ro-bind", "--bind"):
                    bindings[argv[index + 2]] = argv[index + 1]
                    index += 3
                elif argv[index] == "--":
                    command = argv[index + 1:]
                    command[0] = bindings.get(command[0], command[0])
                    os.execve(command[0], command, os.environ)
                elif argv[index] in ("--proc", "--dev", "--tmpfs", "--dir", "--chdir"):
                    index += 2
                else:
                    index += 1
            raise SystemExit(8)
        """)

    def executable(self, name: str, body: str) -> Path:
        path = self.bin / name
        path.write_text("#!/usr/bin/python3\n" + textwrap.dedent(body), encoding="utf-8")
        path.chmod(0o755)
        return path

    def elf_executable(self, path: Path, output: str = "codex-cli 0.162.1",
                       *, libraries: tuple[str, ...] = ()) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        base = 0x400000
        data = (output + "\n").encode("ascii")
        code = (b"\xb8\x01\x00\x00\x00\xbf\x01\x00\x00\x00"
                b"\x48\x8d\x35\x10\x00\x00\x00\xba" + struct.pack("<I", len(data))
                + b"\x0f\x05\xb8\x3c\x00\x00\x00\x31\xff\x0f\x05")
        program_headers = 2 if libraries else 1
        code_offset = 64 + 56 * program_headers
        body = bytearray(code + data)
        dynamic_offset = code_offset + len(body)
        dynamic = b""
        strings = b""
        if libraries:
            strings = b"\x00" + b"\x00".join(
                ("lib" + library + ".so.1").encode("ascii") for library in libraries) + b"\x00"
            string_offset = dynamic_offset + 16 * (len(libraries) + 3)
            entries = [(5, base + string_offset), (10, len(strings))]
            cursor = 1
            for library in libraries:
                entries.append((1, cursor))
                cursor += len(("lib" + library + ".so.1").encode("ascii")) + 1
            entries.append((0, 0))
            dynamic = b"".join(struct.pack("<qQ", tag, value) for tag, value in entries)
            body.extend(dynamic + strings)
        total = code_offset + len(body)
        ident = b"\x7fELF\x02\x01\x01" + b"\x00" * 9
        header = ident + struct.pack(
            "<HHIQQQIHHHHHH", 2, 62, 1, base + code_offset, 64, 0, 0,
            64, 56, program_headers, 0, 0, 0,
        )
        load = struct.pack("<IIQQQQQQ", 1, 5, 0, base, base, total, total, 0x1000)
        headers = bytearray(header + load)
        if libraries:
            headers.extend(struct.pack(
                "<IIQQQQQQ", 2, 4, dynamic_offset, base + dynamic_offset,
                base + dynamic_offset, len(dynamic), len(dynamic), 8,
            ))
        path.write_bytes(headers + body)
        path.chmod(0o755)
        return path

    def run_helper(self, operation: str, *, timeout: float = 5.0,
                   home: str | None = None, extra_env: dict[str, str] | None = None):
        environment = {
            "HOME": home or "/home/synthetic",
            "PATH": str(self.bin),
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        environment.update(extra_env or {})
        completed = subprocess.run(
            [sys.executable, str(self.runner), operation],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        self.assertEqual(completed.stderr, b"")
        return completed, json.loads(completed.stdout)

    def test_detect_reports_five_fixed_providers_without_running_until_requested(self):
        marker = self.base / "ran"
        self.executable("codex", f"""
            from pathlib import Path
            import sys
            Path({str(marker)!r}).write_text("ran")
            print("codex-cli 0.162.1")
        """)
        self.assertFalse(marker.exists())

        completed, result = self.run_helper("detect")

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(marker.exists())
        self.assertEqual(result["schemaVersion"], 1)
        self.assertNotIn("checkedAt", result)
        self.assertEqual([provider["id"] for provider in result["providers"]],
                         ["codex", "claude", "opencode", "ollama", "lmstudio"])
        codex = result["providers"][0]
        self.assertEqual(codex["clientVersion"], "0.162.1")
        self.assertEqual(codex["capabilities"]["installation"], "supported")
        self.assertEqual(codex["capabilities"]["anonymous_protocol"], "unknown")
        self.assertTrue(all(value != "auth_needed" for provider in result["providers"]
                            for value in provider["capabilities"].values()))

    def test_unknown_or_missing_operation_is_rejected_without_starting_a_client(self):
        marker = self.base / "ran"
        self.executable("codex", f"from pathlib import Path; Path({str(marker)!r}).touch()")
        environment = {"HOME": str(self.base), "PATH": str(self.bin), "LANG": "C.UTF-8"}
        for arguments in ([], ["future-operation"], ["detect", "extra"]):
            with self.subTest(arguments=arguments):
                completed = subprocess.run(
                    [sys.executable, str(HELPER), *arguments], env=environment,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stderr, b"")
                self.assertEqual(json.loads(completed.stdout)["error"]["code"],
                                 "invalid_operation")
                self.assertFalse(marker.exists())

    def test_detect_distinguishes_presence_from_recognized_version_and_redacts_output(self):
        self.executable("claude", """
            import sys
            sys.stdout.write("future private token=/home/person/.config\\n")
        """)
        self.executable("opencode", """
            import sys, time
            sys.stdout.write("x" * 9000)
            sys.stdout.flush()
            time.sleep(60)
        """)
        self.executable("lms", """
            import sys
            sys.stderr.write("secret" * 2000)
            sys.stderr.flush()
        """)

        completed, result = self.run_helper("detect", timeout=4.0)

        self.assertEqual(completed.returncode, 0)
        by_id = {item["id"]: item for item in result["providers"]}
        self.assertEqual(by_id["codex"]["capabilities"]["installation"], "absent")
        self.assertEqual(by_id["claude"]["capabilities"]["installation"], "unknown")
        self.assertEqual(by_id["claude"]["messageCode"], "version_unrecognized")
        self.assertEqual(by_id["opencode"]["messageCode"], "stdout_limit")
        self.assertEqual(by_id["lmstudio"]["messageCode"], "stderr_limit")
        serialized = json.dumps(result)
        for secret in ("private", "token", "/home/person", str(self.base)):
            self.assertNotIn(secret, serialized)

    def test_detect_uses_each_fixed_version_argv_and_parses_only_provider_formats(self):
        fixtures = {
            "codex": "codex-cli 0.162.1",
            "claude": "2.1.287 (Claude Code)",
            "opencode": "opencode v2.0.24",
            "ollama": "ollama version is 0.12.3",
            "lms": "LM Studio CLI 0.3.9",
        }
        for executable, output in fixtures.items():
            observed = self.base / f"{executable}.argv"
            self.executable(executable, f"""
                import json
                from pathlib import Path
                import sys
                Path({str(observed)!r}).write_text(json.dumps(sys.argv[1:]))
                print({output!r})
            """)

        _, result = self.run_helper("detect")

        self.assertTrue(all(item["capabilities"]["installation"] == "supported"
                            for item in result["providers"]))
        for executable in ("codex", "claude", "opencode", "lms"):
            self.assertEqual(json.loads((self.base / f"{executable}.argv").read_text()),
                             ["--version"])
        self.assertFalse((self.base / "ollama.argv").exists())
        ollama = next(item for item in result["providers"] if item["id"] == "ollama")
        self.assertEqual(ollama["clientVersion"], None)
        self.assertEqual(ollama["messageCode"], "cli_present_version_not_queried")

    def test_detect_never_invokes_present_ollama_client(self):
        marker = self.base / "ollama-ran"
        self.executable("ollama", f"""
            from pathlib import Path
            Path({str(marker)!r}).touch()
            print("ollama version is 0.12.3")
        """)
        _, result = self.run_helper("detect")
        ollama = next(item for item in result["providers"] if item["id"] == "ollama")
        self.assertFalse(marker.exists())
        self.assertEqual(ollama["capabilities"]["installation"], "supported")
        self.assertEqual(ollama["clientVersion"], None)
        self.assertEqual(ollama["capabilities"]["anonymous_protocol"], "unknown")

    def test_version_detection_requires_sandbox_and_preserves_presence_only(self):
        marker = self.base / "codex-ran"
        self.executable("codex", f"""
            from pathlib import Path
            Path({str(marker)!r}).touch()
            print("codex-cli 0.162.1")
        """)
        (self.bin / "bwrap").unlink()
        _, result = self.run_helper("detect")
        codex = result["providers"][0]
        self.assertFalse(marker.exists())
        self.assertEqual(codex["capabilities"]["installation"], "unknown")
        self.assertEqual(codex["clientVersion"], None)
        self.assertEqual(codex["messageCode"], "isolation_unavailable")

    def test_home_installed_standalone_elf_is_mounted_as_one_file(self):
        home = self.base / "home"
        client = self.elf_executable(
            home / ".codex" / "packages" / "standalone" / "releases"
            / "0.162.1-x86_64-unknown-linux-musl" / "bin" / "codex")
        launcher = home / ".local" / "bin" / "codex"
        launcher.parent.mkdir(parents=True)
        launcher.symlink_to(client)
        target = self.import_target()
        environment = {"HOME": str(home), "PATH": str(launcher.parent) + ":" + str(self.bin),
                       "LANG": "C.UTF-8"}
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(
                target, "_safe_system_bwrap", return_value=str(self.bin / "bwrap")):
            result = target.detect()
        codex = result["providers"][0]
        self.assertEqual(codex["clientVersion"], "0.162.1")
        self.assertEqual(codex["capabilities"]["installation"], "supported")
        sandbox = json.loads((self.bin / "bwrap-last.json").read_text())
        mounts = [(sandbox[index + 1], sandbox[index + 2])
                  for index, value in enumerate(sandbox) if value == "--ro-bind"]
        self.assertIn((str(client), "/run/orla/client"), mounts)
        self.assertNotIn(str(client.parent), [source for source, _destination in mounts])
        self.assertNotIn(str(home), [source for source, _destination in mounts])

    def test_home_config_nonexec_shebang_and_ambiguous_elf_are_refused(self):
        home = self.base / "home"
        target = self.import_target()
        safe = home / ".local" / "bin" / "codex"
        safe.parent.mkdir(parents=True)

        sensitive = self.elf_executable(home / ".codex" / "config" / "codex")
        nonexec = self.elf_executable(home / "bin" / "codex")
        nonexec.chmod(0o644)
        shebang = safe
        shebang.write_text("#!/usr/bin/python3\nprint('codex-cli 0.162.1')\n", encoding="utf-8")
        shebang.chmod(0o755)
        ambiguous = self.elf_executable(home / ".local" / "bin" / "claude",
                                        "2.1.287 (Claude Code)", libraries=("z",))

        for path, expected in ((sensitive, "codex"), (nonexec, "codex"),
                               (shebang, "codex")):
            with self.subTest(path=path):
                self.assertIsNone(target._safe_client_executable(
                    str(path), expected, str(home), str(home / ".codex")))
        self.assertEqual(target._safe_client_executable(
            str(ambiguous), "claude", str(home), str(home / ".codex")), str(ambiguous))
        self.assertIsNone(target._runtime_dependencies(str(ambiguous)))

    def test_elf_parser_bounds_interpreter_and_accepts_only_executable_images(self):
        target = self.import_target()
        base = 0x400000

        core = self.bin / "core-image"
        core.write_bytes(elf64_header(elf_type=4, machine=62, entry=0, phnum=0))
        core.chmod(0o755)
        self.assertIsNone(target._elf_requirements(str(core)))

        def interpreter_image(name: str, interpreter: bytes) -> Path:
            headers_size = 64 + 2 * 56
            total = headers_size + len(interpreter)
            path = self.bin / name
            path.write_bytes(
                elf64_header(elf_type=2, machine=62,
                             entry=base + headers_size, phnum=2)
                + elf64_program_header(1, 5, 0, base, total, alignment=0x1000)
                + elf64_program_header(3, 4, headers_size,
                                       base + headers_size, len(interpreter))
                + interpreter
            )
            path.chmod(0o755)
            return path

        oversized = interpreter_image(
            "oversized-interpreter", b"A" * target.ELF_INTERPRETER_LIMIT + b"\x00")
        self.assertIsNone(target._elf_requirements(str(oversized)))
        wrong_architecture = interpreter_image(
            "wrong-architecture-interpreter", b"/lib/ld-linux-aarch64.so.1\x00")
        self.assertIsNone(target._elf_requirements(str(wrong_architecture)))

    def test_elf_parser_rejects_duplicate_special_segments_and_bad_alignment(self):
        target = self.import_target()
        base = 0x400000

        first = b"/lib64/ld-linux-x86-64.so.2\x00"
        second = b"/lib64/ld-linux-x86-64.so.2\x00"
        headers_size = 64 + 3 * 56
        total = headers_size + len(first) + len(second)
        duplicate_interpreter = self.bin / "duplicate-interpreter"
        duplicate_interpreter.write_bytes(
            elf64_header(elf_type=2, machine=62, entry=base + headers_size, phnum=3)
            + elf64_program_header(1, 5, 0, base, total, alignment=0x1000)
            + elf64_program_header(3, 4, headers_size,
                                   base + headers_size, len(first))
            + elf64_program_header(3, 4, headers_size + len(first),
                                   base + headers_size + len(first), len(second))
            + first + second
        )
        duplicate_interpreter.chmod(0o755)

        dynamic = struct.pack("<qQ", 0, 0)
        headers_size = 64 + 3 * 56
        total = headers_size + len(dynamic)
        duplicate_dynamic = self.bin / "duplicate-dynamic"
        duplicate_dynamic.write_bytes(
            elf64_header(elf_type=2, machine=62, entry=base + headers_size, phnum=3)
            + elf64_program_header(1, 5, 0, base, total, alignment=0x1000)
            + elf64_program_header(2, 4, headers_size,
                                   base + headers_size, len(dynamic), alignment=8)
            + elf64_program_header(2, 4, headers_size,
                                   base + headers_size, len(dynamic), alignment=8)
            + dynamic
        )
        duplicate_dynamic.chmod(0o755)

        invalid_alignment = self.bin / "invalid-alignment"
        total = 64 + 56 + 1
        invalid_alignment.write_bytes(
            elf64_header(elf_type=2, machine=62, entry=base + 64 + 56, phnum=1)
            + elf64_program_header(1, 5, 0, base, total, alignment=3)
            + b"\xc3"
        )
        invalid_alignment.chmod(0o755)

        for path in (duplicate_interpreter, duplicate_dynamic, invalid_alignment):
            with self.subTest(path=path.name):
                self.assertIsNone(target._elf_requirements(str(path)))

    def test_elf_parser_requires_coherent_unambiguous_dynamic_mappings(self):
        target = self.import_target()
        base = 0x400000
        headers_size = 64 + 2 * 56
        dynamic_offset = headers_size
        displaced_virtual = base + headers_size + 256
        strings = b"\x00libc.so.6\x00"
        strings_offset = dynamic_offset + 4 * 16
        dynamic = b"".join(struct.pack("<qQ", tag, value) for tag, value in (
            (5, base + strings_offset), (10, len(strings)), (1, 1), (0, 0),
        ))
        total = (displaced_virtual - base) + len(dynamic)
        inconsistent = self.bin / "inconsistent-dynamic"
        inconsistent.write_bytes(
            elf64_header(elf_type=2, machine=62, entry=base + headers_size, phnum=2)
            + elf64_program_header(1, 5, 0, base, total, alignment=0x1000)
            + elf64_program_header(2, 4, dynamic_offset, displaced_virtual,
                                   len(dynamic), alignment=8)
            + dynamic + strings
            + b"\x00" * (total - strings_offset - len(strings))
        )
        inconsistent.chmod(0o755)
        self.assertIsNone(target._elf_requirements(str(inconsistent)))

        headers_size = 64 + 3 * 56
        dynamic_offset = headers_size
        strings_offset = dynamic_offset + len(dynamic)
        strings_address = base + strings_offset
        dynamic = b"".join(struct.pack("<qQ", tag, value) for tag, value in (
            (5, strings_address), (10, len(strings)), (1, 1), (0, 0),
        ))
        total = strings_offset + len(strings)
        ambiguous = self.bin / "ambiguous-string-map"
        ambiguous.write_bytes(
            elf64_header(elf_type=2, machine=62, entry=base + headers_size, phnum=3)
            + elf64_program_header(1, 5, 0, base, total, alignment=0x1000)
            + elf64_program_header(2, 4, dynamic_offset,
                                   base + dynamic_offset, len(dynamic), alignment=8)
            + elf64_program_header(1, 4, strings_offset, strings_address,
                                   len(strings), alignment=1)
            + dynamic + strings
        )
        ambiguous.chmod(0o755)
        self.assertIsNone(target._elf_requirements(str(ambiguous)))

    def test_bwrap_selected_from_home_is_never_trusted(self):
        home = self.base / "home"
        client = self.elf_executable(home / ".local" / "bin" / "codex")
        fake_bwrap = self.elf_executable(home / ".local" / "bin" / "bwrap", "unused")
        target = self.import_target()
        environment = {"HOME": str(home), "PATH": str(client.parent), "LANG": "C.UTF-8"}
        with mock.patch.dict(os.environ, environment, clear=True):
            result = target.detect()
        self.assertTrue(fake_bwrap.exists())
        self.assertEqual(result["providers"][0]["messageCode"], "isolation_unavailable")

    def test_version_command_uses_no_network_empty_home_namespace_and_preserved_strings(self):
        child_environment = self.base / "version-environment.json"
        self.executable("codex", f"""
            import json
            import os
            from pathlib import Path
            Path({str(child_environment)!r}).write_text(json.dumps(dict(os.environ)))
            print("codex-cli 0.162.1")
        """)
        _, result = self.run_helper(
            "detect", extra_env={"CODEX_HOME": "/home/synthetic/.codex",
                                 "OPENAI_API_KEY": "private",
                                 "DBUS_SESSION_BUS_ADDRESS": "unix:path=/private"})
        self.assertEqual(result["providers"][0]["clientVersion"], "0.162.1")
        environment = json.loads(child_environment.read_text())
        self.assertEqual(environment["HOME"], "/home/synthetic")
        self.assertEqual(environment["CODEX_HOME"], "/home/synthetic/.codex")
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("DBUS_SESSION_BUS_ADDRESS", environment)
        sandbox = json.loads((self.bin / "bwrap-last.json").read_text())
        self.assertIn("--unshare-all", sandbox)
        self.assertIn("--new-session", sandbox)
        self.assertNotIn("--share-net", sandbox)
        bind_index = sandbox.index("--bind")
        self.assertEqual(sandbox[bind_index + 2], "/home/synthetic")
        self.assertNotEqual(sandbox[bind_index + 1], "/home/synthetic")

    def import_target(self):
        name = "orla_ai_test_target"
        spec = importlib.util.spec_from_file_location(name, HELPER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        target = importlib.util.module_from_spec(spec)
        sys.modules[name] = target
        self.addCleanup(sys.modules.pop, name, None)
        spec.loader.exec_module(target)
        return target

    def test_preexisting_and_mid_first_cancellation_do_not_spawn_later_versions(self):
        self.executable("codex", "import time; time.sleep(60)")
        self.executable("claude", "print('2.1.287 (Claude Code)')")
        environment = {"HOME": "/home/synthetic", "PATH": str(self.bin), "LANG": "C.UTF-8"}

        target = self.import_target()
        target._cancelled = True
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(
                target, "_safe_system_bwrap", return_value=str(self.bin / "bwrap")), \
                mock.patch.object(target.subprocess, "Popen", wraps=subprocess.Popen) as popen:
            result = target.detect()
        self.assertEqual(popen.call_count, 0)
        self.assertTrue(all(item["messageCode"] == "cancelled" for item in result["providers"]))

        target._cancelled = False
        started = []
        original = subprocess.Popen

        def cancel_on_first(argv, *args, **kwargs):
            started.append(argv)
            process = original(argv, *args, **kwargs)
            target._cancelled = True
            return process

        with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(
                target, "_safe_system_bwrap", return_value=str(self.bin / "bwrap")), \
                mock.patch.object(target.subprocess, "Popen", side_effect=cancel_on_first):
            result = target.detect()
        self.assertEqual(len(started), 1)
        self.assertTrue(all(item["messageCode"] == "cancelled" for item in result["providers"]))

    def test_timeout_kills_term_ignoring_descendant_in_owned_group(self):
        child_pid = self.base / "version-child.pid"
        child_code = (
            "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
        )
        self.executable("codex", f"""
            import subprocess
            import time
            from pathlib import Path
            child = subprocess.Popen(["/usr/bin/python3", "-c", {child_code!r}])
            Path({str(child_pid)!r}).write_text(str(child.pid))
            time.sleep(60)
        """)
        _, result = self.run_helper("detect", timeout=8.0)
        self.assertTrue(child_pid.exists())
        self.assertEqual(result["providers"][0]["messageCode"], "timeout")
        pid = int(child_pid.read_text())
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        else:
            os.kill(pid, signal.SIGKILL)
            self.fail("TERM-ignoring descendant survived owned group cleanup")

    def install_probe_fixtures(self, server_body: str):
        codex = self.executable("codex", f"""
            import json
            import os
            import sys
            if sys.argv[1:] == ["--version"]:
                print("codex-cli 0.162.1")
                raise SystemExit(0)
            if sys.argv[1:4] != ["app-server", "--listen", "stdio://"]:
                raise SystemExit(9)
            {textwrap.indent(textwrap.dedent(server_body), '            ').lstrip()}
        """)
        self.executable("bwrap", """
            import json
            import os
            from pathlib import Path
            import sys
            argv = sys.argv[1:]
            Path(__file__).with_name("bwrap-observed.json").write_text(json.dumps(argv))
            bindings = {}
            index = 0
            while index < len(argv):
                if argv[index] in ("--ro-bind", "--bind"):
                    bindings[argv[index + 2]] = argv[index + 1]
                    index += 3
                elif argv[index] == "--":
                    command = argv[index + 1:]
                    command[0] = bindings.get(command[0], command[0])
                    os.execve(command[0], command, os.environ)
                elif argv[index] in ("--proc", "--dev", "--tmpfs", "--dir", "--chdir"):
                    index += 2
                else:
                    index += 1
            raise SystemExit(8)
        """)
        return codex

    def test_probe_uses_only_initialize_and_initialized_and_qualifies_capability(self):
        transcript = self.base / "transcript.json"
        child_environment = self.base / "environment.json"
        self.install_probe_fixtures(f"""
            first = json.loads(sys.stdin.readline())
            print(json.dumps({{
                "id": first["id"],
                "result": {{
                    "codexHome": "/home/synthetic/.codex",
                    "platformFamily": "unix",
                    "platformOs": "linux",
                    "userAgent": "codex-cli/0.162.1"
                }}
            }}), flush=True)
            second = json.loads(sys.stdin.readline())
            from pathlib import Path
            Path({str(transcript)!r}).write_text(json.dumps([first, second]))
            Path({str(child_environment)!r}).write_text(json.dumps(dict(os.environ)))
        """)

        completed, result = self.run_helper(
            "probe-codex-anonymous", home="/home/synthetic",
            extra_env={"CODEX_HOME": "/home/synthetic/.codex",
                       "OPENAI_API_KEY": "must-not-enter-child",
                       "DBUS_SESSION_BUS_ADDRESS": "unix:path=/private"},
        )

        self.assertEqual(completed.returncode, 0)
        provider = result["provider"]
        self.assertEqual(provider["clientVersion"], "0.162.1")
        self.assertEqual(provider["capabilities"]["installation"], "supported")
        self.assertEqual(provider["capabilities"]["anonymous_protocol"], "supported")
        self.assertEqual(provider["capabilities"]["authentication"], "unknown")
        self.assertEqual(provider["capabilities"]["cancellation"], "unknown")
        messages = json.loads(transcript.read_text())
        self.assertEqual([message["method"] for message in messages],
                         ["initialize", "initialized"])
        self.assertEqual(set(messages[0]), {"id", "method", "params"})
        self.assertEqual(set(messages[1]), {"method"})
        environment = json.loads(child_environment.read_text())
        self.assertEqual(environment["HOME"], "/home/synthetic")
        self.assertEqual(environment["CODEX_HOME"], "/home/synthetic/.codex")
        for name in ("OPENAI_API_KEY", "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR",
                     "WAYLAND_DISPLAY", "DISPLAY", "SSH_AUTH_SOCK"):
            self.assertNotIn(name, environment)
        runtime = ROOT / ".runtime" / "ai-provider-helper-impl"
        self.assertEqual(list(runtime.glob("home-*")), [])
        sandbox = json.loads((self.bin / "bwrap-observed.json").read_text())
        for required in ("--unshare-all", "--die-with-parent", "--new-session",
                         "--proc", "--dev", "--tmpfs", "--chdir"):
            self.assertIn(required, sandbox)
        self.assertNotIn("--share-net", sandbox)
        read_only_sources = [sandbox[index + 1] for index, value in enumerate(sandbox)
                             if value == "--ro-bind"]
        self.assertNotIn("/usr", read_only_sources)
        self.assertNotIn("/home", read_only_sources)
        self.assertNotIn(str(ROOT), read_only_sources)

    def test_probe_rejects_future_version_custom_home_and_missing_isolation(self):
        self.executable("codex", "print('codex-cli 0.999.0')")
        _, future = self.run_helper("probe-codex-anonymous", home="/home/synthetic")
        self.assertEqual(future["provider"]["capabilities"]["installation"], "supported")
        self.assertEqual(future["provider"]["capabilities"]["anonymous_protocol"], "unknown")
        self.assertEqual(future["provider"]["messageCode"], "protocol_version_unknown")

        self.bin.joinpath("codex").unlink()
        self.install_probe_fixtures("raise SystemExit(7)")
        _, custom = self.run_helper(
            "probe-codex-anonymous", home="/home/synthetic",
            extra_env={"CODEX_HOME": "/outside/codex"},
        )
        self.assertEqual(custom["provider"]["capabilities"]["installation"], "unknown")
        self.assertEqual(custom["provider"]["messageCode"], "isolation_unavailable")

        self.bin.joinpath("bwrap").unlink()
        _, missing = self.run_helper("probe-codex-anonymous", home="/home/synthetic")
        self.assertEqual(missing["provider"]["messageCode"], "isolation_unavailable")

    def test_probe_bounds_malformed_timeout_and_excessive_protocol_output(self):
        scenarios = [
            ("print('{bad json', flush=True)", "protocol_invalid"),
            ("import time; time.sleep(60)", "protocol_timeout"),
            ("sys.stdout.write('x' * 70000); sys.stdout.flush()", "protocol_output_limit"),
        ]
        for body, expected in scenarios:
            with self.subTest(expected=expected):
                for path in self.bin.iterdir():
                    path.unlink()
                self.install_probe_fixtures(body)
                started = time.monotonic()
                _, result = self.run_helper(
                    "probe-codex-anonymous", home="/home/synthetic", timeout=12.0)
                self.assertLess(time.monotonic() - started, 11.0)
                self.assertEqual(result["provider"]["messageCode"], expected)
                self.assertEqual(result["provider"]["capabilities"]["anonymous_protocol"],
                                 "unknown")

    def test_probe_cancellation_terminates_owned_group_and_returns_typed_result(self):
        child_pid = self.base / "child.pid"
        self.install_probe_fixtures(f"""
            from pathlib import Path
            import subprocess
            import time
            child = subprocess.Popen(["/usr/bin/sleep", "60"])
            Path({str(child_pid)!r}).write_text(str(child.pid))
            time.sleep(60)
        """)
        environment = {
            "HOME": "/home/synthetic", "PATH": str(self.bin), "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        process = subprocess.Popen(
            [sys.executable, str(self.runner), "probe-codex-anonymous"], env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
        )
        deadline = time.monotonic() + 3.0
        while not child_pid.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(child_pid.exists())
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=5.0)
        self.assertEqual(stderr, b"")
        result = json.loads(stdout)
        self.assertEqual(result["provider"]["messageCode"], "cancelled")
        pid = int(child_pid.read_text())
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        else:
            self.fail("fixture descendant survived cancellation")


if __name__ == "__main__":
    unittest.main()
