# SPDX-License-Identifier: LGPL-2.1-or-later
"""Who am I? The name shown to collaborators in lock files."""

import getpass
import os
import socket


def default_user():
    try:
        return getpass.getuser()
    except Exception:  # no login name (some containers)
        return os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"


def host_name():
    try:
        return socket.gethostname() or "unknown"
    except Exception:
        return "unknown"


class Identity:
    """User name + machine name. The pair identifies the owner of a lock."""

    def __init__(self, user=None, host=None):
        self.user = (user or "").strip() or default_user()
        self.host = (host or "").strip() or host_name()

    def same_as(self, user, host):
        return self.user == user and self.host == host

    def __repr__(self):
        return "Identity(%r, %r)" % (self.user, self.host)
