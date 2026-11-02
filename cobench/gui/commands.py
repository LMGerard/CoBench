# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD commands of the CoBench workbench."""

import FreeCAD as App
import FreeCADGui as Gui

from ..core import locks
from ..i18n import tr
from . import assembly, panel, prefs, session as session_mod
from .qt import QtWidgets

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
        host = QtWidgets.QLabel(tr("Computer: {host}", host=session.identity.host))
        host.setEnabled(False)
        form.addRow(host)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def accept(self):
        name = self.name.text().strip()
        if name and name != self.session.identity.user:
            self.session.set_user(name)
        if name and self.author.isChecked():
            prefs.set_freecad_author(name)
        prefs.set_protect_files(self.protect.isChecked())
        prefs.set_show_overlay(self.overlay.isChecked())
        prefs.set_strict(self.strict.isChecked())
        prefs.set_auto_reload(self.reload.isChecked())
        prefs.set_notifications(self.notifications.isChecked())
        prefs.set_hide_dependencies(self.hide.isChecked())
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
    "CoBench_EditPart": EditPart(),
    "CoBench_ReleasePart": ReleasePart(),
    "CoBench_ReleaseAll": ReleaseAll(),
    "CoBench_SplitDocument": SplitDocument(),
    "CoBench_ShowGraph": ShowGraph(),
    "CoBench_AskForPart": AskForPart(),
    "CoBench_Settings": Settings(),
}

TOOLBAR = ["CoBench_ShowPanel", "CoBench_OpenProject", "CoBench_OpenAssembly", "CoBench_ShowGraph",
           "CoBench_EditPart", "CoBench_ReleasePart", "CoBench_SplitDocument"]
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

