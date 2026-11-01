# SPDX-License-Identifier: LGPL-2.1-or-later
"""A CoBench project is any folder holding .FCStd files.

An optional ``cobench.json`` at the root of the folder keeps the project name
and the central assembly.  Everything else is read from the files themselves,
so the folder stays usable without CoBench.
"""

import json
import os

from . import fcstd, locks

PROJECT_FILE = "cobench.json"
PART_EXTENSION = ".fcstd"


class Project:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.name = os.path.basename(self.root.rstrip("\\/")) or self.root
        self.assembly = ""  # path relative to root, "/" separators
        self.load()

    # -- project file ------------------------------------------------------
    @property
    def project_file(self):
        return os.path.join(self.root, PROJECT_FILE)

    def load(self):
        try:
            with open(self.project_file, "r", encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, ValueError):
            return False
        if isinstance(data, dict):
            self.name = str(data.get("name") or self.name)
            self.assembly = str(data.get("assembly") or "")
        return True

    def save(self):
        data = {"format": 1, "name": self.name, "assembly": self.assembly}
        tmp = self.project_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=1, ensure_ascii=False)
        os.replace(tmp, self.project_file)

    # -- paths -------------------------------------------------------------
    def rel(self, path):
        return os.path.relpath(os.path.abspath(path), self.root).replace("\\", "/")

    def abs(self, rel_path):
        return os.path.normpath(os.path.join(self.root, rel_path))

    def contains(self, path):
        try:
            rel = os.path.relpath(os.path.abspath(path), self.root)
        except ValueError:  # other drive on Windows
            return False
        return not rel.startswith("..") and not os.path.isabs(rel)

    def assembly_path(self):
        return self.abs(self.assembly) if self.assembly else ""

    def set_assembly(self, path):
        self.assembly = self.rel(path) if path else ""
        self.save()

    # -- content -----------------------------------------------------------
    def parts(self):
        """Absolute paths of every .FCStd in the folder, sub-folders included.

        Hidden folders (starting with a dot) are skipped, as are conflict
        copies made by synchronisation clients.
        """
        found = []
        for folder, dirs, files in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for name in files:
                if not name.lower().endswith(PART_EXTENSION):
                    continue
                if any(word in name.lower() for word in locks.CONFLICT_WORDS):
                    continue
                found.append(os.path.join(folder, name))
        found.sort(key=lambda p: self.rel(p).lower())
        return found

    def link_graph(self, parts=None):
        """{part: [parts it links to]} restricted to parts of this project."""
        parts = parts if parts is not None else self.parts()
        known = {os.path.normcase(p): p for p in parts}
        graph = {}
        for part in parts:
            targets = []
            for target in fcstd.read_part(part).links:
                resolved = known.get(os.path.normcase(fcstd.resolve_link(part, target)))
                if resolved and resolved != part and resolved not in targets:
                    targets.append(resolved)
            graph[part] = targets
        return graph

    def used_in(self, graph):
        """{part: [parts that link to it]}"""
        users = {part: [] for part in graph}
        for owner, targets in graph.items():
            for target in targets:
                users.setdefault(target, []).append(owner)
        return users

    def suggest_assembly(self, graph=None):
        """The part linking to the most other parts, if any."""
        graph = graph if graph is not None else self.link_graph()
        best = max(graph.items(), key=lambda item: len(item[1]), default=(None, []))
        return best[0] if best[1] else None


def find_root(path):
    """The nearest folder above ``path`` holding a cobench.json, or None."""
    folder = os.path.abspath(path)
    if os.path.isfile(folder):
        folder = os.path.dirname(folder)
    while True:
        if os.path.isfile(os.path.join(folder, PROJECT_FILE)):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            return None
        folder = parent
