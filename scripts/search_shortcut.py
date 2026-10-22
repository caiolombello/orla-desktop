"""Explicit, reversible Meta assignment through Plasma 6.7.5 KGlobalAccel."""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

META = [16777250, 0, 0, 0]
FALLBACK = [469762127, 0, 0, 0]  # Qt 6.11.2: Ctrl+Alt+Meta+O.
ORLA = ["org.orla.Launcher", "orla-search-open", "Orla Launcher", "Abrir Orla Search"]
PHASES = {"prepared", "enabled", "restoring", "disabled"}


class ShortcutError(Exception):
    pass


def valid_keys(keys):
    if not isinstance(keys, list) or len(keys) > 64:
        raise ShortcutError("Lista de atalhos inválida.")
    if any(not isinstance(key, list) or len(key) != 4 or
           any(type(value) is not int or not 0 <= value <= 2147483647 for value in key) for key in keys):
        raise ShortcutError("Sequência de atalho inválida.")
    return keys


def valid_action(action):
    if not isinstance(action, list) or len(action) != 4 or any(
            not isinstance(value, str) or not value or len(value) > 512 or "\x00" in value for value in action):
        raise ShortcutError("Identidade de ação inválida.")
    return action


def key_set(keys):
    # KGlobalAccel's QSet-backed transport does not preserve sequence order.
    return {tuple(key) for key in valid_keys(keys)}


class NativeBackend:
    def __init__(self):
        self.tool = shutil.which("busctl")
        if not self.tool:
            raise ShortcutError("busctl não está disponível.")
        self.owner = None
        self.running = False

    def call(self, method, signature="", values=(), *, service="org.kde.kglobalaccel",
             path="/kglobalaccel", interface="org.kde.KGlobalAccel", expected=None):
        command = [self.tool, "--user", "--auto-start=no", "--timeout=3s", "--json=short", "call",
                   service, path, interface, method]
        if signature:
            command += [signature, *map(str, values)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ShortcutError("A sessão D-Bus não respondeu.") from exc
        if result.returncode or len(result.stdout) > 262144:
            raise ShortcutError("KGlobalAccel indisponível ou resposta recusada.")
        if expected is None:
            return None
        try:
            reply = json.loads(result.stdout)
            if reply["type"] != expected or not isinstance(reply["data"], list) or len(reply["data"]) != 1:
                raise ValueError()
            return reply["data"][0]
        except (ValueError, KeyError, TypeError) as exc:
            raise ShortcutError("Resposta D-Bus inválida.") from exc

    def bus_owner(self, name):
        return self.call("GetNameOwner", "s", [name], service="org.freedesktop.DBus",
                         path="/org/freedesktop/DBus", interface="org.freedesktop.DBus", expected="s")

    def preflight(self, *, require_running=False):
        owner = self.bus_owner("org.kde.kglobalaccel")
        if self.owner is not None and owner != self.owner:
            raise ShortcutError("KGlobalAccel reiniciou; consulte o estado e tente novamente.")
        self.owner = owner
        present = self.call("NameHasOwner", "s", ["org.orla.Launcher"], service="org.freedesktop.DBus",
                            path="/org/freedesktop/DBus", interface="org.freedesktop.DBus", expected="b")
        self.running = present is True
        if require_running:
            if not self.running:
                raise ShortcutError("Inicie Orla Launcher com --managed-shortcuts antes de ativar Meta.")
            path = self.call("getComponent", "s", [ORLA[0]], expected="o")
            active = self.call("isActive", service="org.kde.kglobalaccel", path=path,
                               interface="org.kde.kglobalaccel.Component", expected="b")
            if active is not True:
                raise ShortcutError("O atalho está salvo, mas o launcher não está ativo.")

    def action(self, identity):
        path = self.call("getComponent", "s", [identity[0]], expected="o")
        contexts = self.call("getShortcutContexts", service="org.kde.kglobalaccel", path=path,
                             interface="org.kde.kglobalaccel.Component", expected="as")
        if not isinstance(contexts, list) or contexts != ["default"]:
            raise ShortcutError("Contextos personalizados de atalhos não são suportados nesta versão.")
        actions = self.call("allActionsForComponent", "as", [1, identity[0]], expected="aas")
        if not isinstance(actions, list) or len(actions) > 256:
            raise ShortcutError("Inventário de ações inválido.")
        matches = [action for action in map(valid_action, actions) if action[:2] == list(identity[:2])]
        if len(matches) != 1:
            raise ShortcutError("A ação não está registrada. Inicie o launcher gerenciado.")
        return matches[0]

    def keys(self, action):
        keys = self.call("shortcutKeys", "as", [4, *valid_action(action)], expected="a(ai)")
        if not isinstance(keys, list) or any(not isinstance(item, list) or len(item) != 1 for item in keys):
            raise ShortcutError("Resposta de atalhos inválida.")
        return valid_keys([item[0] for item in keys])

    def owners(self):
        rows = self.call("getGlobalShortcutsByKey", "i", [META[0]], expected="a(ssssssaiai)")
        if not isinstance(rows, list) or len(rows) > 16:
            raise ShortcutError("Inventário de Meta inválido.")
        owners = []
        for row in rows:
            if not isinstance(row, list) or len(row) != 8 or row[4] != "default":
                raise ShortcutError("Meta em contexto personalizado não é suportado nesta versão.")
            action = valid_action([row[2], row[0], row[3], row[1]])
            if action[:2] not in [item[:2] for item in owners]:
                owners.append(action)
        return owners

    def set_keys(self, action, keys):
        self.preflight()
        action = self.action(action)
        values = [4, *valid_action(action), len(valid_keys(keys))]
        for key in keys:
            values += [4, *key]
        self.call("setForeignShortcutKeys", "asa(ai)", values)
        if key_set(self.keys(action)) != key_set(keys):
            raise ShortcutError("A alteração do atalho não foi confirmada.")


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / "current.json"

    @staticmethod
    def check_file(path):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or \
                stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 65536:
            raise ShortcutError("Registro de recuperação inesperado.")

    @contextlib.contextmanager
    def locked(self):
        # The application-owned leaf must be private; never follow a symlink.
        if any(parent.is_symlink() for parent in [self.directory, *self.directory.parents]):
            raise ShortcutError("O diretório de recuperação não pode passar por links simbólicos.")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ShortcutError("Diretório de recuperação inesperado.")
        lock = self.directory / "lock"
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            self.check_file(lock)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        except BlockingIOError as exc:
            raise ShortcutError("Outra alteração de atalho está em andamento.") from exc
        finally:
            os.close(fd)

    def load(self):
        if any(parent.is_symlink() for parent in [self.directory, *self.directory.parents]):
            raise ShortcutError("O diretório de recuperação não pode passar por links simbólicos.")
        if not self.path.exists() and not self.path.is_symlink():
            return None
        self.check_file(self.path)
        try:
            journal = json.loads(self.path.read_text())
            if journal["schemaVersion"] != 1 or journal["phase"] not in PHASES or \
                    valid_action(journal["orla"]["action"])[:2] != ORLA[:2] or \
                    not isinstance(journal["foreign"], list) or len(journal["foreign"]) > 16:
                raise ValueError()
            valid_keys(journal["orla"]["before"])
            if type(journal["orla"]["attempted"]) is not bool:
                raise ValueError()
            if META in journal["orla"]["before"]:
                raise ValueError()
            seen = {tuple(ORLA[:2])}
            for item in journal["foreign"]:
                action = valid_action(item["action"])
                if tuple(action[:2]) in seen or META not in valid_keys(item["before"]) or type(item["attempted"]) is not bool:
                    raise ValueError()
                seen.add(tuple(action[:2]))
            return journal
        except (ValueError, KeyError, TypeError) as exc:
            raise ShortcutError("Registro de recuperação inválido; nenhuma alteração foi feita.") from exc

    def save(self, journal):
        if self.path.exists() or self.path.is_symlink():
            self.check_file(self.path)
        handle, pending = tempfile.mkstemp(prefix=".shortcut-", dir=self.directory)
        try:
            with os.fdopen(handle, "w") as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(journal, stream, ensure_ascii=False, indent=2)
                stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
            os.replace(pending, self.path)
            directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(pending):
                os.unlink(pending)


def identities(actions):
    return {tuple(valid_action(action)[:2]) for action in actions}


def restore(backend, store, journal):
    allowed = identities([ORLA, *[item["action"] for item in journal["foreign"]]])
    if identities(backend.owners()) - allowed:
        raise ShortcutError("Meta recebeu outra atribuição. Recuperação preservada; resolva o conflito antes de tentar novamente.")
    # Resolve every action before removing the current route to the launcher.
    actions = [backend.action(item["action"]) for item in [journal["orla"], *journal["foreign"]]]
    journal["phase"] = "restoring"; store.save(journal)
    keys = backend.keys(actions[0])
    if journal["orla"]["attempted"] and META in keys:
        backend.set_keys(actions[0], [key for key in keys if key != META])
    for action, item in zip(actions[1:], journal["foreign"]):
        current = backend.keys(action)
        if item["attempted"] and META not in current:
            index = item["before"].index(META)
            current.insert(min(index, len(current)), META.copy())
            backend.set_keys(action, current)
    if identities(backend.owners()) != identities(actions[1:]):
        raise ShortcutError("Recuperação ainda não confirmada; execute recover novamente.")
    journal["phase"] = "disabled"; store.save(journal)


def manage(operation, backend, directory):
    if operation not in {"status", "enable", "disable", "recover"}:
        raise ShortcutError("Operação desconhecida.")
    store = Store(directory)
    if operation == "status":
        backend.preflight()
        journal = store.load()
        return {"phase": journal["phase"] if journal else "unmanaged", "owners": backend.owners(),
                "launcherRunning": getattr(backend, "running", False)}
    with store.locked():
        backend.preflight(require_running=operation == "enable")
        journal = store.load()
        if operation in {"disable", "recover"}:
            if journal and journal["phase"] != "disabled":
                restore(backend, store, journal)
            return {"phase": "disabled"}
        if journal and journal["phase"] != "disabled":
            if journal["phase"] == "enabled" and identities(backend.owners()) == {tuple(ORLA[:2])} \
                    and FALLBACK in backend.keys(backend.action(ORLA)):
                backend.preflight(require_running=True)
                return {"phase": "enabled"}
            raise ShortcutError("Há uma alteração pendente ou divergente. Execute recover antes de ativar novamente.")
        action = backend.action(ORLA)
        before = backend.keys(action)
        if FALLBACK not in before:
            raise ShortcutError("Ctrl+Alt+Meta+O precisa estar disponível no Orla antes de ativar Meta.")
        owners = backend.owners()
        if len(owners) > 1:
            raise ShortcutError("Meta possui múltiplos proprietários. Resolva o conflito antes de ativar Orla.")
        if META in before or tuple(ORLA[:2]) in identities(owners):
            raise ShortcutError("Meta já pertence ao Orla fora deste registro; preserve essa configuração.")
        foreign = [{"action": backend.action(owner), "before": backend.keys(owner), "attempted": False} for owner in owners]
        if any(META not in item["before"] for item in foreign):
            raise ShortcutError("Meta mudou durante a consulta; nenhuma alteração foi feita.")
        journal = {"schemaVersion": 1, "phase": "prepared", "orla": {"action": action, "before": before, "attempted": False},
                   "foreign": foreign}
        store.save(journal)
        try:
            for item in foreign:
                backend.preflight(require_running=True)
                if key_set(backend.keys(item["action"])) != key_set(item["before"]):
                    raise ShortcutError("Atalho alterado por outro processo durante a configuração.")
                item["attempted"] = True; store.save(journal)
                backend.set_keys(item["action"], [key for key in item["before"] if key != META])
            if backend.owners() or key_set(backend.keys(action)) != key_set(before):
                raise ShortcutError("Meta ou Orla mudou durante a configuração.")
            backend.preflight(require_running=True)
            journal["orla"]["attempted"] = True; store.save(journal)
            backend.set_keys(action, [*before, META.copy()])
            if identities(backend.owners()) != {tuple(ORLA[:2])}:
                raise ShortcutError("Meta possui outro proprietário; a configuração não foi aceita.")
            backend.preflight(require_running=True)
            if FALLBACK not in backend.keys(action):
                raise ShortcutError("O atalho alternativo mudou durante a configuração.")
            journal["phase"] = "enabled"; store.save(journal)
        except (ShortcutError, OSError):
            # The durable intent precedes every bus write, including an unknown timeout result.
            # Recovery refuses unexpected Meta owners and never replays an entire config file.
            try:
                restore(backend, store, journal)
            except (ShortcutError, OSError):
                pass
            raise
        return {"phase": "enabled"}


def add_parser(subparsers):
    parser = subparsers.add_parser("search-shortcut", help="consultar, ativar ou restaurar Windows/Meta para Orla Search")
    parser.add_argument("action", choices=("status", "enable", "disable", "recover"))


def cli(args):
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    result = manage(args.action, NativeBackend(), state_home / "orla/search-shortcut")
    print(json.dumps(result, ensure_ascii=False))
    return 0
