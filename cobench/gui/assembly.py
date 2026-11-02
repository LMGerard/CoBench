# SPDX-License-Identifier: LGPL-2.1-or-later
"""Locks shown inside assemblies.

Any open document of the project that links to other parts of the project is
treated as an assembly (App::Link, the built-in Assembly workbench, A2plus
links made with App::Link...).  Over each linked part CoBench draws a
coloured box: red while someone else edits the file, green while you do.
Nothing is written into the document: the boxes live only in the 3D view.

In an assembly you have not locked yourself, faces and edges are not
selectable: hovering a part lights the whole part up, and clicking it opens a
small menu (open read-only, edit, ask for it, show in the panel).  In an
assembly you have locked, FreeCAD's normal selection is kept: clicking a part
shows its file in the panel, double-clicking opens it read-only.
"""

import os
import time

import FreeCAD as App
import FreeCADGui as Gui

from ..core import locks
from ..i18n import tr
from . import prefs
from .qt import Qt, QtCore, QtGui, QtWidgets

try:
    from pivy import coin
except ImportError:  # outside FreeCAD (tests)
    coin = None

PENDING = "pending"  # my lock, not yet seen by the others (same value as session.PENDING)

BOX_COLORS = {
    PENDING: (0.85, 0.66, 0.05),
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


def link_under(doc, root_name, subname, project_contains):
    """(part file, top object, subname of the part) for a click on ``root_name`` + ``subname``.

    Walks the object path from the top and returns the first link leading to
    another file of the project, so a click on a face of a body inside a
    sub-assembly designates the sub-assembly's file when the click path goes
    through it, else the part itself.  (None, None, None) if nothing matches.
    """
    root = doc.getObject(root_name) if doc is not None else None
    if root is None:
        return None, None, None
    try:
        chain = root.getSubObjectList(subname or "")
    except Exception:
        chain = [root]
    names = [n for n in (subname or "").split(".")]
    own = _norm(doc.FileName) if doc.FileName else None
    for index, obj in enumerate(chain):
        path = linked_file(obj)
        if not (path and _norm(path) != own and project_contains(path)):
            path = None
            if obj.Document is not doc and obj.Document.FileName and project_contains(obj.Document.FileName):
                path = obj.Document.FileName
        if path:
            sub = ".".join(names[:index]) + "." if index else ""
            return path, root, sub
    return None, None, None


def part_under(doc, root_name, subname, project_contains):
    """Part file designated by a click on ``root_name`` + ``subname``."""
    return link_under(doc, root_name, subname, project_contains)[0]


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
        if not _shown(obj):
            continue
        box = _global_bound_box(obj)
        if box is not None and box.isValid():
            found.append((obj, box, path))
    return found


def reference_count(doc, project_contains):
    """Number of links of ``doc`` to other files of the project, shown or hidden."""
    own = _norm(doc.FileName) if doc.FileName else None
    count = 0
    for obj in doc.Objects:
        if not hasattr(obj, "LinkedObject"):
            continue
        path = linked_file(obj)
        if path and _norm(path) != own and project_contains(path):
            count += 1
    return count


def _shown(obj):
    """False if the object or one of the containers above it is hidden."""
    if not getattr(obj, "Visibility", True):
        return False
    try:
        parents = obj.Parents
    except Exception:
        parents = []
    if parents:
        root, sub = parents[0]
        try:
            chain = root.getSubObjectList(sub)
        except Exception:
            chain = [root]
        for item in chain:
            if not getattr(item, "Visibility", True):
                return False
    return True


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
        self.highlight = coin.SoSeparator()
        self.root.addChild(self.highlight)
        self.highlighted = None
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

    def set_highlight(self, key, node):
        """Light up one part (node from _highlight_node), or none with key None."""
        if key == self.highlighted:
            return
        self.highlighted = key
        self.highlight.removeAllChildren()
        if node is not None:
            self.highlight.addChild(node)


def _box_node(box, color, label):
    margin = 0.5 + 0.01 * max(box.XLength, box.YLength, box.ZLength)
    sep = coin.SoSeparator()
    move = coin.SoTranslation()
    move.translation.setValue(box.Center.x, box.Center.y, box.Center.z)
    sep.addChild(move)
    size = (box.XLength + 2 * margin, box.YLength + 2 * margin, box.ZLength + 2 * margin)

    edges = coin.SoSeparator()
    style = coin.SoDrawStyle()
    style.style = coin.SoDrawStyle.LINES
    style.lineWidth = 2
    style.linePattern = 0xF0F0  # dashed
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


def highlight_color():
    """FreeCAD's own pre-selection colour (Preferences > Display > Colors)."""
    try:
        value = App.ParamGet("User parameter:BaseApp/Preferences/View").GetUnsigned("HighlightColor", 0xE1E114FF)
    except Exception:
        value = 0xE1E114FF
    return tuple(((value >> shift) & 0xFF) / 255.0 for shift in (24, 16, 8))


def _highlight_node(root, sub):
    """The whole part, drawn over itself in the highlight colour."""
    import Part
    try:
        shape = Part.getShape(root, sub, needSubElement=False)
    except Exception as exc:
        App.Console.PrintWarning("CoBench: no shape to highlight for %s.%s (%s)\n" % (root.Name, sub, exc))
        return None
    if shape.isNull():
        App.Console.PrintWarning("CoBench: empty shape for %s.%s\n" % (root.Name, sub))
        return None
    box = shape.BoundBox
    tolerance = max(0.01, 0.005 * box.DiagonalLength) if box.isValid() else 0.1
    try:
        points, triangles = shape.tessellate(tolerance)
    except Exception as exc:
        App.Console.PrintWarning("CoBench: cannot mesh %s.%s (%s)\n" % (root.Name, sub, exc))
        return None
    if not triangles:
        return None
    color = highlight_color()
    sep = coin.SoSeparator()
    offset = coin.SoPolygonOffset()  # drawn just in front of the part's own faces
    offset.factor = -1.0
    offset.units = -1.0
    sep.addChild(offset)
    material = coin.SoMaterial()
    material.diffuseColor.setValue(*color)
    material.emissiveColor.setValue(*[c * 0.6 for c in color])
    material.transparency.setValue(0.35)
    sep.addChild(material)
    coords = coin.SoCoordinate3()
    coords.point.setValues(0, len(points), [(p.x, p.y, p.z) for p in points])
    sep.addChild(coords)
    faces = coin.SoIndexedFaceSet()
    index = []
    for a, b, c in triangles:
        index.extend((a, b, c, -1))
    faces.coordIndex.setValues(0, len(index), index)
    sep.addChild(faces)
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
        self.dirty = set()
        self.link_cache = {}    # document name -> ((object count, references), links, references)
        self.highlights = {}    # (document, top object, subname) -> coin node or None
        self.marker = coin.SoInfo() if coin is not None else None  # marks views already hooked
        if self.marker is not None:
            self.marker.ref()
        self.last_click = (0.0, None, None)
        self.press = None       # (document name, position) of the left button press
        self.buttons_down = 0
        self.last_hover = 0.0
        self.menu = None
        self.gate = _Gate(self)
        self.filters = []       # mouse filters of the 3D views (kept alive)
        self.gate_on = False
        session.listeners.append(self.refresh)
        session.recompute_listeners.append(self._recomputed)
        Gui.Selection.addObserver(self)

    def _contains(self, path):
        return self.session.managed(path)

    def _recomputed(self, doc):
        # A part changed or moved: every assembly showing it needs new boxes.
        self.dirty.update(self.overlays)
        self.dirty.add(doc.Name)
        self.highlights.clear()

    def picking(self, doc_name):
        """True for a project file that holds several references to other
        files of the project and that I have not locked (read-only)."""
        if not prefs.assembly_picking() or doc_name not in self.overlays:
            return False
        cached = self.link_cache.get(doc_name)
        if cached is None or cached[2] < 2:
            return False
        try:
            doc = App.getDocument(doc_name)
        except Exception:
            return False
        return not self.session.editable(doc)

    def refresh(self):
        if coin is None:
            return
        documents = App.listDocuments()
        for name in list(self.overlays):
            if name not in documents:
                self.overlays.pop(name).detach()
        for name in list(self.link_cache):
            if name not in documents:
                self.link_cache.pop(name)
        if not prefs.show_overlay() and not prefs.assembly_picking():
            for overlay in self.overlays.values():
                overlay.detach()
            self.overlays.clear()
            self._update_gate()
            return
        for name, doc in documents.items():
            if not doc.FileName or not self._contains(doc.FileName):
                continue
            cached = self.link_cache.get(name)
            # The references count in the key: while a file opens, its links
            # only resolve once the part files they point to are loaded.
            refs = reference_count(doc, self._contains)
            key = (len(doc.Objects), refs)
            if cached is None or cached[0] != key or name in self.dirty:
                cached = self.link_cache[name] = (key, assembly_links(doc, self._contains), refs)
            links = cached[1]
            if not links:
                if name in self.overlays:
                    self.overlays.pop(name).detach()
                continue
            overlay = self.overlays.get(name)
            if overlay is None:
                overlay = self.overlays[name] = Overlay(doc)
            overlay.attach()
            self._watch_views(doc)
            entries = []
            if prefs.show_overlay():
                for _obj, box, path in links:
                    status, label = self._look(path)
                    if status in BOX_COLORS:
                        entries.append((box, status, label))
            overlay.update(entries, force=name in self.dirty)
            if not self.picking(name):
                overlay.set_highlight(None, None)
            self.dirty.discard(name)
        self._update_gate()

    def _look(self, path):
        """(box status, label) of a part."""
        state = self.session.locks.state(path)
        if state.status == locks.MINE:
            return (PENDING if self.session.lock_pending(path) else locks.MINE), tr("you")
        return state.status, (state.info.user if state.info else "?")

    # -- no face or edge selection in picked assemblies --------------------------
    def _update_gate(self):
        """The selection gate refuses selection in picked assemblies.

        It is left alone while a task dialog is open (sketcher, attachment...),
        whose own selection filter must win.
        """
        wanted = any(self.picking(name) for name in self.overlays)
        try:
            busy = bool(Gui.Control.activeDialog())
        except Exception:
            busy = False
        if busy:
            return
        try:
            if wanted:
                # again each time: another one may have replaced it
                _add_gate(self.gate)
                self.gate_on = True
            elif self.gate_on:
                Gui.Selection.removeSelectionGate()
                self.gate_on = False
        except Exception as exc:
            App.Console.PrintWarning("CoBench: %s\n" % exc)

    # -- mouse in the 3D views ---------------------------------------------------
    def _watch_views(self, doc):
        gdoc = Gui.getDocument(doc.Name)
        try:
            views = gdoc.mdiViewsOfType("Gui::View3DInventor")
        except Exception:
            views = []
        for view in views:
            try:
                graph = view.getSceneGraph()
                if graph.findChild(self.marker) >= 0:
                    continue
                graph.addChild(self.marker)
                view.addEventCallback("SoMouseButtonEvent", _guarded(self._make_click_handler(view, doc.Name)))
            except Exception as exc:
                App.Console.PrintWarning("CoBench: %s\n" % exc)
                continue
            viewport = _viewport(view)
            if viewport is None:
                App.Console.PrintWarning("CoBench: no access to the 3D view of %s: parts cannot be picked.\n"
                                         % doc.Label)
                continue
            mouse = _MouseFilter(self, view, doc.Name, viewport)
            viewport.installEventFilter(mouse)
            self.filters.append(mouse)  # keep the Python object alive

    def _make_click_handler(self, view, doc_name):
        def on_click(event):
            button, state = event.get("Button"), event.get("State")
            position = tuple(event.get("Position", (0, 0)))
            if state == "DOWN":
                self.buttons_down += 1
            elif state == "UP":
                self.buttons_down = max(0, self.buttons_down - 1)
            if button != "BUTTON1":
                return
            if self.picking(doc_name):
                return  # handled by _MouseFilter
            if state != "DOWN":
                return
            now = time.monotonic()
            last_time, last_pos, last_doc = self.last_click
            self.last_click = (now, position, doc_name)
            interval = QtWidgets.QApplication.doubleClickInterval() / 1000.0
            if (last_doc == doc_name and last_pos is not None and now - last_time <= interval
                    and abs(position[0] - last_pos[0]) <= 4 and abs(position[1] - last_pos[1]) <= 4):
                self.last_click = (0.0, None, None)
                path = self._path_at(view, position)
                if path:
                    # Leave the coin callback before opening dialogs.
                    from .session import later
                    later(lambda: self.session.view(path))
        return on_click

    def hover(self, view, doc_name, position, viewport):
        """Light up the whole part under the mouse (position in Coin pixels).

        False when no part of the project is there (navigation cube, empty space...).
        """
        overlay = self.overlays.get(doc_name)
        if overlay is None:
            return
        path, root, sub = self._link_at(view, position)
        if path is None:
            overlay.set_highlight(None, None)
            viewport.unsetCursor()
            return False
        key = (doc_name, root.Name, sub)
        if key not in self.highlights:
            self.highlights[key] = _highlight_node(root, sub)
        overlay.set_highlight(key, self.highlights[key])
        status, label = self._look(path)
        name = os.path.splitext(os.path.basename(path))[0]
        text = name if status not in BOX_COLORS else "%s (%s)" % (name, label)
        try:
            Gui.getMainWindow().statusBar().showMessage(text, 3000)
        except Exception:
            pass
        viewport.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
        return True

    def unhover(self, doc_name):
        overlay = self.overlays.get(doc_name)
        if overlay is not None:
            overlay.set_highlight(None, None)

    def _link_at(self, view, position):
        try:
            info = view.getObjectInfo(position)
        except Exception:
            info = None
        if not info:
            return None, None, None
        doc, root, sub = _info_target(info)
        return link_under(doc, root, sub, self._contains)

    def _path_at(self, view, position):
        return self._link_at(view, position)[0]

    # -- the small menu -------------------------------------------------------
    def show_menu(self, path):
        if self.menu is not None:
            try:
                self.menu.close()
            except Exception:
                pass
        self.menu = PartMenu(self, path)
        self.menu.popup(QtGui.QCursor.pos())

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


def _info_target(info):
    """(document, top object name, subname) from View3DInventor.getObjectInfo().

    FreeCAD gives "Object" as a name but "ParentObject" as the object itself.
    """
    parent = info.get("ParentObject")
    if parent is not None:
        name = parent if isinstance(parent, str) else getattr(parent, "Name", None)
        doc = getattr(parent, "Document", None)
        sub = info.get("SubName", "") or ""
    else:
        name, doc, sub = info.get("Object"), None, ""
    if doc is None and info.get("Document"):
        try:
            doc = App.getDocument(info.get("Document"))
        except Exception:
            doc = None
    return doc, name, sub


def _guarded(handler):
    """Coin callbacks must never raise: FreeCAD only prints the exception's class."""
    def run(event):
        try:
            handler(event)
        except Exception:
            import traceback
            App.Console.PrintWarning("CoBench: %s\n" % traceback.format_exc())
    return run


class _Gate:
    """Selection gate: nothing selectable in picked assemblies, the rest untouched."""

    def __init__(self, watcher):
        self.watcher = watcher

    def allow(self, doc, obj, sub):
        try:
            return not self.watcher.picking(doc.Name)
        except Exception:
            return True


def _add_gate(gate):
    """Install the gate so that it is asked about the document where the click
    happens (the assembly), not about the file of the linked part: FreeCAD
    resolves links before asking a gate unless told not to (resolve = 0)."""
    try:
        Gui.Selection.addSelectionGate(gate, 0)
    except TypeError:  # older FreeCAD: no resolve argument
        Gui.Selection.addSelectionGate(gate)


def _viewport(view):
    """The Qt widget that receives the mouse events of a 3D view."""
    try:
        return view.graphicsView().viewport()
    except Exception:
        return None


def _event_pos(event):
    pos = event.position() if hasattr(event, "position") else event.pos()
    return QtCore.QPointF(pos)


class _MouseFilter(QtCore.QObject):
    """Mouse of one 3D view of an assembly, seen before FreeCAD.

    In a picked assembly: moves without button never reach FreeCAD (no face or
    edge pre-selection), CoBench lights the whole part up instead; a left click
    opens the part menu; a left drag is handed back to FreeCAD so the view still
    rotates.  Everything else (wheel, middle and right buttons) goes through.
    """

    DRAG = 4  # pixels

    def __init__(self, watcher, view, doc_name, viewport):
        super().__init__(viewport)
        self.watcher = watcher
        self.view = view
        self.doc_name = doc_name
        self.viewport = viewport
        self.press = None       # (local position, global position, modifiers)
        self.dragging = False
        self.replaying = False
        self.cleared = False

    def eventFilter(self, obj, event):
        if self.replaying:
            return False
        try:
            return self._handle(event)
        except Exception:
            import traceback
            App.Console.PrintWarning("CoBench: %s\n" % traceback.format_exc())
            return False

    def _coin(self, pos):
        """Qt widget position -> Coin pixel position (origin bottom left, device pixels)."""
        ratio = self.viewport.devicePixelRatioF()
        return (int(pos.x() * ratio), int((self.viewport.height() - 1 - pos.y()) * ratio))

    def _handle(self, event):
        kind = event.type()
        mouse = (QtCore.QEvent.MouseMove, QtCore.QEvent.MouseButtonPress,
                 QtCore.QEvent.MouseButtonRelease, QtCore.QEvent.MouseButtonDblClick)
        if kind == QtCore.QEvent.Leave:
            self.watcher.unhover(self.doc_name)
            return False
        if kind not in mouse:
            return False
        if not self.watcher.picking(self.doc_name):
            self.press, self.dragging, self.cleared = None, False, False
            return False
        if not self.cleared:
            self.cleared = True
            try:
                Gui.Selection.clearPreselection()
                Gui.Selection.clearSelection(self.doc_name)
            except Exception:
                pass
        pos = _event_pos(event)
        left = event.button() == Qt.LeftButton
        if kind == QtCore.QEvent.MouseMove:
            if self.press is not None and not self.dragging:
                start = self.press[0]
                if abs(pos.x() - start.x()) > self.DRAG or abs(pos.y() - start.y()) > self.DRAG:
                    self.dragging = True
                    self.watcher.unhover(self.doc_name)
                    self._replay_press()
                    return False
                return True
            if self.dragging or event.buttons() != Qt.NoButton:
                return False
            # Over a part: ours.  Elsewhere (navigation cube...): FreeCAD's.
            return bool(self.watcher.hover(self.view, self.doc_name, self._coin(pos), self.viewport))
        if kind == QtCore.QEvent.MouseButtonPress and left:
            self.press = (pos, QtCore.QPointF(event.globalPosition() if hasattr(event, "globalPosition")
                                              else event.globalPos()), event.modifiers())
            self.dragging = False
            return True
        if kind == QtCore.QEvent.MouseButtonRelease and left:
            press, dragging = self.press, self.dragging
            self.press, self.dragging = None, False
            if press is None or dragging:
                return False  # the end of a rotation: FreeCAD's
            path = self.watcher._path_at(self.view, self._coin(pos))
            if not path:
                # Not a part (navigation cube, empty space...): an ordinary click for FreeCAD.
                self.press = press
                self._replay_press()
                self.press = None
                return False
            from .session import later
            later(lambda: self.watcher.show_menu(path))
            return True
        if kind == QtCore.QEvent.MouseButtonDblClick and left:
            return True
        return False

    def _replay_press(self):
        """Give FreeCAD the press it did not get, so the drag rotates the view."""
        local, global_pos, modifiers = self.press
        event = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, local, global_pos,
                                  Qt.LeftButton, Qt.LeftButton, modifiers)
        self.replaying = True
        try:
            QtWidgets.QApplication.sendEvent(self.viewport, event)
        finally:
            self.replaying = False


class PartMenu(QtWidgets.QFrame):
    """Small floating menu shown when a part of an assembly is clicked."""

    def __init__(self, watcher, path):
        super().__init__(Gui.getMainWindow(), Qt.Popup)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.watcher = watcher
        self.path = path
        session = watcher.session
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        title = QtWidgets.QLabel("<b>%s</b>" % _escape(os.path.splitext(os.path.basename(path))[0]))
        layout.addWidget(title)
        state = session.locks.state(path)
        from . import panel as panel_mod
        pending = "waiting" if session.waiting_for_file(path) else session.lock_pending(path)
        status = QtWidgets.QLabel(panel_mod.status_text(state, pending))
        status.setStyleSheet("color: gray;")
        layout.addWidget(status)
        if state.status == locks.OTHER:
            self._button(layout, tr("Ask for it"), lambda: session.ask_for(path))
        elif state.status == locks.MINE:
            self._button(layout, tr("Edit"), lambda: session.edit(path))
            self._button(layout, tr("Release"), lambda: session.release(path))
        else:
            self._button(layout, tr("Edit"), lambda: session.edit(path))
        self._button(layout, tr("Open read-only"), lambda: session.view(path))
        self._button(layout, tr("Show in the panel"), self._show_in_panel)

    def _button(self, layout, text, action):
        button = QtWidgets.QPushButton(text)
        button.setFlat(True)
        button.setStyleSheet("text-align: left; padding: 3px 6px;")

        def run():
            self.close()
            from .session import later
            later(action)
        button.clicked.connect(run)
        layout.addWidget(button)

    def _show_in_panel(self):
        from . import panel as panel_mod
        panel_mod.show_panel().select_path(self.path)

    def popup(self, position):
        self.adjustSize()
        self.move(position + QtCore.QPoint(8, 8))
        self.show()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)


def _escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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
