#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Watch the reference copy of CoBench projects and write it into the lock database.

Run it where the files of the project really are, for example on the Nextcloud
server (read-only access to the project folder is enough).  Every few seconds it
writes the fingerprint (sha1, size, date) of every part, and of cobench.json,
into ``cobench_server_files``, plus a heartbeat in ``cobench_projects``.  Each
FreeCAD running CoBench 0.5 or newer compares this with its own copy, so a part
that does not arrive, or does not leave, through the sync is shown in red and
nobody edits a part believing everything works.

Python 3.8+, standard library only.  Settings (environment variables):

  COBENCH_REST         REST address of the database: https://<project>.supabase.co/rest/v1,
                       or http://<host>:3000 for a self-hosted PostgREST
  COBENCH_KEY          Supabase service_role key (stays on the server, never in cobench.json)
  COBENCH_JWT_SECRET   instead of COBENCH_KEY for a self-hosted PostgREST: its JWT secret
  COBENCH_PROJECTS     <project id>=<folder>[;<project id>=<folder>...]
                       (the id is "locking.id" in the project's cobench.json)
  COBENCH_MIN_VERSION  optional: older CoBench versions may not lock parts of these projects
  COBENCH_INTERVAL     seconds between two looks at the folders (default 5)
  COBENCH_HEARTBEAT    seconds between two heartbeats when nothing changes (default 20)

The tables are created by Resources/supabase.sql (its last part).
"""

import base64
import datetime
import hashlib
import hmac
import json
import os
import socket
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

PART_EXTENSION = ".fcstd"
PROJECT_FILE = "cobench.json"
# Same rules as CoBench (core/project.py, core/locks.py): conflict copies are not parts.
CONFLICT_WORDS = ("conflict", "conflit", "konflikt", "conflicto", "conflitto")


def log(text):
    print("%s %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text), flush=True)


def service_token(secret):
    """A JWT with the service_role role, signed for PostgREST."""
    def b64(data):
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64(json.dumps({"role": "service_role", "iss": "cobench-scanner"}).encode())
    signature = hmac.new(secret.encode(), ("%s.%s" % (header, payload)).encode(), hashlib.sha256).digest()
    return "%s.%s.%s" % (header, payload, b64(signature))


class Rest:
    def __init__(self, base, token):
        self.base = base.rstrip("/")
        self.token = token

    def call(self, method, table, query="", body=None, prefer=""):
        address = "%s/%s%s" % (self.base, table, ("?" + query) if query else "")
        headers = {"apikey": self.token, "Authorization": "Bearer " + self.token, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if prefer:
            headers["Prefer"] = prefer
        request = urllib.request.Request(address, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=15) as answer:
                raw = answer.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raise RuntimeError("%s %s: %s %s" % (method, table, error.code, error.read()[:300].decode("utf-8", "replace")))


def quote(value):
    return urllib.parse.quote(str(value), safe="")


def files_of(root):
    """{relative path: absolute path} of the parts and cobench.json, as CoBench sees them."""
    found = {}
    project_file = os.path.join(root, PROJECT_FILE)
    if os.path.isfile(project_file):
        found[PROJECT_FILE] = project_file
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in names:
            lower = name.lower()
            if not lower.endswith(PART_EXTENSION) or any(word in lower for word in CONFLICT_WORDS):
                continue
            path = os.path.join(folder, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            found[unicodedata.normalize("NFC", rel)] = path
    return found


class Project:
    def __init__(self, project_id, root):
        self.id, self.root = project_id, root
        self.cache = {}       # path -> ((size, mtime_ns), sha1)
        self.sent = None      # rel -> row as last written in the database
        self.last_beat = 0.0

    def scan(self):
        rows = {}
        for rel, path in files_of(self.root).items():
            try:
                info = os.stat(path)
                signature = (info.st_size, info.st_mtime_ns)
                cached = self.cache.get(path)
                if not cached or cached[0] != signature:
                    digest = hashlib.sha1()
                    with open(path, "rb") as stream:
                        for block in iter(lambda: stream.read(1 << 20), b""):
                            digest.update(block)
                    cached = (signature, digest.hexdigest())
                    self.cache[path] = cached
                rows[rel] = {"project": self.id, "part": rel, "sha1": cached[1], "size": info.st_size,
                             "mtime": round(info.st_mtime, 3)}
            except OSError:
                continue  # being replaced right now: next time
        for path in list(self.cache):
            if not os.path.exists(path):
                del self.cache[path]
        return rows

    def run_once(self, rest, min_version, heartbeat):
        if not os.path.isdir(self.root):
            raise RuntimeError("folder not found: %s" % self.root)
        if self.sent is None:  # first pass: start from what the database holds
            current = rest.call("GET", "cobench_server_files",
                                "project=eq.%s&select=project,part,sha1,size,mtime" % quote(self.id)) or []
            self.sent = {row["part"]: row for row in current}
        rows = self.scan()
        changed = [row for rel, row in rows.items() if self.sent.get(rel) is None or any(
            self.sent[rel].get(k) != row[k] for k in ("sha1", "size"))]
        removed = [rel for rel in self.sent if rel not in rows]
        if changed:
            rest.call("POST", "cobench_server_files", "on_conflict=project,part", changed,
                      "resolution=merge-duplicates,return=minimal")
        for rel in removed:
            rest.call("DELETE", "cobench_server_files", "project=eq.%s&part=eq.%s" % (quote(self.id), quote(rel)),
                      prefer="return=minimal")
        for row in changed:
            self.sent[row["part"]] = row
        for rel in removed:
            self.sent.pop(rel, None)
        now = time.time()
        if changed or removed or now - self.last_beat >= heartbeat:
            project = {"project": self.id, "scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       "scanner": socket.gethostname()}
            if changed or removed or self.last_beat == 0.0:
                project["files_rev"] = int(now * 1000)
            if min_version is not None:
                project["min_version"] = min_version
            rest.call("POST", "cobench_projects", "on_conflict=project", project,
                      "resolution=merge-duplicates,return=minimal")
            self.last_beat = now
        if changed or removed:
            log("%s: %d changed, %d removed (%d files)" % (self.id, len(changed), len(removed), len(rows)))


def parse_projects(text):
    projects = []
    for item in (text or "").split(";"):
        if "=" in item:
            project_id, folder = item.split("=", 1)
            if project_id.strip() and folder.strip():
                projects.append(Project(project_id.strip(), folder.strip()))
    return projects


def main():
    base = os.environ.get("COBENCH_REST", "")
    secret = os.environ.get("COBENCH_JWT_SECRET", "")
    token = service_token(secret) if secret else os.environ.get("COBENCH_KEY", "")
    projects = parse_projects(os.environ.get("COBENCH_PROJECTS", ""))
    if not base or not token or not projects:
        sys.exit("Set COBENCH_REST, COBENCH_KEY (or COBENCH_JWT_SECRET) and COBENCH_PROJECTS.")
    min_version = os.environ.get("COBENCH_MIN_VERSION")
    interval = float(os.environ.get("COBENCH_INTERVAL", "5"))
    heartbeat = float(os.environ.get("COBENCH_HEARTBEAT", "20"))
    rest = Rest(base, token)
    log("watching %s" % ", ".join("%s=%s" % (p.id, p.root) for p in projects))
    failing = set()
    while True:
        for project in projects:
            try:
                project.run_once(rest, min_version, heartbeat)
                if project.id in failing:
                    failing.discard(project.id)
                    log("%s: working again" % project.id)
            except Exception as exc:  # keep going: the network or the database may come back
                if project.id not in failing:
                    failing.add(project.id)
                    log("%s: %s" % (project.id, exc))
                project.sent = None
        time.sleep(interval)


if __name__ == "__main__":
    main()
