# SPDX-License-Identifier: LGPL-2.1-or-later
"""The CoBench panel: the parts of the project, by folder or as thumbnails."""

import datetime
import os

import FreeCADGui as Gui

from ..core import fcstd, locks, requests
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
    session_mod.PENDING: QtGui.QColor(227, 178, 43),
}


def status_text(state, pending=False):
    if state.status == locks.FREE:
        return tr("free")
    if state.status == locks.MINE:
        if pending == "waiting":
            return tr("you are editing (waiting for the last version)")
        return tr("you are editing (lock being sent)") if pending else tr("you are editing")
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


def _mtime(path):
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0]


class PartsPanel(QtWidgets.QWidget):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._icon_cache = {}
        self._graph = None
        self._missing = {}
        self._signature = None
        self._selected = None
        self._syncing = False
        self.grid_items = {}
        self.tree_items = {}
        self.folder_items = {}
        self._build()
        self.session.listeners.append(self.refresh)
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
        self.graph_button = self._tool_button("graph", tr("Show the links between parts"), self.show_graph)
        self.refresh_button = self._tool_button("refresh", tr("Refresh"), self.full_refresh)
        for button in (self.folder_button, self.assembly_button, self.graph_button, self.refresh_button):
            top.addWidget(button)
        layout.addLayout(top)

        self.warning = QtWidgets.QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #d0342c;")
        self.warning.hide()
        layout.addWidget(self.warning)

        filters = QtWidgets.QHBoxLayout()
        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText(tr("Filter (name, folder or #tag)"))
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._apply_filter)
        filters.addWidget(self.filter, 1)
        self.mode = QtWidgets.QToolButton()
        self.mode.setCheckable(True)
        self.mode.setChecked(prefs.panel_view() == "thumbnails")
        self.mode.setToolTip(tr("Switch between folders and thumbnails"))
        self.mode.toggled.connect(self._set_mode)
        filters.addWidget(self.mode)
        layout.addLayout(filters)

        self.stack = QtWidgets.QStackedWidget()
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels([tr("Part"), tr("State")])
        self.tree.setIconSize(QtCore.QSize(32, 32))
        self.tree.setUniformRowHeights(True)
        self.tree.header().setStretchLastSection(True)
        self.tree.itemSelectionChanged.connect(lambda: self._selection_from(self.tree))
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(lambda pos: self._context_menu(self.tree, pos))
        self.grid = QtWidgets.QListWidget()
        self.grid.setViewMode(QtWidgets.QListView.IconMode)
        self.grid.setIconSize(QtCore.QSize(ICON_SIZE, ICON_SIZE))
        self.grid.setResizeMode(QtWidgets.QListView.Adjust)
        self.grid.setMovement(QtWidgets.QListView.Static)
        self.grid.setWordWrap(True)
        self.grid.setGridSize(QtCore.QSize(ICON_SIZE + 36, ICON_SIZE + 52))
        self.grid.setUniformItemSizes(True)
        self.grid.itemSelectionChanged.connect(lambda: self._selection_from(self.grid))
        self.grid.itemDoubleClicked.connect(self._double_clicked)
        self.grid.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(lambda pos: self._context_menu(self.grid, pos))
        self.stack.addWidget(self.tree)
        self.stack.addWidget(self.grid)
        layout.addWidget(self.stack, 1)

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
        self.ask_button = QtWidgets.QPushButton(tr("Ask for it"))
        self.ask_button.setToolTip(tr("Ask the person editing it to release it"))
        self.ask_button.clicked.connect(self.ask_for)
        self.take_button = QtWidgets.QPushButton(tr("Take the lock"))
        self.take_button.setToolTip(tr("For a lock left behind after a crash"))
        self.take_button.clicked.connect(self.take_over)
        self.more_button = QtWidgets.QPushButton(tr("More"))
        self.more_button.clicked.connect(lambda: self._context_menu(None, None))
        buttons.addWidget(self.edit_button, 0, 0)
        buttons.addWidget(self.view_button, 0, 1)
        buttons.addWidget(self.release_button, 1, 0)
        buttons.addWidget(self.ask_button, 1, 1)
        buttons.addWidget(self.take_button, 2, 0)
        buttons.addWidget(self.more_button, 2, 1)
        layout.addLayout(buttons)

        self.activity_toggle = QtWidgets.QToolButton()
        self.activity_toggle.setText(tr("Activity"))
        self.activity_toggle.setCheckable(True)
        self.activity_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.activity_toggle.setArrowType(Qt.RightArrow)
        self.activity_toggle.setAutoRaise(True)
        self.activity_toggle.toggled.connect(self._toggle_activity)
        layout.addWidget(self.activity_toggle)
        self.activity = QtWidgets.QListWidget()
        self.activity.setMaximumHeight(110)
        self.activity.hide()
        layout.addWidget(self.activity)

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

    def _set_mode(self, thumbnails, save=True):
        self.stack.setCurrentWidget(self.grid if thumbnails else self.tree)
        self.mode.setText(tr("Folders") if thumbnails else tr("Thumbnails"))
        if save:
            prefs.set_panel_view("thumbnails" if thumbnails else "folders")

    def _toggle_activity(self, shown):
        self.activity.setVisible(shown)
        self.activity_toggle.setArrowType(Qt.DownArrow if shown else Qt.RightArrow)

    # -- data ----------------------------------------------------------------
    def full_refresh(self):
        fcstd.clear_cache()
        self._icon_cache.clear()
        self._graph = None
        self._signature = None
        if self.session.project:
            self.session.project.load()
        self.session.tick()

    def refresh(self):
        project = self.session.project
        identity = self.session.identity
        self.user_label.setText(tr("You appear as <b>{user}</b> (<a href='#'>change</a>)",
                                   user=_escape(identity.user)))
        self._refresh_activity()
        if project is None:
            self.title.setText(tr("<b>No project</b><br>Choose a folder holding .FCStd files."))
            self.grid.clear()
            self.tree.clear()
            self.grid_items, self.tree_items, self.folder_items = {}, {}, {}
            self._update_buttons()
            return
        self.title.setText("<b>%s</b><br><small>%s</small>" % (_escape(project.name), _escape(project.root)))
        self.assembly_button.setEnabled(bool(project.assembly))
        parts = list(self.session.parts)
        signature = tuple((p, _mtime(p)) for p in parts)
        if signature != self._signature:
            self._signature = signature
            self._graph = None
            self._missing = project.missing_links(parts)
        self._sync_grid(parts)
        self._sync_tree(parts)
        broken = sum(len(v) for v in self._missing.values())
        problems = []
        if self.session.store() == "supabase" and self.session.locks.error:
            problems.append(tr("Lock database: {error}", error=self.session.locks.error))
        if broken:
            problems.append(tr("{count} broken links: a linked file was moved or deleted.", count=broken))
        self.warning.setText("\n".join(problems))
        self.warning.setVisible(bool(problems))
        self._apply_filter()
        self._show_details()

    def _key(self, path, state):
        """Colour key: the lock status, or PENDING while my lock is not sent yet."""
        if state.status == locks.MINE and self.session.lock_pending(path):
            return session_mod.PENDING
        return state.status

    def _text(self, path, state):
        if self._key(path, state) != session_mod.PENDING:
            return status_text(state)
        return status_text(state, "waiting" if self.session.waiting_for_file(path) else "sending")

    def _label(self, path):
        project = self.session.project
        name = _stem(path)
        if project.rel(path) == project.assembly:
            name = "★ " + name  # the central assembly
        if path in self._missing:
            name = "⚠ " + name
        if requests.Request.read(path) is not None:
            name = name + " ✉"
        return name

    def _sync_grid(self, parts):
        for path in list(self.grid_items):
            if path not in parts:
                self.grid.takeItem(self.grid.row(self.grid_items.pop(path)))
        for index, path in enumerate(parts):
            state = self.session.state(path)
            item = self.grid_items.get(path)
            if item is None:
                item = QtWidgets.QListWidgetItem()
                item.setData(PATH_ROLE, path)
                self.grid.insertItem(index, item)
                self.grid_items[path] = item
            item.setText("%s\n%s" % (self._label(path), self._text(path, state)))
            item.setIcon(self._icon(path, state))
            item.setForeground(COLORS[self._key(path, state)] if state.status != locks.FREE
                               else self.palette().text().color())
            item.setToolTip(self._tooltip(path, state))

    def _folder_item(self, rel_dir):
        if not rel_dir:
            return None
        item = self.folder_items.get(rel_dir)
        if item is not None:
            return item
        parent_dir, name = os.path.split(rel_dir)
        parent = self._folder_item(parent_dir)
        item = QtWidgets.QTreeWidgetItem([name, ""])
        item.setIcon(0, QtGui.QIcon(icon_path("folder")))
        item.setFlags(Qt.ItemIsEnabled)
        if parent is None:
            self.tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        item.setExpanded(True)
        self.folder_items[rel_dir] = item
        return item

    def _sync_tree(self, parts):
        project = self.session.project
        for path in list(self.tree_items):
            if path not in parts:
                item = self.tree_items.pop(path)
                (item.parent() or self.tree.invisibleRootItem()).removeChild(item)
        for path in parts:
            state = self.session.state(path)
            rel_dir = os.path.dirname(project.rel(path))
            item = self.tree_items.get(path)
            if item is None:
                item = QtWidgets.QTreeWidgetItem()
                item.setData(0, PATH_ROLE, path)
                parent = self._folder_item(rel_dir)
                if parent is None:
                    self.tree.addTopLevelItem(item)
                else:
                    parent.addChild(item)
                self.tree_items[path] = item
            item.setText(0, self._label(path))
            item.setText(1, self._text(path, state))
            item.setIcon(0, self._icon(path, state))
            color = COLORS[self._key(path, state)] if state.status != locks.FREE else self.palette().text().color()
            item.setForeground(0, color)
            item.setForeground(1, color)
            tip = self._tooltip(path, state)
            item.setToolTip(0, tip)
            item.setToolTip(1, tip)
        # Folders emptied by a move go away.
        for rel_dir in sorted(self.folder_items, key=len, reverse=True):
            item = self.folder_items[rel_dir]
            if item.childCount() == 0:
                (item.parent() or self.tree.invisibleRootItem()).removeChild(item)
                del self.folder_items[rel_dir]
        self.tree.sortItems(0, Qt.AscendingOrder)

    def _tooltip(self, path, state):
        tip = [self.session.project.rel(path), self._text(path, state)]
        if state.info:
            tip.append(session_mod.describe_lock(state.info))
        tags = self.session.project.tags_of(path)
        if tags:
            tip.append(" ".join("#" + t for t in tags))
        return "\n".join(tip)

    def _icon(self, path, state):
        part = fcstd.read_part(path)
        status = self._key(path, state)
        key = (part.thumbnail is not None and len(part.thumbnail), _mtime(path), status)
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
        color = COLORS[status]
        if state.status != locks.FREE:
            pen = QtGui.QPen(color)
            pen.setWidth(5)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(3, 3, size - 6, size - 6, 8, 8)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(size - 26, 4, 22, 22)
        painter.end()
        icon = QtGui.QIcon(canvas)
        self._icon_cache[path] = (key, icon)
        return icon

    def _apply_filter(self):
        project = self.session.project
        words = [w.lower() for w in self.filter.text().split()]
        tags = [w[1:] for w in words if w.startswith("#") and len(w) > 1]
        texts = [w for w in words if not w.startswith("#")]

        def visible(path):
            if project is None:
                return True
            haystack = (project.rel(path) + " " + self._text(path, self.session.state(path))).lower()
            part_tags = [t.lower() for t in project.tags_of(path)]
            return (all(t in haystack for t in texts)
                    and all(any(tag in pt for pt in part_tags) for tag in tags))

        for path, item in self.grid_items.items():
            item.setHidden(not visible(path))
        for path, item in self.tree_items.items():
            item.setHidden(not visible(path))
        for rel_dir in sorted(self.folder_items, key=len, reverse=True):
            item = self.folder_items[rel_dir]
            item.setHidden(all(item.child(i).isHidden() for i in range(item.childCount())))

    def _refresh_activity(self):
        entries = self.session.activity
        if self.activity.count() == len(entries):
            return
        self.activity.clear()
        for moment, text in reversed(entries):
            self.activity.addItem("%s  %s" % (moment.strftime("%H:%M"), text))
        if entries:
            self.activity_toggle.setText(tr("Activity") + "  •  " + entries[-1][1])

    # -- selection -----------------------------------------------------------
    def selected_path(self):
        return self._selected

    def _selection_from(self, view):
        if self._syncing:
            return
        if view is self.tree:
            items = self.tree.selectedItems()
            path = items[0].data(0, PATH_ROLE) if items else None
        else:
            items = self.grid.selectedItems()
            path = items[0].data(PATH_ROLE) if items else None
        if path:
            self._selected = path
            self._sync_selection(path, skip=view)
        self._show_details()

    def _sync_selection(self, path, skip=None):
        self._syncing = True
        try:
            if skip is not self.grid and path in self.grid_items:
                self.grid.setCurrentItem(self.grid_items[path])
            if skip is not self.tree and path in self.tree_items:
                self.tree.setCurrentItem(self.tree_items[path])
        finally:
            self._syncing = False

    def select_path(self, path):
        target = os.path.normcase(os.path.abspath(path))
        for known in self.tree_items:
            if os.path.normcase(known) == target:
                self._selected = known
                self._sync_selection(known)
                view = self.stack.currentWidget()
                if view is self.tree:
                    self.tree.scrollToItem(self.tree_items[known])
                else:
                    self.grid.scrollToItem(self.grid_items[known])
                self._show_details()
                return True
        return False

    def _double_clicked(self, item, *_args):
        if self._selected:
            self.view()  # open read-only; the padlock (or Edit) locks it

    def _graph_data(self):
        if self._graph is None and self.session.project:
            graph = self.session.project.link_graph(self.session.parts)
            self._graph = (graph, self.session.project.used_in(graph))
        return self._graph or ({}, {})

    def _show_details(self):
        path = self._selected
        if path is not None and path not in self.tree_items:
            path = self._selected = None
        self._update_buttons()
        if not path or self.session.project is None:
            self.details.setText("<i>%s</i>" % tr("Select a part. Double-click to open it read-only."))
            return
        project = self.session.project
        state = self.session.state(path)
        part = fcstd.read_part(path)
        color = COLORS[self._key(path, state)].name()
        lines = ["<b>%s</b>" % _escape(project.rel(path)),
                 "<span style='color:%s'>&#9679;</span> %s" % (color, _escape(self._text(path, state)))]
        if state.info:
            lines.append(_escape(session_mod.describe_lock(state.info)))
        request = requests.Request.read(path)
        if request is not None and request.status == requests.PENDING:
            lines.append(tr("Requested by {user}", user=_escape(request.user)))
        author = part.meta.get("LastModifiedBy") or ""
        lines.append(tr("Saved {when}{by}", when=_fmt_time((_mtime(path) or 0) / 1e9),
                        by=(" " + tr("by {user}", user=_escape(author))) if author else ""))
        tags = project.tags_of(path)
        if tags:
            lines.append(" ".join("<b>#%s</b>" % _escape(t) for t in tags))
        graph, used_in = self._graph_data()
        contains = graph.get(path) or []
        users = used_in.get(path) or []
        if contains:
            lines.append(tr("Uses: {parts}", parts=", ".join(_escape(_stem(p)) for p in contains)))
        if users:
            lines.append(tr("Used in: {parts}", parts=", ".join(_escape(_stem(p)) for p in users)))
        for gone in self._missing.get(path, []):
            lines.append("<span style='color:#d0342c'>%s</span>" % _escape(tr(
                "Broken link: {file} not found", file=os.path.relpath(gone, os.path.dirname(path)))))
        conflicts = locks.find_conflicts(path)
        if conflicts:
            lines.append("<span style='color:#d0342c'>%s</span>" % _escape(tr(
                "Conflict copies made by the sync client: {files}",
                files=", ".join(os.path.basename(c) for c in conflicts))))
        if part.error:
            lines.append("<i>%s</i>" % tr("Could not read the file (still syncing?)."))
        self.details.setText("<br>".join(lines))

    def _update_buttons(self):
        path = self._selected
        state = self.session.state(path) if path else None
        status = state.status if state else None
        self.edit_button.setEnabled(path is not None)
        self.view_button.setEnabled(path is not None)
        self.release_button.setEnabled(status in (locks.MINE, locks.ORPHAN))
        self.ask_button.setEnabled(status == locks.OTHER)
        self.take_button.setEnabled(status in (locks.OTHER, locks.ORPHAN))
        self.more_button.setEnabled(path is not None)
        self.edit_button.setText(tr("Edit") if status != locks.MINE else tr("Show"))

    def _context_menu(self, view, position):
        if view is not None:
            item = view.itemAt(position)
            path = item.data(0, PATH_ROLE) if view is self.tree and item else (
                item.data(PATH_ROLE) if item else None)
            if not path:
                return
            self.select_path(path)
        path = self._selected
        if not path:
            return
        menu = QtWidgets.QMenu(self)
        if view is not None:
            for button in (self.edit_button, self.view_button, self.release_button, self.ask_button,
                           self.take_button):
                action = menu.addAction(button.text())
                action.setEnabled(button.isEnabled())
                action.triggered.connect(button.click)
            menu.addSeparator()
        menu.addAction(tr("Rename..."), lambda: self.rename(path))
        menu.addAction(tr("Move to folder..."), lambda: self.move(path))
        menu.addAction(tr("Tags..."), lambda: self.edit_tags(path))
        menu.addSeparator()
        menu.addAction(tr("Use as central assembly"), lambda: self.set_assembly(path))
        menu.addAction(tr("Show in file explorer"), lambda: QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(os.path.dirname(path))))
        if view is not None:
            menu.exec(view.viewport().mapToGlobal(position))
        else:
            menu.exec(self.more_button.mapToGlobal(QtCore.QPoint(0, self.more_button.height())))

    # -- actions -------------------------------------------------------------
    def _run(self, action, *args):
        path = self._selected
        if path:
            try:
                action(path, *args)
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "CoBench", str(exc))
            self.session.tick()

    def edit(self):
        self._run(self.session.edit)

    def view(self):
        self._run(self.session.view)

    def release(self):
        self._run(self.session.release)

    def take_over(self):
        self._run(self.session.take_over)

    def ask_for(self):
        self._run(self.session.ask_for)

    def rename(self, path):
        stem = _stem(path)
        name, ok = QtWidgets.QInputDialog.getText(self, "CoBench", tr("New name for {name}:", name=stem),
                                                  QtWidgets.QLineEdit.Normal, stem)
        name = name.strip()
        if not ok or not name or name == stem:
            return
        if any(c in name for c in '<>:"/\\|?*'):
            QtWidgets.QMessageBox.warning(self, "CoBench", tr("A file name cannot contain < > : \" / \\ | ? *"))
            return
        self._do_move(path, os.path.join(os.path.dirname(path), name + ".FCStd"))

    def move(self, path):
        project = self.session.project
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, tr("Move {name} to", name=_stem(path)), os.path.dirname(path))
        if not folder:
            return
        if not project.contains(os.path.join(folder, "x")):
            QtWidgets.QMessageBox.warning(self, "CoBench", tr("Choose a folder inside the project."))
            return
        self._do_move(path, os.path.join(folder, os.path.basename(path)))

    def _do_move(self, path, new_path):
        if os.path.normcase(os.path.abspath(new_path)) == os.path.normcase(os.path.abspath(path)):
            return
        try:
            new = self.session.move(path, new_path)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "CoBench", str(exc))
            return
        self._signature = None
        self.session.tick()
        self.select_path(new)

    def edit_tags(self, path):
        project = self.session.project
        current = " ".join("#" + t for t in project.tags_of(path))
        known = project.all_tags()
        hint = tr("Tags for {name}, separated by spaces (known: {known}):", name=_stem(path),
                  known=" ".join("#" + t for t in known) or "-")
        text, ok = QtWidgets.QInputDialog.getText(self, "CoBench", hint, QtWidgets.QLineEdit.Normal, current)
        if ok:
            project.set_tags(path, text.replace(",", " ").split())
            self.refresh()

    def set_assembly(self, path):
        self.session.project.set_assembly(path)
        self.session.tick()

    def choose_folder(self):
        start = self.session.project.root if self.session.project else os.path.expanduser("~")
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, tr("Choose the project folder"), start)
        if folder:
            self._graph = None
            self._signature = None
            self._selected = None
            self.grid.clear()
            self.tree.clear()
            self.grid_items, self.tree_items, self.folder_items = {}, {}, {}
            self.session.open_project(folder)

    def open_assembly(self):
        project = self.session.project
        if project and project.assembly:
            path = project.assembly_path()
            if not os.path.exists(path):
                QtWidgets.QMessageBox.warning(self, "CoBench", tr("{name} not found.", name=project.assembly))
                return
            self.session.open_assembly(path)

    def show_graph(self):
        if self.session.project is None:
            return
        from .graph import GraphDialog
        graph, _users = self._graph_data()
        dialog = GraphDialog(self.session, graph, self)
        dialog.part_selected.connect(self.select_path)
        dialog.part_activated.connect(lambda path: (self.select_path(path), self.view()))
        dialog.show()

    def change_user(self):
        change_user_dialog(self.session, self)


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
