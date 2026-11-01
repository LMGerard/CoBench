# SPDX-License-Identifier: LGPL-2.1-or-later
"""The CoBench panel: every part of the project with its preview and lock."""

import datetime
import os

import FreeCADGui as Gui

from ..core import fcstd, locks
from ..i18n import tr
from . import prefs, session as session_mod
from .qt import Qt, QtCore, QtGui, QtWidgets

PANEL_NAME = "CoBenchPanel"
ICON_SIZE = 96
PATH_ROLE = Qt.UserRole + 1

COLORS = {
    locks.FREE: QtGui.QColor(150, 150, 150),
    locks.MINE: QtGui.QColor(46, 160, 67),
    locks.OTHER: QtGui.QColor(208, 52, 44),
    locks.ORPHAN: QtGui.QColor(230, 140, 20),
}


def status_text(state):
    if state.status == locks.FREE:
        return tr("free")
    if state.status == locks.MINE:
        return tr("you are editing")
    if state.status == locks.ORPHAN:
        return tr("your old lock (FreeCAD closed)")
    return tr("locked by {user}", user=state.info.user if state.info else "?")


def _fmt_time(value):
    if isinstance(value, (int, float)):
        moment = datetime.datetime.fromtimestamp(value)
    else:
        moment = locks.parse_iso(value)
        if moment is None:
            return value or ""
        moment = moment.astimezone()
    return moment.strftime("%d/%m/%Y %H:%M")


def _escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class PartsPanel(QtWidgets.QWidget):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.states = {}
        self._icon_cache = {}
        self._graph = None
        self._build()
        self.session.listeners.append(self.refresh)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(prefs.refresh_seconds() * 1000)
        self.refresh()

    # -- layout --------------------------------------------------------------
    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        top = QtWidgets.QHBoxLayout()
        self.title = QtWidgets.QLabel()
        self.title.setTextFormat(Qt.RichText)
        self.title.setWordWrap(True)
        top.addWidget(self.title, 1)
        self.folder_button = self._tool_button("folder", tr("Choose the project folder"), self.choose_folder)
        self.assembly_button = self._tool_button("assembly", tr("Open the central assembly"), self.open_assembly)
        self.refresh_button = self._tool_button("refresh", tr("Refresh"), self.full_refresh)
        for button in (self.folder_button, self.assembly_button, self.refresh_button):
            top.addWidget(button)
        layout.addLayout(top)

        filters = QtWidgets.QHBoxLayout()
        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText(tr("Filter parts"))
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._apply_filter)
        filters.addWidget(self.filter, 1)
        self.mode = QtWidgets.QToolButton()
        self.mode.setCheckable(True)
        self.mode.setChecked(not prefs.icon_view())
        self.mode.setText(tr("List"))
        self.mode.setToolTip(tr("Switch between thumbnails and a compact list"))
        self.mode.toggled.connect(self._set_mode)
        filters.addWidget(self.mode)
        layout.addLayout(filters)

        self.list = QtWidgets.QListWidget()
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.list.setUniformItemSizes(True)
        self.list.itemSelectionChanged.connect(self._show_details)
        self.list.itemDoubleClicked.connect(lambda item: self.edit())
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.list, 1)

        self.details = QtWidgets.QLabel()
        self.details.setTextFormat(Qt.RichText)
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.details.setMinimumHeight(60)
        self.details.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.details)

        buttons = QtWidgets.QGridLayout()
        self.edit_button = QtWidgets.QPushButton(tr("Edit"))
        self.edit_button.setToolTip(tr("Lock the part and open it"))
        self.edit_button.clicked.connect(self.edit)
        self.view_button = QtWidgets.QPushButton(tr("Open read-only"))
        self.view_button.clicked.connect(self.view)
        self.release_button = QtWidgets.QPushButton(tr("Release"))
        self.release_button.setToolTip(tr("Give the part back so others can edit it"))
        self.release_button.clicked.connect(self.release)
        self.take_button = QtWidgets.QPushButton(tr("Take the lock"))
        self.take_button.setToolTip(tr("For a lock left behind after a crash"))
        self.take_button.clicked.connect(self.take_over)
        buttons.addWidget(self.edit_button, 0, 0)
        buttons.addWidget(self.view_button, 0, 1)
        buttons.addWidget(self.release_button, 1, 0)
        buttons.addWidget(self.take_button, 1, 1)
        layout.addLayout(buttons)

        self.user_label = QtWidgets.QLabel()
        self.user_label.setTextFormat(Qt.RichText)
        self.user_label.linkActivated.connect(lambda _link: self.change_user())
        layout.addWidget(self.user_label)

        self._set_mode(self.mode.isChecked(), save=False)

    def _tool_button(self, icon, tip, slot):
        button = QtWidgets.QToolButton()
        button.setIcon(QtGui.QIcon(icon_path(icon)))
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.clicked.connect(slot)
        return button

    def _set_mode(self, compact, save=True):
        if compact:
            self.list.setViewMode(QtWidgets.QListView.ListMode)
            self.list.setIconSize(QtCore.QSize(32, 32))
            self.list.setWordWrap(False)
            self.list.setGridSize(QtCore.QSize())
        else:
            self.list.setViewMode(QtWidgets.QListView.IconMode)
            self.list.setIconSize(QtCore.QSize(ICON_SIZE, ICON_SIZE))
            self.list.setResizeMode(QtWidgets.QListView.Adjust)
            self.list.setMovement(QtWidgets.QListView.Static)
            self.list.setWordWrap(True)
            self.list.setGridSize(QtCore.QSize(ICON_SIZE + 36, ICON_SIZE + 52))
        if save:
            prefs.set_icon_view(not compact)

    # -- data ----------------------------------------------------------------
    def full_refresh(self):
        fcstd.clear_cache()
        self._icon_cache.clear()
        self._graph = None
        if self.session.project:
            self.session.project.load()
        self.session.changed()

    def refresh(self):
        project = self.session.project
        identity = self.session.identity
        self.user_label.setText(tr("You appear as <b>{user}</b> (<a href='#'>change</a>)",
                                   user=_escape(identity.user)))
        if project is None:
            self.title.setText(tr("<b>No project</b><br>Choose a folder holding .FCStd files."))
            self.list.clear()
            self.states = {}
            self._update_buttons()
            return
        self.title.setText("<b>%s</b><br><small>%s</small>" % (_escape(project.name), _escape(project.root)))
        self.assembly_button.setEnabled(bool(project.assembly))
        parts = project.parts()
        signature = tuple((p, _mtime(p)) for p in parts)
        if signature != getattr(self, "_signature", None):
            self._signature = signature
            self._graph = None  # links may have changed
        existing = {}
        for row in range(self.list.count()):
            item = self.list.item(row)
            existing[item.data(PATH_ROLE)] = item
        for path in list(existing):
            if path not in parts:
                self.list.takeItem(self.list.row(existing.pop(path)))
        states = {}
        for index, path in enumerate(parts):
            state = self.session.locks.state(path)
            states[path] = state
            self.session.apply_protection(path, state)
            item = existing.get(path)
            if item is None:
                item = QtWidgets.QListWidgetItem()
                item.setData(PATH_ROLE, path)
                self.list.insertItem(index, item)
            self._fill(item, path, state)
        self.states = states
        self._apply_filter()
        self._show_details()

    def _fill(self, item, path, state):
        part = fcstd.read_part(path)
        rel = self.session.project.rel(path)
        name = os.path.splitext(os.path.basename(path))[0]
        if rel == self.session.project.assembly:
            name = "★ " + name  # the central assembly
        item.setText("%s\n%s" % (name, status_text(state)))
        item.setIcon(self._icon(path, part, state))
        item.setForeground(COLORS[state.status] if state.status != locks.FREE else self.palette().text().color())
        tip = [rel, status_text(state)]
        if state.info:
            tip.append(session_mod.describe_lock(state.info))
        item.setToolTip("\n".join(tip))

    def _icon(self, path, part, state):
        key = (path, part.thumbnail is not None and len(part.thumbnail), _mtime(path), state.status)
        cached = self._icon_cache.get(path)
        if cached and cached[0] == key:
            return cached[1]
        size = ICON_SIZE
        canvas = QtGui.QPixmap(size, size)
        canvas.fill(Qt.transparent)
        painter = QtGui.QPainter(canvas)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        image = QtGui.QPixmap()
        if part.thumbnail:
            image.loadFromData(part.thumbnail)
        if image.isNull():
            image = QtGui.QPixmap(icon_path("part"))
        if not image.isNull():
            image = image.scaled(size - 8, size - 8, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap((size - image.width()) // 2, (size - image.height()) // 2, image)
        color = COLORS[state.status]
        if state.status != locks.FREE:
            pen = QtGui.QPen(color)
            pen.setWidth(4)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(2, 2, size - 4, size - 4, 8, 8)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(size - 22, 4, 18, 18)
        painter.end()
        icon = QtGui.QIcon(canvas)
        self._icon_cache[path] = (key, icon)
        return icon

    def _apply_filter(self):
        text = self.filter.text().strip().lower()
        for row in range(self.list.count()):
            item = self.list.item(row)
            rel = self.session.project.rel(item.data(PATH_ROLE)).lower() if self.session.project else ""
            item.setHidden(bool(text) and text not in rel and text not in item.text().lower())

    # -- selection -----------------------------------------------------------
    def selected_path(self):
        items = self.list.selectedItems()
        return items[0].data(PATH_ROLE) if items else None

    def select_path(self, path):
        target = os.path.normcase(os.path.abspath(path))
        for row in range(self.list.count()):
            item = self.list.item(row)
            if os.path.normcase(item.data(PATH_ROLE)) == target:
                self.list.setCurrentItem(item)
                self.list.scrollToItem(item)
                return True
        return False

    def _graph_for_details(self):
        if self._graph is None and self.session.project:
            graph = self.session.project.link_graph()
            self._graph = (graph, self.session.project.used_in(graph))
        return self._graph or ({}, {})

    def _show_details(self):
        path = self.selected_path()
        self._update_buttons()
        if not path or self.session.project is None:
            self.details.setText("<i>%s</i>" % tr("Select a part. Double-click to edit it."))
            return
        project = self.session.project
        state = self.states.get(path) or self.session.locks.state(path)
        part = fcstd.read_part(path)
        color = COLORS[state.status].name()
        lines = ["<b>%s</b>" % _escape(project.rel(path)),
                 "<span style='color:%s'>&#9679;</span> %s" % (color, _escape(status_text(state)))]
        if state.info:
            lines.append(_escape(session_mod.describe_lock(state.info)))
        author = part.meta.get("LastModifiedBy") or ""
        lines.append(tr("Saved {when}{by}", when=_fmt_time((_mtime(path) or 0) / 1e9),
                        by=(" " + tr("by {user}", user=_escape(author))) if author else ""))
        graph, used_in = self._graph_for_details()
        contains = graph.get(path) or []
        users = used_in.get(path) or []
        if contains:
            lines.append(tr("Uses: {parts}", parts=", ".join(_escape(_stem(p)) for p in contains)))
        if users:
            lines.append(tr("Used in: {parts}", parts=", ".join(_escape(_stem(p)) for p in users)))
        conflicts = locks.find_conflicts(path)
        if conflicts:
            lines.append("<span style='color:#d0342c'>%s</span>" % _escape(tr(
                "Conflict copies made by the sync client: {files}",
                files=", ".join(os.path.basename(c) for c in conflicts))))
        if part.error:
            lines.append("<i>%s</i>" % tr("Could not read the file (still syncing?)."))
        self.details.setText("<br>".join(lines))

    def _update_buttons(self):
        path = self.selected_path()
        state = self.states.get(path) if path else None
        status = state.status if state else None
        self.edit_button.setEnabled(path is not None)
        self.view_button.setEnabled(path is not None)
        self.release_button.setEnabled(status in (locks.MINE, locks.ORPHAN))
        self.take_button.setEnabled(status in (locks.OTHER, locks.ORPHAN))
        self.edit_button.setText(tr("Edit") if status != locks.MINE else tr("Show"))

    def _context_menu(self, position):
        item = self.list.itemAt(position)
        if item is None:
            return
        self.list.setCurrentItem(item)
        menu = QtWidgets.QMenu(self)
        for button in (self.edit_button, self.view_button, self.release_button, self.take_button):
            action = menu.addAction(button.text())
            action.setEnabled(button.isEnabled())
            action.triggered.connect(button.click)
        menu.addSeparator()
        central = menu.addAction(tr("Use as central assembly"))
        central.triggered.connect(lambda: self.set_assembly(item.data(PATH_ROLE)))
        reveal = menu.addAction(tr("Show in file explorer"))
        reveal.triggered.connect(lambda: QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(os.path.dirname(item.data(PATH_ROLE)))))
        menu.exec(self.list.viewport().mapToGlobal(position))

    # -- actions -------------------------------------------------------------
    def _run(self, action):
        path = self.selected_path()
        if path:
            try:
                action(path)
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "CoBench", str(exc))
            self.refresh()

    def edit(self):
        self._run(self.session.edit)

    def view(self):
        self._run(self.session.view)

    def release(self):
        self._run(self.session.release)

    def take_over(self):
        self._run(self.session.take_over)

    def set_assembly(self, path):
        self.session.project.set_assembly(path)
        self.session.changed()

    def choose_folder(self):
        start = self.session.project.root if self.session.project else os.path.expanduser("~")
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, tr("Choose the project folder"), start)
        if folder:
            self._graph = None
            self.list.clear()
            self.session.open_project(folder)

    def open_assembly(self):
        project = self.session.project
        if project and project.assembly:
            path = project.assembly_path()
            if not os.path.exists(path):
                QtWidgets.QMessageBox.warning(self, "CoBench", tr("{name} not found.", name=project.assembly))
                return
            self.session.view(path)

    def change_user(self):
        change_user_dialog(self.session, self)


def _mtime(path):
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def icon_path(name):
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(here, "Resources", "icons", name + ".svg")


def change_user_dialog(session, parent=None):
    name, ok = QtWidgets.QInputDialog.getText(
        parent, "CoBench", tr("Name shown to the others on your locks:"),
        QtWidgets.QLineEdit.Normal, session.identity.user)
    if ok and name.strip():
        session.set_user(name.strip())
        if not prefs.freecad_author():
            prefs.set_freecad_author(name.strip())
        return True
    return False


_dock = None


def show_panel():
    """Create the dock (once) and show it."""
    global _dock
    window = Gui.getMainWindow()
    if _dock is None or not _alive(_dock):
        _dock = window.findChild(QtWidgets.QDockWidget, PANEL_NAME)
    if _dock is None:
        _dock = QtWidgets.QDockWidget("CoBench", window)
        _dock.setObjectName(PANEL_NAME)
        _dock.setWidget(PartsPanel(session_mod.get(), _dock))
        window.addDockWidget(Qt.RightDockWidgetArea, _dock)
    _dock.show()
    _dock.raise_()
    return _dock.widget()


def current_panel():
    if _dock is not None and _alive(_dock):
        return _dock.widget()
    return None


def _alive(widget):
    try:
        widget.objectName()
        return True
    except RuntimeError:
        return False
