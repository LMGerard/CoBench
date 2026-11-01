# SPDX-License-Identifier: LGPL-2.1-or-later
"""Lock files placed next to each part.

``Plate.FCStd`` is locked by the file ``Plate.FCStd.cobench-lock`` in the same
folder.  The lock is a small JSON document saying who holds it, on which
machine and since when.  Any folder works: a local disk, a network share, or a
folder synchronised by Nextcloud, Dropbox, Google Drive, Syncthing...

The name deliberately does not start with a dot or a tilde: synchronisation
clients skip hidden files and ``~`` / ``.~lock`` patterns by default, and the
lock must travel with the part.

Known limit: with a synchronised folder, two people who open the same part
within the synchronisation delay will not see each other's lock.  Conflict
copies created by the sync client are reported by :func:`find_conflicts`.
"""

import datetime
import json
import os
import stat
import sys

LOCK_SUFFIX = ".cobench-lock"
FORMAT = 1

FREE = "free"            # nobody holds the part
MINE = "mine"            # held by this FreeCAD session
OTHER = "other"          # held by someone else (or by me in another FreeCAD)
ORPHAN = "orphan"        # held by me on this machine, but that FreeCAD is gone

CONFLICT_WORDS = ("conflict", "conflit", "konflikt", "conflicto", "conflitto")


def lock_path(part_path):
    return part_path + LOCK_SUFFIX


def is_lock_file(path):
    return path.endswith(LOCK_SUFFIX)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(text):
    try:
        value = datetime.datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value


def pid_alive(pid):
    """True if a process with this id runs on this machine."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform.startswith("win"):
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class LockInfo:
    """Content of a lock file."""

    def __init__(self, user="?", host="?", pid=0, since="", session="", app="", path=""):
        self.user = user
        self.host = host
        self.pid = pid
        self.since = since
        self.session = session
        self.app = app
        self.path = path

    @classmethod
    def read(cls, path):
        """The lock at ``path`` or None.  An unreadable lock still counts."""
        try:
            with open(path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return cls(path=path)  # half-synchronised or corrupt: still a lock
        if not isinstance(data, dict):
            return cls(path=path)
        pid = data.get("pid", 0)
        return cls(
            user=str(data.get("user", "?")),
            host=str(data.get("host", "?")),
            pid=pid if isinstance(pid, int) else 0,
            since=str(data.get("since", "")),
            session=str(data.get("session", "")),
            app=str(data.get("app", "")),
            path=path,
        )

    def to_json(self):
        return json.dumps(
            {
                "format": FORMAT,
                "user": self.user,
                "host": self.host,
                "pid": self.pid,
                "since": self.since,
                "session": self.session,
                "app": self.app,
            },
            indent=1,
        )

    def since_datetime(self):
        return parse_iso(self.since)

    def age_seconds(self, now=None):
        start = self.since_datetime()
        if start is None:
            return None
        now = now or datetime.datetime.now(datetime.timezone.utc)
        return max(0.0, (now - start).total_seconds())


class LockState:
    """Status of one part, as seen from this FreeCAD session."""

    def __init__(self, status, info=None):
        self.status = status
        self.info = info

    def __repr__(self):
        return "LockState(%s, %s)" % (self.status, getattr(self.info, "user", None))


class LockManager:
    """Takes and releases locks for one FreeCAD session."""

    def __init__(self, identity, session, app="FreeCAD"):
        self.identity = identity
        self.session = session
        self.app = app
        self.held = set()  # normalised part paths locked by this session

    # -- queries -----------------------------------------------------------
    def state(self, part_path):
        info = LockInfo.read(lock_path(part_path))
        if info is None:
            return LockState(FREE)
        return LockState(self._classify(info), info)

    def _classify(self, info):
        if not self.identity.same_as(info.user, info.host):
            return OTHER
        if info.session == self.session:
            return MINE
        # Same person, same machine, another FreeCAD run.
        if info.pid and info.pid != os.getpid() and pid_alive(info.pid):
            return OTHER  # another FreeCAD window of mine has it open
        return ORPHAN

    # -- changes -----------------------------------------------------------
    def _new_info(self):
        return LockInfo(
            user=self.identity.user,
            host=self.identity.host,
            pid=os.getpid(),
            since=now_iso(),
            session=self.session,
            app=self.app,
        )

    def acquire(self, part_path):
        """Lock the part.  Returns the resulting :class:`LockState`.

        The part is ours when the returned status is MINE.  An orphan lock
        left by a crashed FreeCAD of the same user on the same machine is
        taken over silently.
        """
        path = lock_path(part_path)
        info = self._new_info()
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            current = self.state(part_path)
            if current.status == MINE:
                self.held.add(_norm(part_path))
                return current
            if current.status == ORPHAN:
                return self.force(part_path)
            return current
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(info.to_json())
            stream.flush()
            os.fsync(stream.fileno())
        info.path = path
        self.held.add(_norm(part_path))
        return LockState(MINE, info)

    def force(self, part_path):
        """Take the lock whoever holds it (the caller has warned the user)."""
        path = lock_path(part_path)
        info = self._new_info()
        tmp = path + ".tmp-%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as stream:
            stream.write(info.to_json())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        info.path = path
        self.held.add(_norm(part_path))
        return LockState(MINE, info)

    def release(self, part_path):
        """Remove our lock.  Never removes somebody else's lock."""
        self.held.discard(_norm(part_path))
        current = self.state(part_path)
        if current.status not in (MINE, ORPHAN):
            return False
        try:
            os.remove(lock_path(part_path))
        except FileNotFoundError:
            pass
        return True

    def release_all(self):
        for part in list(self.held):
            try:
                self.release(part)
            except OSError:
                pass

    def holds(self, part_path):
        return _norm(part_path) in self.held


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def find_conflicts(part_path):
    """Conflict copies made by a sync client for the part or its lock."""
    folder, name = os.path.split(part_path)
    stem = os.path.splitext(name)[0].lower()
    found = []
    try:
        entries = os.listdir(folder or ".")
    except OSError:
        return found
    for entry in entries:
        low = entry.lower()
        if low == name.lower() or not low.startswith(stem):
            continue
        if any(word in low for word in CONFLICT_WORDS):
            found.append(os.path.join(folder, entry))
    return sorted(found)


def set_read_only(path, read_only):
    """Make the part read-only on this computer while someone else edits it.

    A save over a read-only file then fails instead of silently overwriting
    the other person's work.  Returns True when the mode changed.
    """
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    writable = bool(mode & stat.S_IWUSR)
    if read_only and writable:
        os.chmod(path, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        return True
    if not read_only and not writable:
        os.chmod(path, mode | stat.S_IWUSR)
        return True
    return False


def is_read_only(path):
    try:
        return not (os.stat(path).st_mode & stat.S_IWUSR)
    except OSError:
        return False
