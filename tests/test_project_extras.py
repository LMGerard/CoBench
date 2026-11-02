# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tags, moves, broken links and part requests."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cobench.core import requests  # noqa: E402
from cobench.core.identity import Identity  # noqa: E402
from cobench.core.project import Project  # noqa: E402
from test_core import make_part  # noqa: E402


def test_tags_are_shared_and_cleaned(tmp_path):
    part = str(tmp_path / "Plate.FCStd")
    make_part(part)
    project = Project(str(tmp_path))
    project.set_tags(part, ["#frame", "frame", " metal ", ""])
    assert project.tags_of(part) == ["frame", "metal"]
    other = Project(str(tmp_path))  # someone else's CoBench
    assert other.tags_of(part) == ["frame", "metal"]
    assert other.all_tags() == ["frame", "metal"]
    other.set_tags(part, [])
    project.load()
    assert project.tags_of(part) == []


def test_set_tags_keeps_assembly_saved_by_others(tmp_path):
    a, b = str(tmp_path / "A.FCStd"), str(tmp_path / "B.FCStd")
    make_part(a)
    make_part(b)
    mine, theirs = Project(str(tmp_path)), Project(str(tmp_path))
    theirs.set_assembly(b)
    mine.set_tags(a, ["x"])
    assert Project(str(tmp_path)).assembly == "B.FCStd"


def test_moved_carries_tags_and_assembly(tmp_path):
    os.makedirs(tmp_path / "sub")
    old, new = str(tmp_path / "Asm.FCStd"), str(tmp_path / "sub" / "Main.FCStd")
    make_part(old)
    project = Project(str(tmp_path))
    project.set_assembly(old)
    project.set_tags(old, ["top"])
    os.replace(old, new)
    project.moved(old, new)
    again = Project(str(tmp_path))
    assert again.assembly == "sub/Main.FCStd"
    assert again.tags_of(new) == ["top"]
    assert again.tags_of(old) == []


def test_missing_links(tmp_path):
    make_part(str(tmp_path / "Plate.FCStd"))
    make_part(str(tmp_path / "Asm.FCStd"), links=["Plate.FCStd", "Gone.FCStd", "Gone.FCStd"])
    project = Project(str(tmp_path))
    missing = project.missing_links()
    assert list(missing) == [str(tmp_path / "Asm.FCStd")]
    assert [os.path.basename(p) for p in missing[str(tmp_path / "Asm.FCStd")]] == ["Gone.FCStd"]


def test_request_cycle(tmp_path):
    part = str(tmp_path / "Plate.FCStd")
    make_part(part)
    assert requests.Request.read(part) is None
    bob = Identity("bob", "pc-bob")
    sent = requests.write(part, bob)
    assert (sent.user, sent.host, sent.status) == ("bob", "pc-bob", requests.PENDING)
    requests.decline(part, sent)
    seen = requests.Request.read(part)
    assert seen.status == requests.DECLINED and seen.user == "bob" and seen.since == sent.since
    assert requests.clear(part) is True
    assert requests.clear(part) is False
    assert requests.Request.read(part) is None


def test_half_written_request_is_ignored(tmp_path):
    part = str(tmp_path / "Plate.FCStd")
    with open(requests.request_path(part), "w") as stream:
        stream.write("{\"user\": ")
    assert requests.Request.read(part) is None
