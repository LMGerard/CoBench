# SPDX-License-Identifier: LGPL-2.1-or-later
"""Is everything connected as it should be before a part is edited?

The state of the connection is a list of checks, each green, orange or red:

* **CoBench version**: the version this FreeCAD runs against the minimum the
  project asks for (kept in the lock database), the version installed on disk
  (updated but FreeCAD not restarted) and the latest one published.
* **Lock database**: reachable, right key, tables present.
* **Sync, both ways**: a small program next to the reference copy of the files
  (``server/cobench_scanner.py``, e.g. on the Nextcloud server) writes the
  fingerprint of every part into the lock database.  Each FreeCAD compares it
  with its own copy: a part saved elsewhere that does not arrive, or a part
  saved here that does not leave, is a problem once it lasts longer than a
  normal sync (``SYNC_GRACE`` seconds).
* **Identity**: the name the others see.

A red check stops CoBench from locking parts, so nobody edits a part while
believing everything works.  This module does no GUI work and is tested
without FreeCAD.
"""

import os
import re
import threading
import time
import unicodedata
import urllib.request

from . import stamps
from ..i18n import tr

OFF, OK, WARNING, ERROR = "off", "ok", "warning", "error"
_RANK = {OFF: 0, OK: 1, WARNING: 2, ERROR: 3}

IN, OUT = "in", "out"            # server copy newer / this computer's copy newer

SYNC_GRACE = 180                 # seconds a normal sync may take before it is a problem
SCANNER_STALE = 90               # seconds without news from the server's scanner
SCANNER_STALE_CLOCK = 600        # same, judged on the clock (when CoBench just started)
UPDATE_EVERY = 6 * 3600          # seconds between two looks for a new version
UPDATE_URL = "https://raw.githubusercontent.com/LMGerard/CoBench/main/package.xml"
PROJECT_FILE = "cobench.json"
ADDON_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# -- versions ----------------------------------------------------------------
def parse_version(text):
    """'0.4.8' -> (0, 4, 8); unreadable parts count as 0."""
    numbers = []
    for piece in str(text or "").strip().lstrip("vV").split("."):
        match = re.match(r"\d+", piece)
        numbers.append(int(match.group()) if match else 0)
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    return tuple(numbers)


def older(version, other):
    """True when version is strictly older than other (empty other: False)."""
    if not other:
        return False
    return parse_version(version) < parse_version(other)


def version_in_package(text):
    match = re.search(r"<version>\s*([^<\s]+)\s*</version>", text or "")
    return match.group(1) if match else ""


def installed_version(root=ADDON_ROOT):
    """The version in package.xml on disk ('' when unreadable)."""
    try:
        with open(os.path.join(root, "package.xml"), encoding="utf-8") as stream:
            return version_in_package(stream.read())
    except OSError:
        return ""


def latest_version(url=UPDATE_URL, timeout=5):
    """The version published on the repository, or '' (offline...)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as answer:
            return version_in_package(answer.read(65536).decode("utf-8", "replace"))
    except Exception:
        return ""


# -- files -------------------------------------------------------------------
def part_key(rel):
    """Key of a file relative to the project root, the same on every system.

    macOS may give decomposed accents, Windows ignores case.
    """
    return os.path.normcase(unicodedata.normalize("NFC", str(rel).replace("\\", "/")))


class FingerprintCache:
    """sha1 of files, computed again only when their size or date changes."""

    def __init__(self):
        self._known = {}  # path -> ((size, mtime_ns), sha1)

    def read(self, paths):
        """{key: (sha1, size, mtime)} for {key: absolute path}; unreadable files are skipped."""
        found = {}
        for key, path in paths.items():
            try:
                info = os.stat(path)
                signature = (info.st_size, info.st_mtime_ns)
                cached = self._known.get(path)
                if cached and cached[0] == signature:
                    sha1 = cached[1]
                else:
                    sha1 = stamps.fingerprint(path)
                    self._known[path] = (signature, sha1)
                found[key] = (sha1, info.st_size, info.st_mtime_ns / 1e9)
            except OSError:
                continue
        for path in list(self._known):
            if path not in paths.values():
                del self._known[path]
        return found


class Collector:
    """Slow work done in a thread: fingerprints of the local files, latest version."""

    def __init__(self):
        self.cache = FingerprintCache()
        self.local = None          # {key: (sha1, size, mtime)}, None until the first pass
        self.latest = ""
        self._latest_at = None
        self._running = False

    def start(self, paths, check_updates=True):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._run, args=(dict(paths), check_updates), daemon=True).start()

    def _run(self, paths, check_updates):
        try:
            self.local = self.cache.read(paths)
            now = time.monotonic()
            if check_updates and (self._latest_at is None or now - self._latest_at > UPDATE_EVERY):
                self._latest_at = now
                self.latest = latest_version()
        except Exception:
            pass
        finally:
            self._running = False


# -- sync both ways ------------------------------------------------------------
class SyncItem:
    def __init__(self, key, direction, age, late):
        self.key, self.direction, self.age, self.late = key, direction, age, late

    def __repr__(self):
        return "SyncItem(%r, %r, %.0f, %r)" % (self.key, self.direction, self.age, self.late)


class SyncTracker:
    """Files that differ between this computer and the server, and for how long.

    A file being received is timed while the local copy does not change; a
    file being sent, while the server copy does not change.  So a part saved
    again and again here, whose copies never leave, still turns red.
    """

    def __init__(self, grace=SYNC_GRACE):
        self.grace = grace
        self._since = {}

    def compare(self, local, server, versions=None, now=None):
        """{key: SyncItem} for every file that differs.

        local: {key: (sha1, size, mtime)}; server: {key: {"sha1", "size", "mtime"}};
        versions: {key: sha1 of the last version recorded in the lock database}.
        """
        now = time.monotonic() if now is None else now
        versions = versions or {}
        items, seen = {}, set()
        for key in set(local) | set(server):
            mine, theirs = local.get(key), server.get(key)
            mine_sha = mine[0] if mine else None
            server_sha = str(theirs.get("sha1") or "") if theirs else None
            if mine_sha == server_sha:
                continue
            direction = self.direction(mine, theirs, versions.get(key))
            ident = (key, direction, mine_sha if direction == IN else server_sha)
            seen.add(ident)
            since = self._since.setdefault(ident, now)
            items[key] = SyncItem(key, direction, now - since, now - since >= self.grace)
        for ident in list(self._since):
            if ident not in seen:
                del self._since[ident]
        return items

    @staticmethod
    def direction(mine, theirs, version_sha):
        if mine is None:
            return IN
        if theirs is None:
            return OUT
        if version_sha:
            if theirs.get("sha1") == version_sha:
                return IN
            if mine[0] == version_sha:
                return OUT
        try:
            server_time = float(theirs.get("mtime") or 0)
        except (TypeError, ValueError):
            server_time = 0.0
        return IN if server_time > (mine[2] or 0) + 1 else OUT


# -- the report ------------------------------------------------------------------
class Check:
    def __init__(self, name, level, text, fix=""):
        self.name, self.level, self.text, self.fix = name, level, text, fix

    def __repr__(self):
        return "Check(%r, %r, %r)" % (self.name, self.level, self.text)


class Report:
    def __init__(self, checks, sync=None, server_ready=False):
        self.checks = checks
        self.sync = sync or {}          # key -> SyncItem
        self.server_ready = server_ready  # the server's copy is known and fresh
        self.level = max((c.level for c in checks), key=_RANK.get, default=OFF)

    @property
    def blocking(self):
        return self.level == ERROR

    def problems(self):
        return [c for c in self.checks if c.level == ERROR]

    def warnings(self):
        return [c for c in self.checks if c.level == WARNING]

    def summary(self):
        problems = self.problems()
        if problems:
            if len(problems) == 1:
                return tr("Problem: {problem}", problem=problems[0].text)
            return tr("{count} problems: {problem}", count=len(problems), problem=problems[0].text)
        warnings = self.warnings()
        if warnings:
            return warnings[0].text
        return tr("Connected and up to date")

    def sent(self, key):
        """True when the server holds this computer's copy of the file."""
        return self.server_ready and key not in self.sync


def _names(keys, display, limit=4):
    names = sorted(display.get(k, k) for k in keys)
    text = ", ".join(names[:limit])
    if len(names) > limit:
        text += tr(" and {count} more", count=len(names) - limit)
    return text


def evaluate(running, installed="", latest="", min_version="", store="files", store_error="",
             store_offline=False, store_loaded=True, server_state="none", server_age=None,
             server_clock_age=None, local=None, sync=None, display=None, user="", host="",
             user_named=True):
    """The report from what is known now (no I/O).

    server_state: 'missing' (the database has no table for it), 'none' (no
    scanner writes for this project), 'ok', or 'unknown' (not read yet).
    server_age: seconds since the scanner's heartbeat last changed;
    server_clock_age: age of that heartbeat on this computer's clock.
    local: fingerprints of the local files, None until computed;
    sync: {key: SyncItem}; display: {key: name shown to the user}.
    """
    checks = []
    display = display or {}
    sync = sync or {}

    # CoBench version
    name = tr("CoBench version")
    if older(running, min_version):
        fix = (tr("Restart FreeCAD.") if installed and not older(installed, min_version)
               else tr("Update CoBench (Add-on manager, or git pull in its folder), then restart FreeCAD."))
        checks.append(Check(name, ERROR, tr("CoBench {running} is too old: this project needs {minimum} or newer.",
                                            running=running, minimum=min_version), fix))
    elif installed and older(running, installed):
        checks.append(Check(name, WARNING, tr("CoBench {installed} is installed but FreeCAD still runs {running}.",
                                              installed=installed, running=running), tr("Restart FreeCAD.")))
    elif latest and older(running, latest):
        checks.append(Check(name, WARNING, tr("CoBench {latest} is available (you have {running}).",
                                              latest=latest, running=running),
                            tr("Update CoBench (Add-on manager, or git pull in its folder), then restart FreeCAD.")))
    else:
        checks.append(Check(name, OK, tr("CoBench {running}, up to date", running=running) if latest
                            else tr("CoBench {running}", running=running)))

    # Lock database
    name = tr("Lock database")
    if store != "supabase":
        checks.append(Check(name, OK, tr("Lock files next to the parts")))
    elif store_error and store_offline:
        checks.append(Check(name, ERROR, tr("Cannot reach the lock database: {error}", error=store_error),
                            tr("Check the internet connection of this computer.")))
    elif store_error:
        checks.append(Check(name, ERROR, store_error, tr("Check the project's lock settings (cobench.json).")))
    elif not store_loaded:
        checks.append(Check(name, WARNING, tr("Connecting to the lock database...")))
    else:
        checks.append(Check(name, OK, tr("Connected")))

    # Sync both ways
    receive, send = tr("Server → this computer"), tr("This computer → server")
    server_ready = False
    if store != "supabase" or server_state in ("missing", "none"):
        text = tr("Not checked: no copy of the files is watched on the server for this project.")
        checks.append(Check(receive, OFF, text))
        checks.append(Check(send, OFF, text))
    elif server_state != "ok" or local is None:
        checks.append(Check(receive, WARNING, tr("Checking...")))
        checks.append(Check(send, WARNING, tr("Checking...")))
    elif (server_age is not None and server_age > SCANNER_STALE) or (
            server_clock_age is not None and server_clock_age > SCANNER_STALE_CLOCK):
        minutes = max(1, int(max(server_age or 0, server_clock_age or 0) // 60))
        text = tr("The server stopped reporting its files {minutes} min ago: the sync cannot be checked.",
                  minutes=minutes)
        fix = tr("Tell whoever runs the server (cobench_scanner).")
        checks.append(Check(receive, WARNING, text, fix))
        checks.append(Check(send, WARNING, text, fix))
    else:
        server_ready = True
        minutes = max(1, SYNC_GRACE // 60)
        fix = tr("Check the sync client (Nextcloud...) of this computer: is it running, connected, "
                 "without errors? Restart it if needed.")
        for check_name, direction, late_text, busy_text, done_text in (
                (receive, IN,
                 "{count} files saved on the server have not arrived here for more than {minutes} min: {names}",
                 "Receiving {count} files: {names}", "Up to date"),
                (send, OUT,
                 "{count} files changed here have not reached the server for more than {minutes} min: {names}",
                 "Sending {count} files: {names}", "Everything sent")):
            items = [i for i in sync.values() if i.direction == direction]
            late = [i.key for i in items if i.late]
            if late:
                checks.append(Check(check_name, ERROR, tr(late_text, count=len(late), minutes=minutes,
                                                          names=_names(late, display)), fix))
            elif items:
                checks.append(Check(check_name, WARNING, tr(busy_text, count=len(items),
                                                            names=_names([i.key for i in items], display))))
            else:
                checks.append(Check(check_name, OK, tr(done_text)))

    # Identity
    name = tr("Identity")
    if not user_named:
        checks.append(Check(name, WARNING, tr("You appear as {user}: choose the name the others see.", user=user),
                            tr("CoBench > My name and options.")))
    else:
        checks.append(Check(name, OK, tr("{user} on {host}", user=user, host=host)))

    return Report(checks, sync, server_ready)
