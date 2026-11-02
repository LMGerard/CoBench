# SPDX-License-Identifier: LGPL-2.1-or-later
"""Locks shown inside assemblies.

Any open document of the project that links to other parts of the project is
treated as an assembly (App::Link, the built-in Assembly workbench, A2plus
links made with App::Link...).  Over each linked part CoBench draws a
coloured box: red while someone else edits the file, green while you do.
Nothing is written into the document: the boxes live only in the 3D view.

Clicking a part shows its file in the CoBench panel; double-clicking it in the
3D view opens that file read-only; the padlock (or "Edit part") locks it.
"""

import os
import time

import FreeCAD as App
import FreeCADGui as Gui

from ..core import locks
from ..i18n import tr
from . import prefs
from .qt import QtWidgets

try:
    from pivy import coin
except ImportError:  # outside FreeCAD (tests)
    coin = None

BOX_COLORS = {
    locks.MINE: (0.18, 0.63, 0.26),
    locks.OTHER: (0.82, 0.20, 0.17),
    locks.ORPHAN: (0.90, 0.55, 0.08),
}


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def linked_file(obj):
    """File of the object an App::Link points to, following links inside the same file."""
    seen = set()
    while obj is not None and id(obj) not in seen:
        seen.add(id(obj))
        target = getattr(obj, "LinkedObject", None)
        if isinstance(target, tuple):  # (object, subname)
            target = target[0]
        if target is None:
            return None
        if target.Document is not obj.Document:
            return target.Document.FileName or None
        obj = target
    return None


def part_under(doc, root_name, subname, project_contains):
    """Part file designated by a click on ``root_name`` + ``subname``.

    Walks the object path from the top and returns the first link leading to
    another file of the project, so a click on a face of a body inside a
    sub-assembly designates the sub-assembly's file when the click path goes
    through it, else the part itself.
    """
    root = doc.getObject(root_name) if doc is not None else None
    if root is None:
        return None
    try:
        chain = root.getSubObjectList(subname or "")
    except Exception:
        chain = [root]
    own = _norm(doc.FileName) if doc.FileName else None
    for obj in chain:
        path = linked_file(obj)
        if path and _norm(path) != own and project_contains(path):
            return path
        if obj.Document is not doc and obj.Document.FileName and project_contains(obj.Document.FileName):
            return obj.Document.FileName
    return None


def assembly_links(doc, project_contains):
    """[(link object, global bound box, part file)] for every project link."""
    found = []
    own = _norm(doc.FileName) if doc.FileName else None
    for obj in doc.Objects:
        if not hasattr(obj, "LinkedObject"):
            continue
        path = linked_file(obj)
        if not path or _norm(path) == own or not project_contains(path):
            continue
        box = _global_bound_box(obj)
        if box is not None and box.isValid():
            found.append((obj, box, path))
    return found


def _global_bound_box(obj):
    import Part
    try:
        parents = obj.Parents
    except Exception:
        parents = []
    try:
        if parents:
            root, sub = parents[0]
            return Part.getShape(root, sub, needSubElement=False).BoundBox
        return Part.getShape(obj).BoundBox
    except Exception:
        return None


class Overlay:
    """Coloured boxes added to the scene graph of one document's 3D views."""

    def __init__(self, doc):
        self.doc_name = doc.Name
        self.root = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE  # clicks go through to the parts
        self.root.addChild(pick)
        self.content = coin.SoSeparator()
        self.root.addChild(self.content)
        self.signature = None
        self.graphs = []

    def attach(self):
        gdoc = Gui.getDocument(self.doc_name)
        try:
            views = gdoc.mdiViewsOfType("Gui::View3DInventor")
        except Exception:
            views = []
        current = []
        for view in views:
            try:
                graph = view.getSceneGraph()
            except Exception:
                continue
            current.append(graph)
            if graph.findChild(self.root) < 0:
                graph.addChild(self.root)
        self.graphs = current

    def detach(self):
        for graph in self.graphs:
            try:
                if graph.findChild(self.root) >= 0:
                    graph.removeChild(self.root)
            except Exception:
                pass
        self.graphs = []

    def update(self, entries, force=False):
        """entries: [(bound box, status, label)]"""
        signature = [(round(b.XMin, 3), round(b.YMin, 3), round(b.ZMin, 3),
                      round(b.XMax, 3), round(b.YMax, 3), round(b.ZMax, 3), s, l)
                     for b, s, l in entries]
        if signature == self.signature and not force:
            return
        self.signature = signature
        self.content.removeAllChildren()
        for box, status, label in entries:
            self.content.addChild(_box_node(box, BOX_COLORS[status], label))


def _box_node(box, color, label):
    margin = 0.5 + 0.01 * max(box.XLength, box.YLength, box.ZLength)
    sep = coin.SoSeparator()
    move = coin.SoTranslation()
    move.translation.setValue(box.Center.x, box.Center.y, box.Center.z)
    sep.addChild(move)
    size = (box.XLength + 2 * margin, box.YLength + 2 * margin, box.ZLength + 2 * margin)

    filled = coin.SoSeparator()
    material = coin.SoMaterial()
    material.diffuseColor.setValue(*color)
    material.emissiveColor.setValue(*[c * 0.4 for c in color])
    material.transparency.setValue(0.78)
    filled.addChild(material)
    filled.addChild(_cube(size))
    sep.addChild(filled)

    edges = coin.SoSeparator()
    style = coin.SoDrawStyle()
    style.style = coin.SoDrawStyle.LINES
    style.lineWidth = 2
    edges.addChild(style)
    line_color = coin.SoBaseColor()
    line_color.rgb.setValue(*color)
    edges.addChild(line_color)
    edges.addChild(_cube(size))
    sep.addChild(edges)

    text = coin.SoSeparator()
    up = coin.SoTranslation()
    up.translation.setValue(0, 0, size[2] / 2 + margin)
    text.addChild(up)
    text_color = coin.SoBaseColor()
    text_color.rgb.setValue(*color)
    text.addChild(text_color)
    font = coin.SoFont()
    font.size = 14
    text.addChild(font)
    words = coin.SoText2()
    words.string = label
    words.justification = coin.SoText2.CENTER
    text.addChild(words)
    sep.addChild(text)
    return sep


def _cube(size):
    cube = coin.SoCube()
    cube.width, cube.height, cube.depth = size
    return cube


class AssemblyWatcher:
    """Keeps the overlays of all open project assemblies up to date."""

    def __init__(self, session, panel_getter):
        self.session = session
        self.panel_getter = panel_getter
        self.overlays = {}      # document name -> Overlay
        self.callbacks = {}     # document name -> [(view, callback)]
        self.dirty = set()
        self.link_cache = {}    # document name -> (object count, links)
        self.last_click = (0.0, None, None)
        session.listeners.append(self.refresh)
        session.recompute_listeners.append(self._recomputed)
        Gui.Selection.addObserver(self)

    def _contains(self, path):
        return self.session.managed(path)

    def _recomputed(self, doc):
        self.dirty.add(doc.Name)

    def refresh(self):
        if coin is None:
            return
        documents = App.listDocuments()
        for name in list(self.overlays):
            if name not in documents:
                self.overlays.pop(name).detach()
                self.callbacks.pop(name, None)
        for name in list(self.link_cache):
            if name not in documents:
                self.link_cache.pop(name)
        if not prefs.show_overlay():
            for overlay in self.overlays.values():
                overlay.detach()
            self.overlays.clear()
            return
        for name, doc in documents.items():
            if not doc.FileName or not self._contains(doc.FileName):
                continue
            cached = self.link_cache.get(name)
            key = len(doc.Objects)
            if cached is None or cached[0] != key or name in self.dirty:
                cached = self.link_cache[name] = (key, assembly_links(doc, self._contains))
            links = cached[1]
            if not links:
                if name in self.overlays:
                    self.overlays.pop(name).detach()
                continue
            overlay = self.overlays.get(name)
            if overlay is None:
                overlay = self.overlays[name] = Overlay(doc)
            overlay.attach()
            self._watch_clicks(doc)
            entries = []
            for _obj, box, path in links:
                state = self.session.locks.state(path)
                if state.status in BOX_COLORS:
                    if state.status == locks.MINE:
                        label = tr("you")
                    else:
                        label = state.info.user if state.info else "?"
                    entries.append((box, state.status, label))
            overlay.update(entries, force=name in self.dirty)
            self.dirty.discard(name)

    # -- clicks ----------------------------------------------------------------
    def _watch_clicks(self, doc):
        if doc.Name in self.callbacks:
            return
        gdoc = Gui.getDocument(doc.Name)
        hooks = []
        try:
            views = gdoc.mdiViewsOfType("Gui::View3DInventor")
        except Exception:
            views = []
        for view in views:
            callback = self._make_click_handler(view, doc.Name)
            try:
                view.addEventCallback("SoMouseButtonEvent", callback)
                hooks.append((view, callback))
            except Exception:
                pass
        self.callbacks[doc.Name] = hooks

    def _make_click_handler(self, view, doc_name):
        def on_click(event):
            if event.get("Button") != "BUTTON1" or event.get("State") != "DOWN":
                return
            position = tuple(event.get("Position", (0, 0)))
            now = time.monotonic()
            last_time, last_pos, last_doc = self.last_click
            self.last_click = (now, position, doc_name)
            interval = QtWidgets.QApplication.doubleClickInterval() / 1000.0
            if (last_doc == doc_name and last_pos is not None and now - last_time <= interval
                    and abs(position[0] - last_pos[0]) <= 4 and abs(position[1] - last_pos[1]) <= 4):
                self.last_click = (0.0, None, None)
                info = view.getObjectInfo(position)
                if info:
                    path = self._path_from_info(info)
                    if path:
                        # Leave the coin callback before opening dialogs.
                        from .session import later
                        later(lambda: self.session.view(path))
        return on_click

    def _path_from_info(self, info):
        doc = App.getDocument(info.get("Document")) if info.get("Document") else None
        root = info.get("ParentObject") or info.get("Object")
        sub = info.get("SubName", "") if info.get("ParentObject") else ""
        return part_under(doc, root, sub, self._contains)

    # -- selection observer (FreeCAD calls these by name) ----------------------
    def addSelection(self, doc_name, obj_name, sub, _point):
        try:
            doc = App.getDocument(doc_name)
        except Exception:
            return
        if not doc.FileName or not self._contains(doc.FileName):
            return
        path = part_under(doc, obj_name, sub, self._contains)
        panel = self.panel_getter()
        if path and panel is not None:
            panel.select_path(path)


def selected_part(session):
    """Part file designated by the current selection, else the active document."""
    for sel in Gui.Selection.getSelectionEx("", 0):
        doc = sel.Document
        subs = sel.SubElementNames or [""]
        for sub in subs:
            path = part_under(doc, sel.ObjectName, sub, session.managed)
            if path:
                return path
    doc = App.ActiveDocument
    if doc is not None and doc.FileName and session.managed(doc.FileName):
        return doc.FileName
    return None
