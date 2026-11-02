# SPDX-License-Identifier: LGPL-2.1-or-later
"""Which version of a part is the latest one?

On each save, ``Plate.FCStd.cobench-stamp`` records who saved the part and
the fingerprint of the file.  It travels with the part through the same
sync, so when the part is taken, a local copy whose fingerprint differs is
an older version that has not arrived yet.
"""

import hashlib
import json
import os

from .locks import now_iso, parse_iso

STAMP_SUFFIX = ".cobench-stamp"


def stamp_path(part_path):
    return part_path + STAMP_SUFFIX


def fingerprint(path):
    digest = hashlib.sha1()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class Stamp:
    def __init__(self, user="?", host="?", saved="", size=0, sha1=""):
        self.user, self.host, self.saved, self.size, self.sha1 = user, host, saved, size, sha1

    @classmethod
    def read(cls, part_path):
        try:
            with open(stamp_path(part_path), "r", encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        return cls(str(data.get("user", "?")), str(data.get("host", "?")), str(data.get("saved", "")),
                   int(data.get("size", 0) or 0), str(data.get("sha1", "")))


def write(part_path, identity):
    data = {"format": 1, "user": identity.user, "host": identity.host, "saved": now_iso(),
            "size": os.path.getsize(part_path), "sha1": fingerprint(part_path)}
    path = stamp_path(part_path)
    tmp = path + ".tmp-%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def remove(part_path):
    try:
        os.remove(stamp_path(part_path))
    except OSError:
        pass


def newer_elsewhere(part_path):
    """The stamp when the local copy is older than the last saved version, else None.

    A local file changed after the stamp was written (saved without CoBench)
    is not reported.
    """
    stamp = Stamp.read(part_path)
    if stamp is None or not stamp.sha1:
        return None
    try:
        size = os.path.getsize(part_path)
        mtime = os.path.getmtime(part_path)
    except OSError:
        return None
    if size == stamp.size and fingerprint(part_path) == stamp.sha1:
        return None
    saved = parse_iso(stamp.saved)
    if saved is not None and mtime > saved.timestamp() + 2:
        return None  # the local file is the more recent one
    return stamp
