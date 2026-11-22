# SPDX-License-Identifier: LGPL-2.1-or-later
"""Proposals: create, comment, detect conflicts, integrate, refuse."""

import json
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cobench.core import fcstd, locks, proposals, stamps  # noqa: E402
from cobench.core.identity import Identity  # noqa: E402
from cobench.core.project import Project  # noqa: E402
from test_core import make_part  # noqa: E402

ALICE = Identity("alice", "pc1")
BOB = Identity("bob", "pc2")


def links(path):
    fcstd.clear_cache()
    return fcstd.read_part(path).links


def resolved(path):
    return [os.path.normcase(fcstd.resolve_link(path, t)) for t in links(path)]


def project(tmp_path):
    """Variables, a plate reading it, an assembly of the plate and a pin in sub/."""
    root = str(tmp_path / "proj")
    make_part(os.path.join(root, "Variables.FCStd"))
    make_part(os.path.join(root, "sub", "Plate.FCStd"), links=["../Variables.FCStd"])
    make_part(os.path.join(root, "sub", "Pin.FCStd"))
    make_part(os.path.join(root, "Asm.FCStd"), links=["sub/Plate.FCStd", "sub/Pin.FCStd"])
    return root


def change(path, author="alice"):
    """Save the file again with another content (as FreeCAD would)."""
    fcstd.clear_cache()
    keep = links(path)
    make_part(path, author=author + "-changed", links=keep)


def manager(identity, session="s"):
    return locks.LockManager(identity, session + identity.user)


# -- links ------------------------------------------------------------------------

def test_relocate_keeps_links_pointing_to_the_same_files(tmp_path):
    root = project(tmp_path)
    plate = os.path.join(root, "sub", "Plate.FCStd")
    copy = os.path.join(root, "elsewhere", "deep", "Plate.copy")
    proposals.relocate(plate, copy)
    assert links(copy) == ["../../Variables.FCStd"]
    assert resolved(copy) == resolved(plate)
    with zipfile.ZipFile(plate) as a, zipfile.ZipFile(copy) as b:
        assert a.read("thumbnails/Thumbnail.png") == b.read("thumbnails/Thumbnail.png")


def test_relocate_mapping_and_special_characters(tmp_path):
    root = str(tmp_path / "p")
    make_part(os.path.join(root, "A & B.FCStd"))
    make_part(os.path.join(root, "Asm.FCStd"), links=["A &amp; B.FCStd", ""])
    target = os.path.join(root, "new", "A & B.other")
    proposals.relocate(os.path.join(root, "Asm.FCStd"), os.path.join(root, "x", "Asm.FCStd"),
                       {os.path.normcase(os.path.join(root, "A & B.FCStd")): target})
    moved = os.path.join(root, "x", "Asm.FCStd")
    assert links(moved) == ["../new/A & B.other"]
    with zipfile.ZipFile(moved) as archive:
        xml = archive.read("Document.xml")
    assert b'file="../new/A &amp; B.other"' in xml and b'file=""' in xml


# -- create -------------------------------------------------------------------------

def test_create_copies_parts_and_records_the_base(tmp_path):
    root = project(tmp_path)
    plate = os.path.join(root, "sub", "Plate.FCStd")
    asm = os.path.join(root, "Asm.FCStd")
    stamps.write(plate, BOB)
    p = proposals.create(root, ALICE, [plate, asm], "Thicker plate", "6 mm instead of 4")
    again = proposals.Proposal.load(p.folder)
    assert again.title == "Thicker plate" and again.message == "6 mm instead of 4"
    assert (again.user, again.host, again.status) == ("alice", "pc1", proposals.OPEN)
    assert [f.part for f in again.files] == ["sub/Plate.FCStd", "Asm.FCStd"]
    item = again.files[0]
    assert item.base["sha1"] == stamps.fingerprint(plate) and item.base["saved_by"] == "bob"
    assert item.stored == "files/sub/Plate.cobench-fcstd"
    # The copy of the plate still reads the project's Variables...
    stored_plate = again.stored_path(item)
    assert resolved(stored_plate) == [os.path.normcase(os.path.join(root, "Variables.FCStd"))]
    # ...and the proposed assembly uses the proposed plate, but the project's pin.
    stored_asm = again.stored_path(again.files[1])
    assert resolved(stored_asm) == [os.path.normcase(stored_plate),
                                    os.path.normcase(os.path.join(root, "sub", "Pin.FCStd"))]
    # The originals are untouched and no lock was taken.
    assert links(asm) == ["sub/Plate.FCStd", "sub/Pin.FCStd"]
    assert not os.path.exists(plate + locks.LOCK_SUFFIX)


def test_older_cobench_ignores_the_proposals(tmp_path):
    root = project(tmp_path)
    before = Project(root).parts()
    proposals.create(root, ALICE, [os.path.join(root, "sub", "Plate.FCStd")], "x")
    assert Project(root).parts() == before
    # What a CoBench without proposals does: every *.FCStd outside hidden folders.
    old = [os.path.join(d, n) for d, dirs, files in os.walk(root)
           for n in files if n.lower().endswith(".fcstd") and not d.startswith(".")]
    assert sorted(old) == sorted(before)
    assert not any(name.startswith(".") for name in os.listdir(root))  # synchronised by every client


def test_add_part_relinks_the_parts_already_proposed(tmp_path):
    root = project(tmp_path)
    plate, asm = os.path.join(root, "sub", "Plate.FCStd"), os.path.join(root, "Asm.FCStd")
    p = proposals.create(root, ALICE, [asm], "x")
    stored_asm = p.stored_path(p.files[0])
    assert os.path.normcase(plate) in resolved(stored_asm)
    proposals.add_parts(p, ALICE, [plate])
    stored_plate = p.stored_path(p.file_for(plate))
    assert os.path.normcase(stored_plate) in resolved(stored_asm)
    with pytest.raises(proposals.ProposalError):
        proposals.add_parts(p, BOB, [os.path.join(root, "sub", "Pin.FCStd")])
    proposals.remove_part(p, ALICE, p.file_for(plate))
    assert not os.path.exists(stored_plate)
    assert os.path.normcase(plate) in resolved(stored_asm)
    assert [f.part for f in proposals.Proposal.load(p.folder).files] == ["Asm.FCStd"]


def test_list_and_lookup(tmp_path):
    root = project(tmp_path)
    plate = os.path.join(root, "sub", "Plate.FCStd")
    first = proposals.create(root, ALICE, [plate], "first")
    second = proposals.create(root, BOB, [os.path.join(root, "Asm.FCStd")], "second")
    proposals.refuse(first, BOB, "no")
    assert [p.id for p in proposals.list_proposals(root, include_closed=False)] == [second.id]
    assert {p.id for p in proposals.list_proposals(root)} == {first.id, second.id}
    stored = first.stored_path(first.files[0])
    owner, item = proposals.proposed_part(root, stored)
    assert owner.id == first.id and item.part == "sub/Plate.FCStd"
    assert proposals.proposed_part(root, plate) == (None, None)
    assert proposals.is_proposal_path(root, stored) and not proposals.is_proposal_path(root, plate)
    assert proposals.open_for(root, plate) == []
    assert [p.id for p in proposals.open_for(root, os.path.join(root, "Asm.FCStd"))] == [second.id]


def test_half_synchronised_proposal_is_skipped(tmp_path):
    root = project(tmp_path)
    folder = os.path.join(root, proposals.DIR_NAME, "20261122-000000-bob-0000")
    os.makedirs(folder)
    with open(os.path.join(folder, proposals.INFO_FILE), "w") as stream:
        stream.write('{"title": ')
    assert proposals.list_proposals(root) == []


# -- comments, refuse, withdraw -----------------------------------------------------------

def test_comments_are_separate_files(tmp_path):
    root = project(tmp_path)
    p = proposals.create(root, ALICE, [os.path.join(root, "sub", "Plate.FCStd")], "x")
    proposals.comment(p, BOB, "Why 6 mm?")
    proposals.comment(p, ALICE, "Stiffness")
    assert proposals.comment(p, BOB, "   ") is None
    texts = [(c.user, c.text) for c in proposals.Proposal.load(p.folder).comments()]
    assert sorted(texts) == [("alice", "Stiffness"), ("bob", "Why 6 mm?")]
    assert len(os.listdir(os.path.join(p.folder, proposals.COMMENTS_DIR))) == 2


def test_refuse_closes_once(tmp_path):
    root = project(tmp_path)
    plate = os.path.join(root, "sub", "Plate.FCStd")
    before = stamps.fingerprint(plate)
    p = proposals.create(root, ALICE, [plate], "x")
    proposals.refuse(p, BOB, "Too heavy")
    seen = proposals.Proposal.load(p.folder)
    assert seen.status == proposals.REFUSED and seen.closed_by() == "bob"
    assert seen.comments()[-1].text == "Too heavy" and seen.comments()[-1].kind == proposals.REFUSED
    assert stamps.fingerprint(plate) == before
    with pytest.raises(proposals.ProposalError):
        proposals.refuse(seen, ALICE, "again")
    with pytest.raises(proposals.ProposalError):
        proposals.integrate(seen, BOB, manager(BOB))


def test_only_the_author_withdraws(tmp_path):
    root = project(tmp_path)
    p = proposals.create(root, ALICE, [os.path.join(root, "sub", "Plate.FCStd")], "x")
    with pytest.raises(proposals.ProposalError):
        proposals.withdraw(p, BOB)
    proposals.withdraw(p, ALICE, "done another way")
    assert proposals.Proposal.load(p.folder).status == proposals.WITHDRAWN


# -- conflicts ---------------------------------------------------------------------

def test_conflict_when_the_part_changed_since(tmp_path):
    root = project(tmp_path)
    plate = os.path.join(root, "sub", "Plate.FCStd")
    p = proposals.create(root, ALICE, [plate], "x")
    assert proposals.check(p) == []
    change(plate, "carol")
    conflicts = proposals.check(p)
    assert [(c.part, c.reason) for c in conflicts] == [("sub/Plate.FCStd", proposals.CHANGED)]
    changed = stamps.fingerprint(plate)
    result = proposals.integrate(p, BOB, manager(BOB))
    assert not result and result.conflicts[0].reason == proposals.CHANGED
    assert stamps.fingerprint(plate) == changed  # nothing replaced
    assert not os.path.exists(plate + locks.LOCK_SUFFIX)
    assert proposals.Proposal.load(p.folder).is_open


def test_conflict_reported_by_the_version_database(tmp_path):
    root = project(tmp_path)
    plate = os.path.join(root, "sub", "Plate.FCStd")
    p = proposals.create(root, ALICE, [plate], "x")
    base = p.files[0].base["sha1"]
    # Someone saved a newer version; the file has not arrived on this computer yet.
    assert proposals.check(p, latest=lambda path: "newer")[0].reason == proposals.CHANGED
    # The database knows the base, but the file here is another one (e.g. still syncing).
    change(plate)
    assert proposals.check(p, latest=lambda path: base)[0].reason == proposals.NOT_ARRIVED


def test_conflict_when_missing_locked_or_unreadable(tmp_path):
    root = project(tmp_path)
    plate, pin = os.path.join(root, "sub", "Plate.FCStd"), os.path.join(root, "sub", "Pin.FCStd")
    asm = os.path.join(root, "Asm.FCStd")
    p = proposals.create(root, ALICE, [plate, pin, asm], "x")
    os.remove(pin)
    manager(Identity("carol", "pc3")).acquire(plate)
    with open(p.stored_path(p.file_for(asm)), "wb") as stream:
        stream.write(b"half synchronised")
    reasons = {c.part: c.reason for c in proposals.check(p, lock_manager=manager(BOB))}
    assert reasons == {"sub/Pin.FCStd": proposals.MISSING, "sub/Plate.FCStd": proposals.LOCKED,
                       "Asm.FCStd": proposals.UNREADABLE}


# -- integrate --------------------------------------------------------------------

def test_integrate_replaces_the_parts_and_closes(tmp_path):
    root = project(tmp_path)
    plate, asm = os.path.join(root, "sub", "Plate.FCStd"), os.path.join(root, "Asm.FCStd")
    old_plate = stamps.fingerprint(plate)
    p = proposals.create(root, ALICE, [plate, asm], "Thicker plate")
    # The author edits the copies in FreeCAD (here: a new save of each copy).
    for item in p.files:
        stored = p.stored_path(item)
        keep = links(stored)
        make_part(stored, author="alice-proposal", links=keep)
    bob = manager(BOB)
    result = proposals.integrate(p, BOB, bob, "Thanks")
    assert result and result.conflicts == [] and result.warnings == []
    # The parts are the proposed versions, linked to the project again.
    fcstd.clear_cache()
    assert fcstd.read_part(plate).meta["LastModifiedBy"] == "alice-proposal"
    assert links(plate) == ["../Variables.FCStd"]
    assert links(asm) == ["sub/Plate.FCStd", "sub/Pin.FCStd"]
    # A new version in the integrator's name, citing the author.
    stamp = json.load(open(stamps.stamp_path(plate), encoding="utf-8"))
    assert stamp["user"] == "bob" and stamp["author"] == "alice" and stamp["proposal"] == p.id
    assert stamp["sha1"] == stamps.fingerprint(plate)
    # Locks given back, the previous version kept, the proposal closed.
    assert not os.path.exists(plate + locks.LOCK_SUFFIX) and not bob.held
    assert stamps.fingerprint(p.previous_path(p.file_for(plate))) == old_plate
    seen = proposals.Proposal.load(p.folder)
    assert seen.status == proposals.INTEGRATED and seen.closed_by() == "bob"
    assert seen.decision["author"] == "alice"
    assert [f["part"] for f in seen.decision["files"]] == ["sub/Plate.FCStd", "Asm.FCStd"]
    assert Project(root).parts() == sorted(Project(root).parts(), key=lambda x: Project(root).rel(x).lower())
    with pytest.raises(proposals.ProposalError):
        proposals.integrate(seen, BOB, bob)


def test_integrate_keeps_a_lock_i_already_held(tmp_path):
    root = project(tmp_path)
    plate = os.path.join(root, "sub", "Plate.FCStd")
    p = proposals.create(root, ALICE, [plate], "x")
    bob = manager(BOB)
    bob.acquire(plate)
    assert proposals.integrate(p, BOB, bob)
    assert bob.state(plate).status == locks.MINE


def test_integrate_refused_when_a_lock_is_taken_meanwhile(tmp_path):
    root = project(tmp_path)
    plate, asm = os.path.join(root, "sub", "Plate.FCStd"), os.path.join(root, "Asm.FCStd")
    p = proposals.create(root, ALICE, [plate, asm], "x")
    before = stamps.fingerprint(plate)

    class Racing(locks.LockManager):
        """Carol takes the assembly between the check and our lock."""
        def acquire(self, part):
            if part.endswith("Asm.FCStd"):
                manager(Identity("carol", "pc3")).acquire(part)
            return super().acquire(part)
    bob = Racing(BOB, "s-bob")
    result = proposals.integrate(p, BOB, bob)
    assert not result and result.conflicts[0].reason == proposals.LOCKED
    assert result.conflicts[0].detail == "carol"
    assert stamps.fingerprint(plate) == before
    assert not os.path.exists(plate + locks.LOCK_SUFFIX)  # the lock taken was given back
    assert proposals.Proposal.load(p.folder).is_open


def test_integrate_with_the_supabase_store(tmp_path, monkeypatch):
    from cobench.core import supabase
    from test_supabase import FakeRest
    fake = FakeRest()
    monkeypatch.setattr(supabase.Client, "request", lambda self, *a, **k: fake.request(*a, **k))
    root = project(tmp_path)
    proj = Project(root)
    plate = os.path.join(root, "sub", "Plate.FCStd")
    bob = supabase.SupabaseLockManager(BOB, "s2", "FreeCAD", "https://x.supabase.co", "sb_publishable_t",
                                       "proj1", proj.rel)
    bob.set_version(plate, stamps.fingerprint(plate), os.path.getsize(plate))
    p = proposals.create(root, ALICE, [plate], "x")

    def latest(path):
        version = bob.version(path)
        return version["sha1"] if version else None
    assert proposals.integrate(p, BOB, bob, latest=latest)
    row = fake.tables["cobench_versions"][0]
    assert row["sha1"] == stamps.fingerprint(plate) and row["saved_by"] == "bob"
    assert fake.tables["cobench_locks"] == []
