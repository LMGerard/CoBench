# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD commands of the CoBench workbench."""

import FreeCAD as App
import FreeCADGui as Gui

from ..core import locks
from ..i18n import tr
from . import assembly, panel, prefs, session as session_mod
from .qt import QtGui, QtWidgets

_watcher = None
_tree = None


def start():
    """Session, assembly boxes and tree cleaning, created once."""
    global _watcher, _tree
    session = session_mod.get()
    if _watcher is None:
        _watcher = assembly.AssemblyWatcher(session, panel.current_panel)
    if _tree is None:
        from .tree import TreeHider
        _tree = TreeHider(session)
    return session


class _Command:
    icon = "CoBench"
    menu = ""
    tip = ""
    accel = ""

    def GetResources(self):
        resources = {"Pixmap": panel.icon_path(self.icon), "MenuText": tr(self.menu), "ToolTip": tr(self.tip)}
        if self.accel:
            resources["Accel"] = self.accel
        return resources

    def IsActive(self):
        return True


class ShowPanel(_Command):
    icon = "CoBench"
    menu = "Project panel"
    tip = "Show the parts of the project, their previews and who edits them"

    def Activated(self):
        start()
        panel.show_panel()


class OpenProject(_Command):
    icon = "folder"
    menu = "Open project folder..."
    tip = "Choose the folder holding the project's .FCStd files (local, network or synchronised)"

    def Activated(self):
        start()
        panel.show_panel().choose_folder()


class OpenAssembly(_Command):
    icon = "assembly"
    menu = "Open central assembly"
    tip = "Open the project's central assembly; locked parts are shown in colour"

    def IsActive(self):
        session = session_mod.get()
        return bool(session.project and session.project.assembly)

    def Activated(self):
        start()
        panel.show_panel().open_assembly()


class ShowGraph(_Command):
    icon = "graph"
    menu = "Links between parts"
    tip = "Show which file uses which part, coloured by who edits them"

    def IsActive(self):
        return session_mod.get().project is not None

    def Activated(self):
        start()
        panel.show_panel().show_graph()


class AskForPart(_Command):
    icon = "edit"
    menu = "Ask for the part"
    tip = "Ask the person editing the selected part to release it"

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        session = start()
        path = assembly.selected_part(session)
        if path:
            session.ask_for(path)


class SetAssembly(_Command):
    icon = "assembly"
    menu = "Use active document as central assembly"
    tip = "Remember the active document as the project's central assembly"

    def IsActive(self):
        doc = App.ActiveDocument
        session = session_mod.get()
        return bool(doc and doc.FileName and session.project and session.project.contains(doc.FileName))

    def Activated(self):
        session = start()
        session.project.set_assembly(App.ActiveDocument.FileName)
        session.changed()


class EditPart(_Command):
    icon = "edit"
    menu = "Edit part"
    tip = "Lock the selected part (or the active document) and open it for editing"

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        session = start()
        path = assembly.selected_part(session)
        if not path:
            QtWidgets.QMessageBox.information(
                Gui.getMainWindow(), "CoBench",
                tr("Select a part of the project (in the 3D view, the tree or the CoBench panel)."))
            return
        session.edit(path)


LOCK_LOOKS = {
    # display status -> (icon, menu text, tooltip)
    None: ("lock_none", "Lock", "Select a part of the project to lock or release it"),
    locks.FREE: ("lock_free", "Lock and edit",
                 "Free: lock the selected part (or the active document) and open it"),
    session_mod.PENDING: ("lock_pending", "Release",
                          "You are editing it; the lock is being sent (wait before going offline). "
                          "Click to release it"),
    locks.MINE: ("lock_mine", "Release", "You are editing it. Click to release it"),
    locks.OTHER: ("lock_other", "Ask for it", "Locked by someone else. Click to ask for it"),
    locks.ORPHAN: ("lock_orphan", "Take back", "Your own lock left by a FreeCAD that closed. Click to take it back"),
}


def lock_target():
    """(part path, display status) for the lock button."""
    session = session_mod.get()
    path = assembly.selected_part(session)
    if not path:
        return None, None
    state = session.locks.state(path)
    if state.status == locks.MINE and session.lock_pending(path):
        return path, session_mod.PENDING
    return path, state.status


class LockToggle(_Command):
    """One padlock: its colour is the state of the selected part, a click does the right thing."""
    icon = "lock_free"
    menu = "Lock and edit"
    tip = "Free: lock the selected part (or the active document) and open it"

    def __init__(self):
        self._shown = "unset"

    def IsActive(self):
        try:
            path, status = lock_target()
        except Exception:
            path, status = None, None
        self._show(status)
        return path is not None

    def _show(self, status):
        if status == self._shown:
            return
        try:
            actions = Gui.Command.get("CoBench_Lock").getAction()
        except Exception:
            return
        icon_name, menu, tip = LOCK_LOOKS[status]
        icon = QtGui.QIcon(panel.icon_path(icon_name))
        if not actions:
            return  # toolbar not built yet: try again at the next check
        for action in actions:
            action.setIcon(icon)
            action.setText(tr(menu))
            action.setToolTip(tr(tip))
            action.setStatusTip(tr(tip))
        self._shown = status

    def Activated(self):
        session = start()
        path, status = lock_target()
        if path is None:
            return
        if status in (locks.MINE, session_mod.PENDING):
            session.release(path)
        elif status == locks.OTHER:
            session.edit(path)  # offers: ask for it, open read-only, take the lock
        else:
            session.edit(path)
        self._shown = "unset"


class ReleasePart(_Command):
    icon = "release"
    menu = "Release part"
    tip = "Release the lock of the active document so others can edit it"

    def IsActive(self):
        doc = App.ActiveDocument
        return bool(doc and doc.FileName and session_mod.get().locks.holds(doc.FileName))

    def Activated(self):
        start().release(App.ActiveDocument.FileName)


class ReleaseAll(_Command):
    icon = "release"
    menu = "Release all my parts"
    tip = "Release every part locked by this FreeCAD (unsaved changes are offered for saving)"

    def IsActive(self):
        return bool(session_mod.get().locks.held)

    def Activated(self):
        session = start()
        for part in list(session.locks.held):
            if not session.release(part):
                break


class SplitDocument(_Command):
    icon = "split"
    menu = "Split into part files..."
    tip = ("One file per part, shared variables in Variables.FCStd and links in Assemblage.FCStd "
           "(the original file is not modified)")

    def IsActive(self):
        doc = App.ActiveDocument
        return bool(doc and doc.FileName)

    def Activated(self):
        from . import split
        split.split_active(start())
        panel.show_panel()


class Settings(_Command):
    icon = "user"
    menu = "My name and options..."
    tip = "Name shown on your locks, read-only protection, boxes in assemblies"

    def Activated(self):
        session = start()
        dialog = SettingsDialog(session, Gui.getMainWindow())
        dialog.exec()


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("CoBench")
        form = QtWidgets.QFormLayout(self)
        self.name = QtWidgets.QLineEdit(session.identity.user)
        form.addRow(tr("Name shown on your locks:"), self.name)
        self.author = QtWidgets.QCheckBox(tr("Also write it as author when FreeCAD saves"))
        self.author.setChecked(prefs.freecad_author() in ("", session.identity.user))
        form.addRow(self.author)
        self.protect = QtWidgets.QCheckBox(tr("Make parts locked by others read-only on this computer"))
        self.protect.setChecked(prefs.protect_files())
        form.addRow(self.protect)
        self.overlay = QtWidgets.QCheckBox(tr("Show locks as coloured boxes in assemblies"))
        self.overlay.setChecked(prefs.show_overlay())
        form.addRow(self.overlay)
        self.picking = QtWidgets.QCheckBox(
            tr("In assemblies, pick whole parts and show a small menu (instead of selecting faces)"))
        self.picking.setChecked(prefs.assembly_picking())
        form.addRow(self.picking)
        self.strict = QtWidgets.QCheckBox(tr("Refuse changes to parts I have not locked"))
        self.strict.setChecked(prefs.strict())
        form.addRow(self.strict)
        self.reload = QtWidgets.QCheckBox(tr("Reload parts saved by others automatically"))
        self.reload.setChecked(prefs.auto_reload())
        form.addRow(self.reload)
        self.notifications = QtWidgets.QCheckBox(tr("Notify me when a part is locked, released or asked for"))
        self.notifications.setChecked(prefs.notifications())
        form.addRow(self.notifications)
        self.hide = QtWidgets.QCheckBox(tr("Hide from the tree the files an assembly loads"))
        self.hide.setChecked(prefs.hide_dependencies())
        form.addRow(self.hide)
        self.offline = QtWidgets.QCheckBox(tr("Refuse to lock a part when this computer is offline"))
        self.offline.setChecked(prefs.offline_check())
        form.addRow(self.offline)
        self.delay = QtWidgets.QSpinBox()
        self.delay.setRange(1, 600)
        self.delay.setSuffix(" s")
        self.delay.setValue(prefs.sync_delay())
        self.delay.setToolTip(tr("Used when the sync client does not say whether the lock was sent"))
        form.addRow(tr("A lock counts as sent after staying online:"), self.delay)
        host = QtWidgets.QLabel(tr("Computer: {host}", host=session.identity.host))
        host.setEnabled(False)
        form.addRow(host)
        form.addRow(self._locking_box())
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    # -- where the locks of the project live ---------------------------------
    def _locking_box(self):
        project = self.session.project
        box = QtWidgets.QGroupBox(tr("Locks of the project {name}", name=project.name) if project
                                  else tr("Locks of the project"))
        layout = QtWidgets.QFormLayout(box)
        self.store_files = QtWidgets.QRadioButton(tr("Lock files next to the parts (any shared folder)"))
        self.store_supabase = QtWidgets.QRadioButton(tr("Supabase database (real time)"))
        config = project.locking if project else {"store": "files"}
        self.store_supabase.setChecked(config.get("store") == "supabase")
        self.store_files.setChecked(config.get("store") != "supabase")
        layout.addRow(self.store_files)
        layout.addRow(self.store_supabase)
        self.url = QtWidgets.QLineEdit(config.get("url", ""))
        self.url.setPlaceholderText("https://xxxxxxxx.supabase.co")
        self.key = QtWidgets.QLineEdit(config.get("key", ""))
        self.key.setPlaceholderText("sb_publishable_... / eyJ...")
        self.key.setToolTip(tr("The anon / publishable key, never the service_role / secret key"))
        layout.addRow(tr("Project URL:"), self.url)
        layout.addRow(tr("Public key:"), self.key)
        row = QtWidgets.QHBoxLayout()
        test = QtWidgets.QPushButton(tr("Test"))
        test.clicked.connect(self._test)
        script = QtWidgets.QPushButton(tr("Copy the SQL script"))
        script.setToolTip(tr("Paste it once in Supabase > SQL Editor, then Run"))
        script.clicked.connect(self._copy_script)
        row.addWidget(test)
        row.addWidget(script)
        row.addStretch(1)
        layout.addRow(row)
        hint = QtWidgets.QLabel(tr("Saved in cobench.json: everybody opening the project uses the same "
                                   "locks. The part files stay in the shared folder."))
        hint.setWordWrap(True)
        hint.setEnabled(False)
        layout.addRow(hint)

        def follow(_on=None):
            on = self.store_supabase.isChecked()
            for widget in (self.url, self.key, test, script):
                widget.setEnabled(on)
        self.store_supabase.toggled.connect(follow)
        follow()
        box.setEnabled(project is not None)
        return box

    def _test(self):
        from ..core import supabase
        problem = supabase.test_connection(self.url.text().strip(), self.key.text().strip())
        if problem:
            QtWidgets.QMessageBox.warning(self, "CoBench", problem)
        else:
            QtWidgets.QMessageBox.information(self, "CoBench", tr("The lock database is ready."))

    def _copy_script(self):
        from ..core import supabase
        with open(supabase.SQL_FILE, "r", encoding="utf-8") as stream:
            QtWidgets.QApplication.clipboard().setText(stream.read())
        QtWidgets.QMessageBox.information(
            self, "CoBench", tr("SQL script copied. In Supabase, open SQL Editor, paste it and click Run."))

    def _apply_locking(self):
        """False when the change must wait (parts still locked)."""
        project = self.session.project
        if project is None:
            return True
        store = "supabase" if self.store_supabase.isChecked() else "files"
        url, key = self.url.text().strip().rstrip("/"), self.key.text().strip()
        current = project.locking
        if store == current.get("store", "files") and (
                store == "files" or (url == current.get("url") and key == current.get("key"))):
            return True
        if store == "supabase":
            from ..core import supabase
            problem = supabase.test_connection(url, key)
            if problem:
                QtWidgets.QMessageBox.warning(self, "CoBench", problem)
                return False
        if self.session.locks.held:
            QtWidgets.QMessageBox.warning(
                self, "CoBench", tr("Release your parts before changing where the locks are kept."))
            return False
        project.set_locking(store, url, key)
        self.session.use_project_locking()
        return True

    def accept(self):
        if not self._apply_locking():
            return
        name = self.name.text().strip()
        if name and name != self.session.identity.user:
            self.session.set_user(name)
        if name and self.author.isChecked():
            prefs.set_freecad_author(name)
        prefs.set_protect_files(self.protect.isChecked())
        prefs.set_show_overlay(self.overlay.isChecked())
        prefs.set_assembly_picking(self.picking.isChecked())
        prefs.set_strict(self.strict.isChecked())
        prefs.set_auto_reload(self.reload.isChecked())
        prefs.set_notifications(self.notifications.isChecked())
        prefs.set_hide_dependencies(self.hide.isChecked())
        prefs.set_offline_check(self.offline.isChecked())
        prefs.set_sync_delay(self.delay.value())
        if not self.protect.isChecked() and self.session.project:
            for part in self.session.project.parts():
                if locks.is_read_only(part):
                    locks.set_read_only(part, False)
        self.session.changed()
        super().accept()


COMMANDS = {
    "CoBench_ShowPanel": ShowPanel(),
    "CoBench_OpenProject": OpenProject(),
    "CoBench_OpenAssembly": OpenAssembly(),
    "CoBench_SetAssembly": SetAssembly(),
    "CoBench_Lock": LockToggle(),
    "CoBench_EditPart": EditPart(),
    "CoBench_ReleasePart": ReleasePart(),
    "CoBench_ReleaseAll": ReleaseAll(),
    "CoBench_SplitDocument": SplitDocument(),
    "CoBench_ShowGraph": ShowGraph(),
    "CoBench_AskForPart": AskForPart(),
    "CoBench_Settings": Settings(),
}

# One toolbar per group: FreeCAD draws separators very faintly with some themes,
# separate toolbars are clearly apart (and each can be moved).
TOOLBARS = [
    ("CoBench", ["CoBench_ShowPanel", "CoBench_OpenProject"]),
    ("CoBench views", ["CoBench_OpenAssembly", "CoBench_ShowGraph"]),
    ("CoBench lock", ["CoBench_Lock"]),
    ("CoBench tools", ["CoBench_SplitDocument"]),
]
MENU = ["CoBench_ShowPanel", "CoBench_OpenProject", "CoBench_OpenAssembly", "CoBench_SetAssembly",
        "CoBench_ShowGraph", "Separator", "CoBench_EditPart", "CoBench_AskForPart",
        "CoBench_ReleasePart", "CoBench_ReleaseAll",
        "Separator", "CoBench_SplitDocument", "Separator", "CoBench_Settings"]


def register():
    for name, command in COMMANDS.items():
        Gui.addCommand(name, command)


def context_items():
    """Commands for the right-click menu of the 3D view and the tree."""
    session = session_mod.get()
    items = []
    selected = assembly.selected_part(session)
    if selected:
        items.append("CoBench_EditPart")
        if session.state(selected).status == locks.OTHER:
            items.append("CoBench_AskForPart")
    doc = App.ActiveDocument
    if doc and doc.FileName and session.locks.holds(doc.FileName):
        items.append("CoBench_ReleasePart")
    return items

