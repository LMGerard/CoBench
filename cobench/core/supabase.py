# SPDX-License-Identifier: LGPL-2.1-or-later
"""Locks kept in a Supabase (PostgreSQL) database instead of lock files.

The part files stay in the shared folder; only who holds which part, and the
fingerprint of the last saved version of each part, go to the database:

* ``cobench_locks``: one row per locked part.  Its primary key (project, part)
  makes the database refuse a second lock on the same part, so taking a part
  is instant and only one person can win.
* ``cobench_versions``: the fingerprint of each part as last saved, so a
  copy that has not arrived through the sync yet is never edited by mistake.

Only the standard library is used (``urllib``), through Supabase's REST API.
"""

import json
import os
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request

from . import locks
from ..i18n import tr
from .locks import LockInfo, LockManager, LockState

TIMEOUT = 6
SQL_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "Resources", "supabase.sql")


class StoreError(Exception):
    """The database answered with an error (wrong key, tables missing...)."""


def _quote(value):
    return urllib.parse.quote(str(value), safe="")


class Client:
    """Minimal client of Supabase's REST API (PostgREST)."""

    def __init__(self, url, key):
        self.url = (url or "").strip().rstrip("/")
        self.key = (key or "").strip()
        self.context = ssl.create_default_context()

    def request(self, method, table, query="", body=None, prefer=""):
        """(status, decoded json or None).  Raises locks.Offline or StoreError."""
        address = "%s/rest/v1/%s%s" % (self.url, table, ("?" + query) if query else "")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"apikey": self.key, "Accept": "application/json"}
        if not self.key.startswith("sb_"):  # legacy anon key is a JWT, sent as bearer too
            headers["Authorization"] = "Bearer " + self.key
        if data is not None:
            headers["Content-Type"] = "application/json"
        if prefer:
            headers["Prefer"] = prefer
        request = urllib.request.Request(address, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT, context=self.context) as answer:
                raw = answer.read()
                return answer.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read() or b"{}")
            except ValueError:
                detail = {}
            return error.code, detail
        except (urllib.error.URLError, OSError) as error:
            raise locks.Offline(str(getattr(error, "reason", error)))

    def check(self, status, detail, what):
        if status >= 400:
            message = ""
            if isinstance(detail, dict):
                message = detail.get("message") or detail.get("hint") or ""
            if status in (401, 403):
                raise StoreError(tr("Supabase refused the key ({status}). Use the anon / publishable key.",
                                    status=status))
            if status == 404 or (isinstance(detail, dict) and detail.get("code") in ("42P01", "PGRST205")):
                raise StoreError(tr("The CoBench tables are missing: run the SQL script in Supabase."))
            raise StoreError(tr("{what}: Supabase error {status} {message}", what=what, status=status,
                                message=message))


def test_connection(url, key):
    """None when the database is reachable and ready, else a message."""
    if not url or not key:
        return tr("Enter the project URL and the anon / publishable key.")
    client = Client(url, key)
    try:
        for table in ("cobench_locks", "cobench_versions"):
            status, detail = client.request("GET", table, "select=part&limit=1")
            client.check(status, detail, table)
    except locks.Offline as exc:
        return tr("Cannot reach {url} ({error}).", url=url, error=exc)
    except StoreError as exc:
        return str(exc)
    return None


def _info_from_row(row):
    pid = row.get("pid") or 0
    info = LockInfo(user=str(row.get("user_name", "?")), host=str(row.get("host", "?")),
                    pid=pid if isinstance(pid, int) else 0, since=str(row.get("since") or ""),
                    session=str(row.get("session", "")), app=str(row.get("app", "")),
                    path="supabase:" + str(row.get("part", "")))
    info.part = str(row.get("part", ""))
    return info


class SupabaseLockManager(LockManager):
    """Same interface as LockManager; the truth is in the database.

    ``state`` answers from a cache refreshed by ``refresh`` (every tick, in a
    thread), so FreeCAD never waits for the network to draw the panel.
    Taking, forcing and releasing go to the database right away.
    """

    store = "supabase"

    def __init__(self, identity, session, app, url, key, project_id, rel):
        super().__init__(identity, session, app)
        self.client = Client(url, key)
        self.project_id = project_id
        self.rel = rel              # part path -> key relative to the project root
        # Keys are os.path.normcase(relative path): FreeCAD and Windows do not agree on case.
        self.rows = {}              # key -> LockInfo (info.part = the exact name in the database)
        self.versions = {}          # key -> {"part", "sha1", "size", "saved_by", "saved_at"}
        self.loaded = False
        self.error = ""             # last problem, shown in the panel
        self.offline = False
        self._pending_release = set()   # rel keys to delete once back online
        self._pending_versions = {}     # rel -> row to send once back online
        self._lock = threading.Lock()
        self._refreshing = False

    # -- reading -----------------------------------------------------------
    def refresh(self):
        """Read every lock and version of the project (blocking)."""
        query = "project=eq.%s&select=*" % _quote(self.project_id)
        try:
            self._flush()
            status, rows = self.client.request("GET", "cobench_locks", query)
            self.client.check(status, rows, "cobench_locks")
            status, versions = self.client.request("GET", "cobench_versions", query)
            self.client.check(status, versions, "cobench_versions")
        except locks.Offline as exc:
            self.offline, self.error = True, str(exc)
            return False
        except StoreError as exc:
            self.offline, self.error = False, str(exc)
            return False
        with self._lock:
            self.rows = {os.path.normcase(str(r.get("part"))): _info_from_row(r) for r in rows or []}
            self.versions = {os.path.normcase(str(v.get("part"))): v for v in versions or []}
            self.loaded, self.offline, self.error = True, False, ""
        return True

    def refresh_async(self):
        if self._refreshing:
            return
        self._refreshing = True

        def run():
            try:
                self.refresh()
            finally:
                self._refreshing = False
        threading.Thread(target=run, daemon=True).start()

    def _flush(self):
        """Send what could not be sent while offline."""
        for rel in list(self._pending_release):
            self._delete(rel)
            self._pending_release.discard(rel)
        for rel, row in list(self._pending_versions.items()):
            status, detail = self.client.request("POST", "cobench_versions", "on_conflict=project,part", row,
                                                 "resolution=merge-duplicates,return=minimal")
            self.client.check(status, detail, "cobench_versions")
            self._pending_versions.pop(rel, None)

    def _key(self, part_path):
        return os.path.normcase(self.rel(part_path))

    def _part(self, part_path):
        """The exact name of the part in the database (case as first written)."""
        with self._lock:
            info = self.rows.get(self._key(part_path))
        return info.part if info is not None else self.rel(part_path)

    def state(self, part_path):
        with self._lock:
            info = self.rows.get(self._key(part_path))
        if info is None:
            return LockState(locks.FREE)
        return LockState(self._classify(info), info)

    def version(self, part_path):
        with self._lock:
            return self.versions.get(self._key(part_path))

    # -- changes -----------------------------------------------------------
    def _row(self, rel, info):
        return {"project": self.project_id, "part": rel, "user_name": info.user, "host": info.host,
                "pid": info.pid, "session": info.session, "app": info.app}

    def acquire(self, part_path):
        rel = self._part(part_path)
        info = self._new_info()
        status, detail = self.client.request("POST", "cobench_locks", "", self._row(rel, info),
                                             "return=representation")
        if status == 409:  # somebody has it: read who
            current = self._read_one(rel, part_path)
            if current is None:
                return self.acquire(part_path)  # released meanwhile
            state = LockState(self._classify(current), current)
            if state.status == locks.MINE:
                self.held.add(locks._norm(part_path))
            elif state.status == locks.ORPHAN:
                return self.force(part_path)
            return state
        self.client.check(status, detail, "cobench_locks")
        row = detail[0] if isinstance(detail, list) and detail else self._row(rel, info)
        info = _info_from_row(row)
        with self._lock:
            self.rows[self._key(part_path)] = info
        self._pending_release.discard(rel)
        self.held.add(locks._norm(part_path))
        return LockState(locks.MINE, info)

    def _read_one(self, rel, part_path):
        query = "project=eq.%s&part=eq.%s&select=*" % (_quote(self.project_id), _quote(rel))
        status, rows = self.client.request("GET", "cobench_locks", query)
        self.client.check(status, rows, "cobench_locks")
        info = _info_from_row(rows[0]) if rows else None
        with self._lock:
            if info is None:
                self.rows.pop(self._key(part_path), None)
            else:
                self.rows[self._key(part_path)] = info
        return info

    def force(self, part_path):
        rel = self._part(part_path)
        info = self._new_info()
        status, detail = self.client.request("POST", "cobench_locks", "on_conflict=project,part",
                                             self._row(rel, info),
                                             "resolution=merge-duplicates,return=representation")
        self.client.check(status, detail, "cobench_locks")
        row = detail[0] if isinstance(detail, list) and detail else self._row(rel, info)
        info = _info_from_row(row)
        with self._lock:
            self.rows[self._key(part_path)] = info
        self.held.add(locks._norm(part_path))
        return LockState(locks.MINE, info)

    def _delete(self, rel):
        """Delete my row (same user and computer) for this part."""
        query = "project=eq.%s&part=eq.%s&user_name=eq.%s&host=eq.%s" % (
            _quote(self.project_id), _quote(rel), _quote(self.identity.user), _quote(self.identity.host))
        status, detail = self.client.request("DELETE", "cobench_locks", query, prefer="return=minimal")
        self.client.check(status, detail, "cobench_locks")

    def release(self, part_path):
        rel = self._part(part_path)
        self.held.discard(locks._norm(part_path))
        current = self.state(part_path)
        if current.status not in (locks.MINE, locks.ORPHAN):
            return False
        with self._lock:
            self.rows.pop(self._key(part_path), None)
        try:
            self._delete(rel)
        except locks.Offline:
            self._pending_release.add(rel)  # sent when back online
        return True

    def set_version(self, part_path, sha1, size):
        rel = self._part(part_path)
        row = {"project": self.project_id, "part": rel, "sha1": sha1, "size": size,
               "saved_by": self.identity.user}
        with self._lock:
            self.versions[self._key(part_path)] = dict(row)
        try:
            status, detail = self.client.request("POST", "cobench_versions", "on_conflict=project,part", row,
                                                 "resolution=merge-duplicates,return=minimal")
            self.client.check(status, detail, "cobench_versions")
        except locks.Offline:
            self._pending_versions[rel] = row

    def forget_version(self, part_path):
        rel = self._part(part_path)
        with self._lock:
            self.versions.pop(self._key(part_path), None)
        query = "project=eq.%s&part=eq.%s" % (_quote(self.project_id), _quote(rel))
        try:
            self.client.request("DELETE", "cobench_versions", query, prefer="return=minimal")
        except locks.Offline:
            pass
