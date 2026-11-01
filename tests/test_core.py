# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tests of the FreeCAD-independent part.  Run with:  python -m pytest tests"""

import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cobench.core import fcstd, locks  # noqa: E402
from cobench.core.identity import Identity  # noqa: E402
from cobench.core.project import Project, find_root  # noqa: E402

def _png(width=8, height=8, rgb=(70, 130, 200)):
    """A small valid PNG, built without any imaging library."""
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    row = b"\x00" + bytes(rgb) * width
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


PNG = _png()


def document_xml(author="", links=()):
    """Shape of a FreeCAD 1.0 Document.xml, reduced to what CoBench reads."""
    xlinks = "".join(
        '<Object name="Link%d"><Properties Count="1">'
        '<Property name="LinkedObject" type="App::PropertyXLink">'
        '<XLink file="%s" stamp="2026-11-01T10:00:00Z" name="Body"/></Property>'
        '</Properties></Object>' % (i, target) for i, target in enumerate(links))
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Document SchemaVersion="4" ProgramVersion="1.0.0" FileVersion="1">\n'
        ' <Properties Count="3">\n'
        '  <Property name="Label" type="App::PropertyString"><String value="Doc"/></Property>\n'
        '  <Property name="LastModifiedBy" type="App::PropertyString"><String value="%s"/></Property>\n'
        '  <Property name="LastModifiedDate" type="App::PropertyString"><String value="2026-11-01"/></Property>\n'
        ' </Properties>\n'
        ' <Objects Count="%d"/>\n'
        ' <ObjectData Count="%d">%s</ObjectData>\n'
        '</Document>\n' % (author, len(links), len(links), xlinks))


def make_part(path, author="", links=(), thumbnail=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Document.xml", document_xml(author, links))
        if thumbnail:
            archive.writestr("thumbnails/Thumbnail.png", PNG)
    return path


def manager(user="alice", host="pc1", session="s1"):
    return locks.LockManager(Identity(user, host), session)


# -- locks -------------------------------------------------------------------

def test_acquire_release(tmp_path):
    part = make_part(str(tmp_path / "Plate.FCStd"))
    alice = manager()
    assert alice.state(part).status == locks.FREE
    state = alice.acquire(part)
    assert state.status == locks.MINE
    assert os.path.exists(part + locks.LOCK_SUFFIX)
    data = json.load(open(part + locks.LOCK_SUFFIX, encoding="utf-8"))
    assert data["user"] == "alice" and data["host"] == "pc1"
    assert alice.holds(part)
    assert alice.release(part)
    assert not os.path.exists(part + locks.LOCK_SUFFIX)
    assert not alice.holds(part)


def test_other_user_sees_lock_and_cannot_release(tmp_path):
    part = make_part(str(tmp_path / "Plate.FCStd"))
    alice, bob = manager(), manager("bob", "pc2", "s2")
    alice.acquire(part)
    state = bob.state(part)
    assert state.status == locks.OTHER and state.info.user == "alice"
    assert bob.acquire(part).status == locks.OTHER
    assert not bob.release(part)
    assert os.path.exists(part + locks.LOCK_SUFFIX)


def test_acquire_twice_is_idempotent(tmp_path):
    part = make_part(str(tmp_path / "Plate.FCStd"))
    alice = manager()
    alice.acquire(part)
    assert alice.acquire(part).status == locks.MINE


def test_orphan_lock_of_crashed_session_is_taken_back(tmp_path):
    part = make_part(str(tmp_path / "Plate.FCStd"))
    lock = locks.LockInfo("alice", "pc1", pid=999999999, since=locks.now_iso(), session="old")
    open(part + locks.LOCK_SUFFIX, "w", encoding="utf-8").write(lock.to_json())
    alice = manager()
    assert alice.state(part).status == locks.ORPHAN
    assert alice.acquire(part).status == locks.MINE
    assert json.load(open(part + locks.LOCK_SUFFIX, encoding="utf-8"))["session"] == "s1"


def test_same_user_other_live_freecad_is_other(tmp_path):
    part = make_part(str(tmp_path / "Plate.FCStd"))
    lock = locks.LockInfo("alice", "pc1", pid=os.getppid(), since=locks.now_iso(), session="other")
    open(part + locks.LOCK_SUFFIX, "w", encoding="utf-8").write(lock.to_json())
    assert manager().state(part).status == locks.OTHER


def test_force_takes_lock_from_other(tmp_path):
    part = make_part(str(tmp_path / "Plate.FCStd"))
    manager("bob", "pc2", "s2").acquire(part)
    alice = manager()
    assert alice.force(part).status == locks.MINE
    assert manager("bob", "pc2", "s2").state(part).status == locks.OTHER


def test_corrupt_lock_still_blocks(tmp_path):
    part = make_part(str(tmp_path / "Plate.FCStd"))
    open(part + locks.LOCK_SUFFIX, "w").write("{half written")
    state = manager().state(part)
    assert state.status == locks.OTHER and state.info.user == "?"


def test_release_all(tmp_path):
    parts = [make_part(str(tmp_path / ("P%d.FCStd" % i))) for i in range(3)]
    alice = manager()
    for part in parts:
        alice.acquire(part)
    alice.release_all()
    assert not any(os.path.exists(p + locks.LOCK_SUFFIX) for p in parts)


def test_conflict_copies(tmp_path):
    part = make_part(str(tmp_path / "Plate.FCStd"))
    make_part(str(tmp_path / "Plate (conflicted copy 2026-11-01 101010).FCStd"))
    open(str(tmp_path / "Plate.FCStd (conflicted copy).cobench-lock"), "w").write("{}")
    make_part(str(tmp_path / "Other.FCStd"))
    found = [os.path.basename(p) for p in locks.find_conflicts(part)]
    assert len(found) == 2


def test_read_only(tmp_path):
    part = make_part(str(tmp_path / "Plate.FCStd"))
    assert locks.set_read_only(part, True)
    assert locks.is_read_only(part)
    assert not locks.set_read_only(part, True)
    assert locks.set_read_only(part, False)
    assert not locks.is_read_only(part)


def test_lock_age():
    info = locks.LockInfo(since="2026-11-01T10:00:00+00:00")
    import datetime
    now = datetime.datetime(2026, 11, 1, 11, 0, tzinfo=datetime.timezone.utc)
    assert info.age_seconds(now) == 3600


# -- files and project ----------------------------------------------------------

def test_read_part(tmp_path):
    part = make_part(str(tmp_path / "Asm.FCStd"), author="Gaelle", links=["Plate.FCStd", "sub/Pin.FCStd"])
    data = fcstd.read_part(part)
    assert data.thumbnail == PNG
    assert data.meta["LastModifiedBy"] == "Gaelle"
    assert data.meta["Label"] == "Doc"
    assert data.links == ["Plate.FCStd", "sub/Pin.FCStd"]
    assert data.error is None


def test_read_broken_part(tmp_path):
    path = str(tmp_path / "Broken.FCStd")
    open(path, "wb").write(b"not a zip")
    assert fcstd.read_part(path).error


def test_project_scan_and_assembly(tmp_path):
    root = str(tmp_path / "proj")
    make_part(os.path.join(root, "Plate.FCStd"))
    make_part(os.path.join(root, "sub", "Pin.FCStd"))
    make_part(os.path.join(root, "Asm.FCStd"), links=["Plate.FCStd", "sub/Pin.FCStd", "Missing.FCStd"])
    make_part(os.path.join(root, ".hidden", "Ignored.FCStd"))
    make_part(os.path.join(root, "Plate (conflicted copy).FCStd"))
    open(os.path.join(root, "Plate.FCStd" + locks.LOCK_SUFFIX), "w").write("{}")
    project = Project(root)
    rels = [project.rel(p) for p in project.parts()]
    assert rels == ["Asm.FCStd", "Plate.FCStd", "sub/Pin.FCStd"]
    graph = project.link_graph()
    asm = project.abs("Asm.FCStd")
    assert [project.rel(p) for p in graph[asm]] == ["Plate.FCStd", "sub/Pin.FCStd"]
    assert project.used_in(graph)[project.abs("Plate.FCStd")] == [asm]
    assert project.suggest_assembly(graph) == asm


def test_project_file_round_trip(tmp_path):
    root = str(tmp_path / "proj")
    make_part(os.path.join(root, "a", "Asm.FCStd"))
    project = Project(root)
    project.name = "Cabas"
    project.set_assembly(project.abs("a/Asm.FCStd"))
    again = Project(root)
    assert again.name == "Cabas" and again.assembly == "a/Asm.FCStd"
    assert find_root(os.path.join(root, "a", "Asm.FCStd")) == os.path.abspath(root)
    assert again.contains(os.path.join(root, "a", "Asm.FCStd"))
    assert not again.contains(str(tmp_path / "elsewhere.FCStd"))
