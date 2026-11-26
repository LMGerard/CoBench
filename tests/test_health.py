# SPDX-License-Identifier: LGPL-2.1-or-later
"""State of the connection: versions, sync both ways, blocking."""

import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cobench.core import health  # noqa: E402


def test_versions():
    assert health.older("0.4.8", "0.5.0")
    assert not health.older("0.5.0", "0.5")
    assert not health.older("0.10.0", "0.9.9")
    assert not health.older("0.4.8", "")
    assert health.version_in_package("<package><version> 0.5.0 </version></package>") == "0.5.0"
    assert health.installed_version() == __import__("cobench").__version__


def test_part_key_ignores_accent_form_and_separators():
    decomposed = unicodedata.normalize("NFD", "sous/boîtier.FCStd")
    assert health.part_key(decomposed) == health.part_key("sous\\boîtier.FCStd")


def test_fingerprints_are_cached(tmp_path):
    part = tmp_path / "a.FCStd"
    part.write_bytes(b"one")
    cache = health.FingerprintCache()
    first = cache.read({"a": str(part)})
    assert first["a"][1] == 3
    part.write_bytes(b"two!")
    assert cache.read({"a": str(part)})["a"][0] != first["a"][0]
    assert cache.read({"a": str(tmp_path / "missing")}) == {}


def sync_items(tracker, local, server, versions=None, now=0):
    return tracker.compare(local, server, versions, now)


def test_receiving_turns_red_only_after_the_grace_delay():
    tracker = health.SyncTracker(grace=100)
    local = {"p": ("old", 1, 10.0)}
    server = {"p": {"sha1": "new", "size": 1, "mtime": 50.0}}
    items = sync_items(tracker, local, server, now=0)
    assert items["p"].direction == health.IN and not items["p"].late
    # The server copy keeps changing (someone saves often): still timed from the start,
    # because the local copy never changed.
    server = {"p": {"sha1": "newer", "size": 1, "mtime": 60.0}}
    assert sync_items(tracker, local, server, now=150)["p"].late
    # Arrived: nothing left.
    assert sync_items(tracker, {"p": ("newer", 1, 60.0)}, server, now=160) == {}


def test_sending_is_timed_while_the_server_copy_does_not_change():
    tracker = health.SyncTracker(grace=100)
    server = {"p": {"sha1": "s0", "size": 1, "mtime": 10.0}}
    sync_items(tracker, {"p": ("l1", 1, 20.0)}, server, now=0)
    # Saved again and again here, nothing reaches the server: red anyway.
    items = sync_items(tracker, {"p": ("l2", 1, 30.0)}, server, now=120)
    assert items["p"].direction == health.OUT and items["p"].late


def test_direction_follows_the_database_version_then_the_dates():
    direction = health.SyncTracker.direction
    assert direction(("a", 1, 99.0), {"sha1": "b", "mtime": 1.0}, "b") == health.IN
    assert direction(("a", 1, 1.0), {"sha1": "b", "mtime": 99.0}, "a") == health.OUT
    assert direction(("a", 1, 1.0), {"sha1": "b", "mtime": 99.0}, "") == health.IN
    assert direction(None, {"sha1": "b"}, "") == health.IN
    assert direction(("a", 1, 1.0), None, "") == health.OUT


def report(**values):
    base = dict(running="0.5.0", installed="0.5.0", store="supabase", server_state="ok", server_age=5,
                local={}, sync={}, user="alice", host="pc1")
    base.update(values)
    return health.evaluate(**base)


def levels(rep):
    return [c.level for c in rep.checks]


def test_all_green():
    rep = report()
    assert rep.level == health.OK and not rep.blocking and rep.server_ready
    assert rep.sent("anything")


def test_old_version_blocks():
    rep = report(running="0.4.8", installed="0.4.8", min_version="0.5.0")
    assert rep.blocking and "0.5.0" in rep.problems()[0].text
    rep = report(running="0.4.8", installed="0.5.0", min_version="0.5.0")
    assert rep.blocking and "FreeCAD" in rep.problems()[0].fix  # updated, not restarted


def test_new_version_or_restart_needed_only_warns():
    assert report(latest="0.6.0").level == health.WARNING
    assert report(running="0.5.0", installed="0.5.1").level == health.WARNING


def test_lock_database_problem_blocks():
    assert report(store_error="Supabase refused the key (401).").blocking
    assert report(store_error="timed out", store_offline=True).blocking


def test_late_sync_blocks_and_busy_sync_warns():
    late = {"p": health.SyncItem("p", health.IN, 500, True)}
    rep = report(sync=late, display={"p": "Plate"})
    assert rep.blocking and "Plate" in rep.problems()[0].text
    assert not rep.sent("p")
    busy = {"p": health.SyncItem("p", health.OUT, 10, False)}
    rep = report(sync=busy)
    assert rep.level == health.WARNING and not rep.blocking and not rep.sent("p")


def test_scanner_missing_or_stopped():
    rep = report(server_state="missing")
    assert rep.level == health.OK and not rep.server_ready  # off: grey lines, nothing blocked
    assert health.OFF in levels(rep)
    rep = report(server_age=500)
    assert rep.level == health.WARNING and not rep.server_ready
    rep = report(store="files")
    assert not rep.blocking and not rep.server_ready


def test_unnamed_user_warns():
    assert report(user_named=False).level == health.WARNING


def test_summary_names_the_first_problem():
    rep = report(running="0.4.8", installed="0.4.8", min_version="0.5.0", store_error="refused")
    assert rep.summary().startswith("2 ") and "0.5.0" in rep.summary()
    assert "0.5.0" in report(running="0.4.8", min_version="0.5.0").summary()
    assert report(latest="0.6.0").summary() == report(latest="0.6.0").warnings()[0].text
