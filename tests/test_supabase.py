# SPDX-License-Identifier: LGPL-2.1-or-later
"""Supabase lock store, against an in-memory imitation of its REST API."""

import os
import sys
import urllib.parse

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cobench.core import locks, supabase  # noqa: E402
from cobench.core.identity import Identity  # noqa: E402

KEYS = {"cobench_locks": ("project", "part"), "cobench_versions": ("project", "part")}


class FakeRest:
    """Enough of PostgREST: eq filters, insert (409 on duplicate), upsert, delete."""

    def __init__(self):
        self.tables = {"cobench_locks": [], "cobench_versions": []}
        self.online = True
        self.calls = 0

    def _filters(self, query):
        out = {}
        for name, value in urllib.parse.parse_qsl(query, keep_blank_values=True):
            if value.startswith("eq."):
                out[name] = value[3:]
        return out

    def request(self, method, table, query="", body=None, prefer=""):
        self.calls += 1
        if not self.online:
            raise locks.Offline("no network")
        rows = self.tables[table]
        where = self._filters(query)

        def match(row):
            return all(str(row.get(k)) == v for k, v in where.items())
        if method == "GET":
            return 200, [dict(r) for r in rows if match(r)]
        if method == "DELETE":
            self.tables[table] = [r for r in rows if not match(r)]
            return 204, None
        if method == "POST":
            key = tuple(body[k] for k in KEYS[table])
            existing = [r for r in rows if tuple(r[k] for k in KEYS[table]) == key]
            row = dict(body)
            row.setdefault("since", "2026-11-02T10:00:00+00:00")
            if existing:
                if "merge-duplicates" not in prefer:
                    return 409, {"code": "23505", "message": "duplicate key"}
                existing[0].update(row)
                return 201, [dict(existing[0])]
            rows.append(row)
            return 201, [dict(row)]
        raise AssertionError(method)


@pytest.fixture
def rest(monkeypatch):
    fake = FakeRest()
    monkeypatch.setattr(supabase.Client, "request", lambda self, *a, **k: fake.request(*a, **k))
    return fake


def manager(tmp_path, user="alice", host="pc1", session="s1"):
    root = str(tmp_path)

    def rel(path):
        return os.path.relpath(os.path.abspath(path), root).replace("\\", "/")
    return supabase.SupabaseLockManager(Identity(user, host), session, "FreeCAD", "https://x.supabase.co",
                                        "sb_publishable_test", "proj1", rel)


def test_only_one_can_take_a_part(tmp_path, rest):
    part = str(tmp_path / "Plate.FCStd")
    alice, bob = manager(tmp_path), manager(tmp_path, "bob", "pc2", "s2")
    assert alice.acquire(part).status == locks.MINE
    taken = bob.acquire(part)  # bob's cache was empty: the database decides
    assert taken.status == locks.OTHER and taken.info.user == "alice"
    assert bob.refresh() and bob.state(part).status == locks.OTHER
    assert alice.release(part)
    bob.refresh()
    assert bob.state(part).status == locks.FREE
    assert bob.acquire(part).status == locks.MINE


def test_release_never_removes_someone_elses_lock(tmp_path, rest):
    part = str(tmp_path / "Plate.FCStd")
    alice, bob = manager(tmp_path), manager(tmp_path, "bob", "pc2", "s2")
    alice.acquire(part)
    bob.refresh()
    assert bob.release(part) is False
    alice.refresh()
    assert alice.state(part).status == locks.MINE


def test_force_takes_over(tmp_path, rest):
    part = str(tmp_path / "Plate.FCStd")
    alice, bob = manager(tmp_path), manager(tmp_path, "bob", "pc2", "s2")
    alice.acquire(part)
    assert bob.force(part).status == locks.MINE
    alice.refresh()
    assert alice.state(part).status == locks.OTHER


def test_orphan_of_crashed_freecad_is_taken_back(tmp_path, rest):
    part = str(tmp_path / "Plate.FCStd")
    old = manager(tmp_path, session="dead")
    old.pid_override = True
    rest.request("POST", "cobench_locks", "", {"project": "proj1", "part": "Plate.FCStd", "user_name": "alice",
                                               "host": "pc1", "pid": 999999, "session": "dead", "app": ""})
    new = manager(tmp_path, session="s9")
    assert new.acquire(part).status == locks.MINE


def test_offline_take_fails_and_release_is_queued(tmp_path, rest):
    part = str(tmp_path / "Plate.FCStd")
    alice = manager(tmp_path)
    alice.acquire(part)
    rest.online = False
    with pytest.raises(locks.Offline):
        alice.acquire(str(tmp_path / "Other.FCStd"))
    assert alice.release(part) is True  # queued
    assert not alice.refresh() and alice.offline
    assert rest.tables["cobench_locks"]  # still in the database
    rest.online = True
    assert alice.refresh()
    assert rest.tables["cobench_locks"] == []


def test_versions(tmp_path, rest):
    part = str(tmp_path / "Plate.FCStd")
    alice, bob = manager(tmp_path), manager(tmp_path, "bob", "pc2", "s2")
    alice.set_version(part, "abc", 3)
    alice.set_version(part, "def", 4)
    bob.refresh()
    assert bob.version(part)["sha1"] == "def" and bob.version(part)["saved_by"] == "alice"
    rest.online = False
    alice.set_version(part, "ghi", 5)  # queued
    rest.online = True
    alice.refresh()
    bob.refresh()
    assert bob.version(part)["sha1"] == "ghi"


def test_project_keeps_locking_config(tmp_path):
    from cobench.core.project import Project
    project = Project(str(tmp_path))
    project.set_locking("supabase", "https://x.supabase.co/", "sb_publishable_k")
    again = Project(str(tmp_path))
    assert again.locking["store"] == "supabase" and again.locking["url"] == "https://x.supabase.co"
    assert again.locking["id"] == project.locking["id"]
    again.set_locking("files")
    assert Project(str(tmp_path)).locking == {"store": "files"}


def test_offline_version_is_sent_before_the_release(tmp_path, rest):
    part = str(tmp_path / "Plate.FCStd")
    alice = manager(tmp_path)
    assert alice.acquire(part).status == locks.MINE
    rest.online = False
    alice.set_version(part, "new-sha", 10)
    alice.release(part)
    order = []
    real = rest.request

    def spy(method, table, *a, **k):
        order.append((method, table))
        return real(method, table, *a, **k)
    rest.request = spy
    rest.online = True
    assert alice.refresh()
    assert order.index(("POST", "cobench_versions")) < order.index(("DELETE", "cobench_locks"))
    assert rest.tables["cobench_versions"][0]["sha1"] == "new-sha"
    assert rest.tables["cobench_locks"] == []


def test_refused_version_keeps_the_part(tmp_path, rest):
    part = str(tmp_path / "Plate.FCStd")
    alice = manager(tmp_path)
    alice.acquire(part)
    real = rest.request

    def refuse(method, table, *a, **k):
        if table == "cobench_versions":
            return 403, {"message": "denied"}
        return real(method, table, *a, **k)
    rest.request = refuse
    with pytest.raises(supabase.StoreError):
        alice.set_version(part, "new-sha", 10)
    assert alice.version_unsent(part)
    rest.request = real
    assert not alice.version_unsent(part)
    assert rest.tables["cobench_versions"][0]["sha1"] == "new-sha"


def test_languages_have_the_same_placeholders():
    import re
    from cobench import i18n
    folder = os.path.join(os.path.dirname(i18n.__file__), "translations")
    codes = ["fr"] + sorted(f[:-5] for f in os.listdir(folder) if f.endswith(".json"))
    source = [k for k in i18n.FR if k]
    for code in codes:
        cat = i18n.catalog(code)
        assert sorted(k for k in cat if k) == sorted(source), code
        for key in source:
            assert set(re.findall(r"\{\w+\}", key)) == set(re.findall(r"\{\w+\}", cat[key])), (code, key)
