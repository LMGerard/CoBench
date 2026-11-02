# SPDX-License-Identifier: LGPL-2.1-or-later
"""Version stamps and the sync state fallback."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cobench.core import stamps, syncstate  # noqa: E402
from cobench.core.identity import Identity  # noqa: E402


def _write(path, data):
    with open(path, "wb") as stream:
        stream.write(data)


def test_same_copy_is_latest(tmp_path):
    part = str(tmp_path / "Plate.FCStd")
    _write(part, b"v1")
    stamps.write(part, Identity("alice", "pc1"))
    assert stamps.newer_elsewhere(part) is None


def test_older_copy_is_reported(tmp_path):
    part = str(tmp_path / "Plate.FCStd")
    _write(part, b"v1")
    old = time.time() - 3600
    os.utime(part, (old, old))  # the copy on this computer, from an hour ago
    _write(part + ".new", b"v2-longer")
    os.replace(part + ".new", part)
    os.utime(part, (old, old))
    # the stamp says bob saved another content just now
    stamps.write(part, Identity("bob", "pc2"))
    _write(part, b"v1")
    os.utime(part, (old, old))
    stamp = stamps.newer_elsewhere(part)
    assert stamp is not None and stamp.user == "bob"


def test_copy_saved_after_stamp_is_not_reported(tmp_path):
    part = str(tmp_path / "Plate.FCStd")
    _write(part, b"v1")
    stamps.write(part, Identity("bob", "pc2"))
    _write(part, b"saved without CoBench")
    later = time.time() + 60
    os.utime(part, (later, later))
    assert stamps.newer_elsewhere(part) is None


def test_no_stamp(tmp_path):
    part = str(tmp_path / "Plate.FCStd")
    _write(part, b"v1")
    assert stamps.newer_elsewhere(part) is None
    stamps.remove(part)


def test_sync_state_unknown_off_windows(tmp_path):
    part = str(tmp_path / "Plate.FCStd")
    _write(part, b"v1")
    if sys.platform != "win32":
        assert syncstate.file_state(part) == syncstate.UNKNOWN
