# SPDX-License-Identifier: LGPL-2.1-or-later
"""Asking the holder of a part to release it.

``Plate.FCStd.cobench-request`` next to the part says who wants it.  The
holder's CoBench shows the request; declining writes ``"status": "declined"``
so the requester is told, and whoever sees the request settled deletes it.
"""

import json
import os

from .locks import now_iso

REQUEST_SUFFIX = ".cobench-request"
PENDING = "pending"
DECLINED = "declined"


def request_path(part_path):
    return part_path + REQUEST_SUFFIX


class Request:
    def __init__(self, user="?", host="?", since="", status=PENDING, path=""):
        self.user = user
        self.host = host
        self.since = since
        self.status = status
        self.path = path

    @property
    def key(self):
        return (self.path, self.user, self.host, self.since, self.status)

    @classmethod
    def read(cls, part_path):
        path = request_path(part_path)
        try:
            with open(path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return None  # half-synchronised: look again next time
        if not isinstance(data, dict):
            return None
        return cls(str(data.get("user", "?")), str(data.get("host", "?")),
                   str(data.get("since", "")), str(data.get("status", PENDING)), path)


def write(part_path, identity, status=PENDING, since=None):
    data = {"format": 1, "user": identity.user, "host": identity.host,
            "since": since or now_iso(), "status": status}
    path = request_path(part_path)
    tmp = path + ".tmp-%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    return Request.read(part_path)


def decline(part_path, request):
    """Keep the requester's name, mark the request declined."""
    data = {"format": 1, "user": request.user, "host": request.host,
            "since": request.since, "status": DECLINED}
    path = request_path(part_path)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=1, ensure_ascii=False)


def clear(part_path):
    try:
        os.remove(request_path(part_path))
        return True
    except FileNotFoundError:
        return False
