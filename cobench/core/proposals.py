# SPDX-License-Identifier: LGPL-2.1-or-later
"""Proposals: the pull requests of a CoBench project.

A member prepares a changed version of one or more parts without taking
their locks.  The others look at it, comment, and one of them integrates it
(the parts are replaced) or refuses it.

Everything lives in the project folder, so it travels with the same sync as
the parts::

    cobench-proposals/
      20261122-101500-alice-3f2a/
        proposal.json                 written by the author only
        files/sub/Plate.cobench-fcstd the proposed Plate.FCStd (a normal .FCStd file)
        comments/<date>-<user>-<n>.json   one file per comment, never rewritten
        decision.json                 written once: integrated, refused or withdrawn
        previous/sub/Plate.cobench-previous   the part as it was before integration

Every file has a single writer, so two people never write the same file at
the same time through the sync.  The folder name does not start with a dot
(sync clients skip hidden files) and the proposed parts do not end with
``.FCStd``: a CoBench without proposals does not list them as parts.

A proposed part is a copy of the part whose links (``App::Link``, expressions
to ``Variables``...) are rewritten so they still point to the project's
parts, or to the other proposed parts of the same proposal.  FCStd files
cannot be merged: a part is integrated only if it has not changed since the
proposal was made (same sha1), and the whole file is replaced.
"""

import datetime
import json
import os
import re
import shutil
import uuid
import zipfile

from . import locks, stamps
from .locks import now_iso
from .project import PROPOSALS_DIR as DIR_NAME
INFO_FILE = "proposal.json"
DECISION_FILE = "decision.json"
COMMENTS_DIR = "comments"
FILES_DIR = "files"
PREVIOUS_DIR = "previous"
STORED_SUFFIX = ".cobench-fcstd"
PREVIOUS_SUFFIX = ".cobench-previous"
FORMAT = 1

OPEN = "open"
INTEGRATED = "integrated"
REFUSED = "refused"
WITHDRAWN = "withdrawn"
CLOSED = (INTEGRATED, REFUSED, WITHDRAWN)

# Reasons a part cannot be integrated.
CHANGED = "changed"          # the part was saved since the proposal was made
NOT_ARRIVED = "not-arrived"  # the database knows the base, the file here is another one
MISSING = "missing"          # the part was deleted or moved
UNREADABLE = "unreadable"    # the proposed file is missing or still being synchronised
LOCKED = "locked"            # someone else holds the part


class ProposalError(Exception):
    """An action that cannot be done (proposal closed, not the author...)."""


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _write_json(path, data, exclusive=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=1, ensure_ascii=False)
        return
    tmp = path + ".tmp-%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return None  # missing or half-synchronised
    return data if isinstance(data, dict) else None


def _slug(text):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", text or "").strip("-")[:24] or "x"


def folder_of(root):
    return os.path.join(root, DIR_NAME)


def stored_name(rel_part):
    """``sub/Plate.FCStd`` -> ``files/sub/Plate.cobench-fcstd``"""
    return FILES_DIR + "/" + os.path.splitext(rel_part)[0] + STORED_SUFFIX


def previous_name(rel_part):
    return PREVIOUS_DIR + "/" + os.path.splitext(rel_part)[0] + PREVIOUS_SUFFIX


def is_proposal_path(root, path):
    """True for any file inside the proposals folder of the project."""
    if not root or not path:
        return False
    try:
        rel = os.path.relpath(os.path.abspath(path), folder_of(root))
    except ValueError:
        return False
    return not rel.startswith("..") and not os.path.isabs(rel)


# -- links inside a .FCStd ----------------------------------------------------

_XLINK = re.compile(rb'(<XLink\b[^>]*?\bfile=")([^"]*)(")')
_ENTITIES = {"&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'"}


def _unescape(text):
    def entity(match):
        name = match.group(0)
        if name.startswith("&#x"):
            return chr(int(name[3:-1], 16))
        if name.startswith("&#"):
            return chr(int(name[2:-1]))
        return _ENTITIES.get(name, name)
    return re.sub(r"&(#x[0-9a-fA-F]+|#[0-9]+|lt|gt|quot|apos);", entity, text).replace("&amp;", "&")


def _escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _new_target(target, base_dir, new_dir, mapping):
    """Where an XLink written relative to base_dir points, written relative to new_dir."""
    if not target:
        return target  # link inside the same document
    absolute = os.path.isabs(target.replace("/", os.sep))
    full = os.path.normpath(target if absolute else os.path.join(base_dir, target))
    full = mapping.get(_norm(full), full)
    if absolute:
        return full.replace("\\", "/")
    try:
        return os.path.relpath(full, new_dir).replace("\\", "/")
    except ValueError:  # another drive on Windows
        return full.replace("\\", "/")


def relocate(src, dst, mapping=None, base=None):
    """Copy the .FCStd ``src`` to ``dst`` keeping its links pointing to the same files.

    FreeCAD writes the files linked by a document relative to the document,
    so a plain copy elsewhere loses its links.  Each ``<XLink file=...>`` of
    Document.xml is resolved from ``base`` (default: the folder of ``src``),
    replaced through ``mapping`` ({normalised absolute path: new absolute
    path}) and written again relative to ``dst``.  Everything else in the
    archive is copied unchanged.  ``src`` and ``dst`` may be the same file.
    """
    mapping = mapping or {}
    base_dir = os.path.dirname(os.path.abspath(base or src))
    new_dir = os.path.dirname(os.path.abspath(dst))

    def rewrite(match):
        target = _unescape(match.group(2).decode("utf-8"))
        new = _new_target(target, base_dir, new_dir, mapping)
        return match.group(1) + _escape(new).encode("utf-8") + match.group(3)

    os.makedirs(new_dir, exist_ok=True)
    tmp = dst + ".tmp-%d" % os.getpid()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "Document.xml":
                data = _XLINK.sub(rewrite, data)
            zout.writestr(info, data)
    os.replace(tmp, dst)


# -- the proposal ---------------------------------------------------------------

class ProposalFile:
    """One part changed by a proposal, and the version it was made from."""

    def __init__(self, part, stored="", base=None):
        self.part = part                    # path of the part in the project ("/" separators)
        self.stored = stored or stored_name(part)
        self.base = dict(base or {})        # sha1, size, saved_by, saved_at of the original

    def to_json(self):
        return {"part": self.part, "stored": self.stored, "base": self.base}

    @classmethod
    def from_json(cls, data):
        return cls(str(data.get("part", "")), str(data.get("stored", "")), data.get("base") or {})


class Comment:
    def __init__(self, user="?", host="?", date="", text="", kind="comment", path=""):
        self.user, self.host, self.date, self.text, self.kind, self.path = user, host, date, text, kind, path


class Proposal:
    def __init__(self, folder):
        self.folder = os.path.abspath(folder)
        self.id = os.path.basename(self.folder)
        self.title = ""
        self.message = ""
        self.user = "?"
        self.host = "?"
        self.created = ""
        self.updated = ""
        self.files = []
        self.decision = None
        self.readable = False

    @property
    def root(self):
        """The project folder."""
        return os.path.dirname(os.path.dirname(self.folder))

    @classmethod
    def load(cls, folder):
        proposal = cls(folder)
        proposal.reload()
        return proposal

    def reload(self):
        data = _read_json(os.path.join(self.folder, INFO_FILE))
        self.readable = data is not None
        data = data or {}
        self.title = str(data.get("title", ""))
        self.message = str(data.get("message", ""))
        self.user = str(data.get("user", "?"))
        self.host = str(data.get("host", "?"))
        self.created = str(data.get("created", ""))
        self.updated = str(data.get("updated", self.created))
        self.files = [ProposalFile.from_json(f) for f in data.get("files") or [] if isinstance(f, dict)]
        self.decision = _read_json(os.path.join(self.folder, DECISION_FILE))
        return self

    def save(self):
        """Rewrite proposal.json (the author's CoBench only)."""
        self.updated = now_iso()
        _write_json(os.path.join(self.folder, INFO_FILE), {
            "format": FORMAT, "id": self.id, "title": self.title, "message": self.message,
            "user": self.user, "host": self.host, "created": self.created, "updated": self.updated,
            "files": [f.to_json() for f in self.files]})

    # -- state ---------------------------------------------------------------
    @property
    def status(self):
        if self.decision is not None:
            status = str(self.decision.get("status", ""))
            if status in CLOSED:
                return status
        return OPEN

    @property
    def is_open(self):
        return self.status == OPEN

    def is_author(self, identity):
        return identity.same_as(self.user, self.host)

    def closed_by(self):
        return str((self.decision or {}).get("user", "?"))

    # -- paths ---------------------------------------------------------------
    def part_path(self, item):
        return os.path.normpath(os.path.join(self.root, item.part))

    def stored_path(self, item):
        return os.path.normpath(os.path.join(self.folder, item.stored))

    def previous_path(self, item):
        return os.path.normpath(os.path.join(self.folder, previous_name(item.part)))

    def file_for(self, path):
        """The ProposalFile whose proposed copy (or original part) is ``path``."""
        target = _norm(path)
        for item in self.files:
            if target in (_norm(self.stored_path(item)), _norm(self.part_path(item))):
                return item
        return None

    def to_stored(self):
        """{original part: proposed copy} for every part of the proposal."""
        return {_norm(self.part_path(f)): self.stored_path(f) for f in self.files}

    def to_parts(self):
        return {_norm(self.stored_path(f)): self.part_path(f) for f in self.files}

    # -- comments --------------------------------------------------------------
    def comments(self):
        found = []
        folder = os.path.join(self.folder, COMMENTS_DIR)
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            names = []
        for name in names:
            if not name.endswith(".json"):
                continue
            data = _read_json(os.path.join(folder, name))
            if data is None:
                continue
            found.append(Comment(str(data.get("user", "?")), str(data.get("host", "?")),
                                 str(data.get("date", "")), str(data.get("text", "")),
                                 str(data.get("kind", "comment")), os.path.join(folder, name)))
        if self.decision is not None:
            found.append(Comment(self.closed_by(), str(self.decision.get("host", "?")),
                                 str(self.decision.get("date", "")), str(self.decision.get("comment", "")),
                                 self.status))
        found.sort(key=lambda c: c.date)
        return found


def list_proposals(root, include_closed=True):
    """The proposals of the project, newest first."""
    found = []
    folder = folder_of(root)
    try:
        names = os.listdir(folder)
    except OSError:
        return found
    for name in names:
        path = os.path.join(folder, name)
        if not os.path.isfile(os.path.join(path, INFO_FILE)):
            continue
        proposal = Proposal.load(path)
        if not proposal.readable:
            continue  # still arriving through the sync
        if include_closed or proposal.is_open:
            found.append(proposal)
    found.sort(key=lambda p: (p.created, p.id), reverse=True)
    return found


def owner_of(root, path):
    """The proposal holding the proposed copy ``path``, or None."""
    if not is_proposal_path(root, path):
        return None
    rel = os.path.relpath(os.path.abspath(path), folder_of(root))
    first = rel.replace("\\", "/").split("/", 1)[0]
    folder = os.path.join(folder_of(root), first)
    if not os.path.isfile(os.path.join(folder, INFO_FILE)):
        return None
    return Proposal.load(folder)


# -- versions -------------------------------------------------------------------

def base_of(path):
    """The version of the part a proposal starts from: its sha1, size and last saver."""
    base = {"sha1": stamps.fingerprint(path), "size": os.path.getsize(path)}
    stamp = stamps.Stamp.read(path)
    if stamp is not None and stamp.sha1 == base["sha1"]:
        base["saved_by"], base["saved_at"] = stamp.user, stamp.saved
    return base


def _copy_in(proposal, parts, bases):
    """Copy parts into the proposal and point all links between proposed parts to the copies."""
    root = proposal.root
    known = {_norm(proposal.part_path(f)) for f in proposal.files}
    added = []
    for path in parts:
        if _norm(path) in known:
            continue
        rel = os.path.relpath(os.path.abspath(path), root).replace("\\", "/")
        if rel.startswith("..") or is_proposal_path(root, path):
            raise ProposalError("%s is not a part of the project" % path)
        base = (bases or {}).get(path) or base_of(path)
        item = ProposalFile(rel, base=base)
        proposal.files.append(item)
        known.add(_norm(path))
        added.append(item)
    mapping = proposal.to_stored()
    for item in added:
        relocate(proposal.part_path(item), proposal.stored_path(item), mapping)
    # Proposed parts already there may link to a part just added: point them to its copy.
    for item in proposal.files:
        if item in added:
            continue
        stored = proposal.stored_path(item)
        if os.path.exists(stored):
            locks.set_read_only(stored, False)
            relocate(stored, stored, mapping)
    return added


def create(root, identity, parts, title, message="", bases=None):
    """A new open proposal holding a copy of each part.  Returns the Proposal.

    ``bases`` ({part path: {"sha1", "size", ...}}) gives the version each part
    is made from; by default the file on this computer.  The caller checks
    beforehand that this copy is the latest version.
    """
    if not parts:
        raise ProposalError("no part")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = os.path.join(folder_of(root), "%s-%s-%s" % (stamp, _slug(identity.user), uuid.uuid4().hex[:4]))
    os.makedirs(folder)
    proposal = Proposal(folder)
    proposal.title = title.strip()
    proposal.message = message.strip()
    proposal.user, proposal.host = identity.user, identity.host
    proposal.created = now_iso()
    try:
        _copy_in(proposal, parts, bases)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    proposal.save()
    return proposal


def add_parts(proposal, identity, parts, bases=None):
    """Add parts to an open proposal of mine.  Returns the new ProposalFiles."""
    proposal.reload()
    _check_author(proposal, identity)
    added = _copy_in(proposal, parts, bases)
    proposal.save()
    return added


def remove_part(proposal, identity, item):
    """Take a part out of an open proposal of mine (its copy is deleted)."""
    proposal.reload()
    _check_author(proposal, identity)
    proposal.files = [f for f in proposal.files if f.part != item.part]
    try:
        locks.set_read_only(proposal.stored_path(item), False)
        os.remove(proposal.stored_path(item))
    except FileNotFoundError:
        pass
    mapping = {_norm(proposal.stored_path(item)): proposal.part_path(item)}
    for other in proposal.files:  # links to the removed copy go back to the part
        stored = proposal.stored_path(other)
        if os.path.exists(stored):
            locks.set_read_only(stored, False)
            relocate(stored, stored, mapping)
    proposal.save()


def edit(proposal, identity, title=None, message=None):
    proposal.reload()
    _check_author(proposal, identity)
    if title is not None:
        proposal.title = title.strip()
    if message is not None:
        proposal.message = message.strip()
    proposal.save()


def _check_author(proposal, identity):
    if not proposal.is_open:
        raise ProposalError("closed")
    if not proposal.is_author(identity):
        raise ProposalError("not the author")


def comment(proposal, identity, text, kind="comment"):
    """Add a comment (a new file: never conflicts with someone else's)."""
    text = (text or "").strip()
    if not text:
        return None
    moment = datetime.datetime.now(datetime.timezone.utc)
    name = "%s-%s-%s.json" % (moment.strftime("%Y%m%dT%H%M%S"), _slug(identity.user), uuid.uuid4().hex[:4])
    path = os.path.join(proposal.folder, COMMENTS_DIR, name)
    _write_json(path, {"format": FORMAT, "user": identity.user, "host": identity.host,
                       "date": now_iso(), "text": text, "kind": kind})
    return path


def _decide(proposal, identity, status, text="", extra=None):
    data = {"format": FORMAT, "status": status, "user": identity.user, "host": identity.host,
            "date": now_iso(), "comment": (text or "").strip()}
    data.update(extra or {})
    try:
        _write_json(os.path.join(proposal.folder, DECISION_FILE), data, exclusive=True)
    except FileExistsError:
        proposal.reload()
        raise ProposalError("closed")
    proposal.decision = data


def refuse(proposal, identity, text=""):
    """Close the proposal without touching the parts."""
    proposal.reload()
    if not proposal.is_open:
        raise ProposalError("closed")
    _decide(proposal, identity, REFUSED, text)


def withdraw(proposal, identity, text=""):
    """The author gives up the proposal."""
    proposal.reload()
    _check_author(proposal, identity)
    _decide(proposal, identity, WITHDRAWN, text)


# -- integration ------------------------------------------------------------------

class Conflict:
    def __init__(self, item, reason, detail=""):
        self.item, self.reason, self.detail = item, reason, detail

    @property
    def part(self):
        return self.item.part

    def __repr__(self):
        return "Conflict(%s, %s)" % (self.item.part, self.reason)


def check(proposal, latest=None, lock_manager=None):
    """Why each part cannot be integrated now ([] when all can).

    ``latest(part_path)`` may return the sha1 of the last saved version known
    elsewhere (the Supabase versions table); a part whose last version is not
    the base is in conflict even if that file has not arrived here yet.
    """
    conflicts = []
    for item in proposal.files:
        part, stored = proposal.part_path(item), proposal.stored_path(item)
        try:
            with zipfile.ZipFile(stored) as archive:
                archive.getinfo("Document.xml")
        except (OSError, KeyError, zipfile.BadZipFile):
            conflicts.append(Conflict(item, UNREADABLE))
            continue
        if not os.path.exists(part):
            conflicts.append(Conflict(item, MISSING))
            continue
        base = item.base.get("sha1", "")
        known = latest(part) if latest else None
        if known and known != base:
            conflicts.append(Conflict(item, CHANGED, known))
            continue
        try:
            current = stamps.fingerprint(part)
        except OSError:
            conflicts.append(Conflict(item, MISSING))
            continue
        if current != base:
            conflicts.append(Conflict(item, NOT_ARRIVED if known else CHANGED, current))
            continue
        if lock_manager is not None:
            state = lock_manager.state(part)
            if state.status == locks.OTHER:
                conflicts.append(Conflict(item, LOCKED, state.info.user if state.info else "?"))
    return conflicts


class Result:
    def __init__(self):
        self.done = False
        self.conflicts = []
        self.parts = []       # part paths replaced
        self.warnings = []    # versions that could not be recorded (part kept locked)

    def __bool__(self):
        return self.done


def _record_version(lock_manager, path, identity, proposal):
    if getattr(lock_manager, "store", "files") == "supabase":
        lock_manager.set_version(path, stamps.fingerprint(path), os.path.getsize(path))
    else:
        stamps.write(path, identity, extra={"proposal": proposal.id, "author": proposal.user})


def integrate(proposal, identity, lock_manager, text="", latest=None):
    """Replace the parts by their proposed versions.  Returns a Result.

    Nothing changes when a part is in conflict.  Otherwise each part is
    locked, the base version is checked once more, the original is kept in
    ``previous/``, the part is replaced (links pointed back to the project),
    a new version is recorded in the name of ``identity`` citing the author,
    the locks taken are released and the proposal is closed.  Parts that
    were already locked by ``identity`` stay locked.
    """
    result = Result()
    proposal.reload()
    if not proposal.is_open:
        raise ProposalError("closed")
    result.conflicts = check(proposal, latest, lock_manager)
    if result.conflicts:
        return result
    taken, kept = [], set()
    try:
        for item in proposal.files:
            part = proposal.part_path(item)
            if lock_manager.state(part).status == locks.MINE:
                continue
            state = lock_manager.acquire(part)
            if state.status != locks.MINE:
                result.conflicts = [Conflict(item, LOCKED, state.info.user if state.info else "?")]
                return result
            taken.append(part)
        result.conflicts = check(proposal, latest)  # saved by someone just before our locks?
        if result.conflicts:
            return result
        to_parts = proposal.to_parts()
        for item in proposal.files:
            part = proposal.part_path(item)
            previous = proposal.previous_path(item)
            os.makedirs(os.path.dirname(previous), exist_ok=True)
            shutil.copy2(part, previous)
            locks.set_read_only(part, False)
            relocate(proposal.stored_path(item), part, to_parts)
            result.parts.append(part)
        files = []
        for item in proposal.files:
            part = proposal.part_path(item)
            try:
                _record_version(lock_manager, part, identity, proposal)
            except Exception as exc:  # the database refused: keep the part locked, like a save
                result.warnings.append((part, str(exc)))
                kept.add(_norm(part))
            files.append({"part": item.part, "base": item.base.get("sha1", ""),
                          "sha1": stamps.fingerprint(part)})
        _decide(proposal, identity, INTEGRATED, text, {"author": proposal.user, "files": files})
        result.done = True
        return result
    finally:
        for part in taken:
            if _norm(part) not in kept:
                try:
                    lock_manager.release(part)
                except Exception:
                    pass


def proposed_part(root, path):
    """(proposal, item) when ``path`` is a proposed copy, else (None, None)."""
    proposal = owner_of(root, path)
    if proposal is None:
        return None, None
    return proposal, proposal.file_for(path)


def open_for(root, part_path):
    """Open proposals that change this part."""
    target = _norm(part_path)
    return [p for p in list_proposals(root, include_closed=False)
            if any(_norm(p.part_path(f)) == target for f in p.files)]
