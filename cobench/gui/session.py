# SPDX-License-Identifier: LGPL-2.1-or-later
"""One CoBench session per FreeCAD run.

The session owns the locks taken by this FreeCAD, watches documents being
opened, saved and closed in every workbench, and tells the panel and the
assembly overlay when something changes.
"""

import atexit
import os
import uuid

import FreeCAD as App
import FreeCADGui as Gui

from ..core import locks
from ..core.identity import Identity
from ..core.project import Project, find_root
from ..i18n import tr
from . import prefs
from .qt import QtCore, QtWidgets

_session = None


def get():
    """The session of this FreeCAD run, created on first use."""
    global _session
    if _session is None:
        _session = Session()
    return _session


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _mtime(path):
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def main_window():
    try:
        return Gui.getMainWindow()
    except Exception:
        return None


def status_message(text, msecs=8000):
    window = main_window()
    if window is not None:
        window.statusBar().showMessage(text, msecs)
    App.Console.PrintMessage("CoBench: %s\n" % text)


def later(function):
    """Run after the current FreeCAD call returns (never inside a save)."""
    QtCore.QTimer.singleShot(0, function)


def who(info):
    """Short name of a lock holder for sentences: "Bob (pc-bob)"."""
    if info is None:
        return "?"
    return "%s (%s)" % (info.user, info.host)


def lock_time(info):
    since = info.since_datetime() if info else None
    return since.astimezone().strftime("%d/%m/%Y %H:%M") if since else "?"


def describe_lock(info):
    if info is None:
        return ""
    since = info.since_datetime()
    when = since.astimezone().strftime("%d/%m/%Y %H:%M") if since else "?"
    return tr("{user} on {host}, since {when}", user=info.user, host=info.host, when=when)


class Session:
    def __init__(self):
        version = ".".join(App.Version()[:3])
        self.session_id = uuid.uuid4().hex
        self.identity = Identity(prefs.user_name())
        self.locks = locks.LockManager(self.identity, self.session_id, "FreeCAD " + version)
        self.project = None
        self.loaded = {}        # normalised path -> mtime when loaded or saved by us
        self.listeners = []     # callables run when locks or documents change
        self.recompute_listeners = []
        self.observer = _DocumentObserver(self)
        App.addDocumentObserver(self.observer)
        for doc in App.listDocuments().values():
            self.remember(doc)
        atexit.register(self.shutdown)
        last = prefs.last_project()
        if last and os.path.isdir(last):
            self.project = Project(last)

    # -- notifications -----------------------------------------------------
    def changed(self):
        for listener in list(self.listeners):
            try:
                listener()
            except Exception as exc:  # a closed widget must not break FreeCAD
                App.Console.PrintWarning("CoBench: %s\n" % exc)

    # -- identity and project ----------------------------------------------
    def set_user(self, name):
        prefs.set_user_name(name)
        old = self.identity
        self.identity = Identity(name)
        self.locks.identity = self.identity
        # Locks already held were written with the old name: rewrite them.
        for part in list(self.locks.held):
            info = locks.LockInfo.read(locks.lock_path(part))
            if info is not None and info.session == self.session_id and info.user == old.user:
                self.locks.force(part)
        self.changed()

    def open_project(self, folder):
        root = find_root(folder) or folder
        self.project = Project(root)
        if not os.path.exists(self.project.project_file):
            suggestion = self.project.suggest_assembly()
            if suggestion:
                self.project.assembly = self.project.rel(suggestion)
            try:
                self.project.save()
            except OSError as exc:
                App.Console.PrintWarning("CoBench: %s\n" % exc)
        prefs.set_last_project(self.project.root)
        self.changed()
        return self.project

    def managed(self, path):
        """True if CoBench handles locks for this file."""
        if not path or not path.lower().endswith(".fcstd"):
            return False
        if self.project and self.project.contains(path):
            return True
        return find_root(path) is not None

    # -- documents -----------------------------------------------------------
    def remember(self, doc):
        path = getattr(doc, "FileName", "")
        if path and os.path.exists(path):
            self.loaded[_norm(path)] = _mtime(path)

    def find_document(self, path):
        target = _norm(path)
        for doc in App.listDocuments().values():
            if doc.FileName and _norm(doc.FileName) == target:
                return doc
        return None

    def changed_on_disk(self, doc):
        """True if someone else saved the file since we loaded it."""
        known = self.loaded.get(_norm(doc.FileName))
        current = _mtime(doc.FileName)
        return known is not None and current is not None and current != known

    @staticmethod
    def is_modified(doc):
        try:
            return bool(Gui.getDocument(doc.Name).Modified)
        except Exception:
            return False

    def _show(self, doc):
        """Make the document the active tab, creating a 3D view if it has none."""
        App.setActiveDocument(doc.Name)
        gdoc = Gui.getDocument(doc.Name)
        try:
            has_view = bool(gdoc.mdiViewsOfType("Gui::View3DInventor"))
        except Exception:
            has_view = True
        if not has_view:
            try:
                gdoc.createView("Gui::View3DInventor")
            except Exception:
                Gui.runCommand("Std_ViewCreate", 0)
        window = main_window()
        area = window.findChild(QtWidgets.QMdiArea) if window is not None else None
        if area is None:
            return
        for sub in area.subWindowList():
            title = sub.windowTitle().replace("[*]", "")
            if title == doc.Label or title.startswith(doc.Label + " : "):
                area.setActiveSubWindow(sub)
                break

    def _load(self, path, reload_if_changed=True):
        """Open the document, or bring back the loaded copy (reloaded if stale)."""
        doc = self.find_document(path)
        if doc is not None and getattr(doc, "Partial", False):
            App.closeDocument(doc.Name)
            doc = None
        if doc is not None and reload_if_changed and self.changed_on_disk(doc):
            name = os.path.basename(path)
            if self.is_modified(doc):
                answer = QtWidgets.QMessageBox.warning(
                    main_window(), "CoBench",
                    tr("{name} was saved by someone else after you opened it, and your copy "
                       "has unsaved changes.\n\nReload the file and lose your changes?", name=name),
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No)
                if answer != QtWidgets.QMessageBox.Yes:
                    return doc
            App.closeDocument(doc.Name)
            doc = None
            status_message(tr("{name} reloaded: it had changed on disk.", name=name))
        if doc is None:
            doc = App.openDocument(path)
            self.remember(doc)
        self._show(doc)
        return doc

    # -- actions -------------------------------------------------------------
    def edit(self, path):
        """Lock the part and open it for editing.  Returns the document or None."""
        name = os.path.basename(path)
        state = self.locks.state(path)
        if state.status == locks.OTHER:
            box = QtWidgets.QMessageBox(main_window())
            box.setIcon(QtWidgets.QMessageBox.Warning)
            box.setWindowTitle("CoBench")
            box.setText(tr("{name} is being edited by {who}.", name=name, who=who(state.info)))
            box.setInformativeText(tr("Locked since {when}.", when=lock_time(state.info)) + "\n\n" + tr("You can open it read-only, or take the lock if you are sure "
                                      "that person no longer works on it (their unsaved work would "
                                      "be lost when they save)."))
            view = box.addButton(tr("Open read-only"), QtWidgets.QMessageBox.AcceptRole)
            take = box.addButton(tr("Take the lock"), QtWidgets.QMessageBox.DestructiveRole)
            box.addButton(QtWidgets.QMessageBox.Cancel)
            box.setDefaultButton(view)
            box.exec()
            if box.clickedButton() is view:
                return self.view(path)
            if box.clickedButton() is not take:
                return None
            state = self.locks.force(path)
        else:
            state = self.locks.acquire(path)
        if state.status != locks.MINE:
            QtWidgets.QMessageBox.warning(
                main_window(), "CoBench",
                tr("{name} was locked by {who} a moment ago.", name=name, who=who(state.info)))
            self.changed()
            return None
        locks.set_read_only(path, False)
        try:
            doc = self._load(path)
        except Exception:
            self.locks.release(path)
            self.changed()
            raise
        status_message(tr("{name} locked: you can edit it.", name=name))
        self.changed()
        return doc

    def view(self, path):
        """Open without locking."""
        was_open = self.find_document(path) is not None
        doc = self._load(path)
        state = self.locks.state(path)
        if state.status == locks.OTHER and was_open:
            status_message(tr("{name} opened read-only: {who} is editing it.",
                              name=os.path.basename(path), who=who(state.info)))
        self.changed()
        return doc

    def release(self, path, ask=True):
        """Give the part back.  Offers to save unsaved changes first."""
        doc = self.find_document(path)
        if ask and doc is not None and self.is_modified(doc):
            answer = QtWidgets.QMessageBox.question(
                main_window(), "CoBench",
                tr("{name} has unsaved changes. Save before releasing it?", name=os.path.basename(path)),
                QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Save)
            if answer == QtWidgets.QMessageBox.Cancel:
                return False
            if answer == QtWidgets.QMessageBox.Save:
                doc.save()
        self.locks.release(path)
        status_message(tr("{name} released.", name=os.path.basename(path)))
        self.changed()
        return True

    def take_over(self, path):
        state = self.locks.state(path)
        if state.status == locks.OTHER:
            answer = QtWidgets.QMessageBox.warning(
                main_window(), "CoBench",
                tr("Take the lock of {name} from {who}?\n\nOnly do this if that person no longer "
                   "works on it, for example after a crash.",
                   name=os.path.basename(path), who=who(state.info)),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
            if answer != QtWidgets.QMessageBox.Yes:
                return False
        self.locks.force(path)
        locks.set_read_only(path, False)
        self.changed()
        return True

    def apply_protection(self, path, state):
        """Read-only on disk while someone else holds the part."""
        if not prefs.protect_files():
            if locks.is_read_only(path) and state.status != locks.OTHER:
                locks.set_read_only(path, False)
            return
        try:
            locks.set_read_only(path, state.status == locks.OTHER)
        except OSError:
            pass

    def shutdown(self):
        try:
            self.locks.release_all()
        except Exception:
            pass

    # -- document events -----------------------------------------------------
    def on_opened(self, doc):
        self.remember(doc)
        path = doc.FileName
        if self.managed(path):
            state = self.locks.state(path)
            if state.status == locks.OTHER:
                later(lambda: status_message(
                    tr("{name} opened read-only: {who} is editing it.",
                       name=os.path.basename(path), who=who(state.info))))
            self.changed()

    def on_closed(self, doc):
        path = getattr(doc, "FileName", "")
        if not path:
            return
        self.loaded.pop(_norm(path), None)
        if self.locks.holds(path):
            self.locks.release(path)
            later(lambda: status_message(tr("{name} released.", name=os.path.basename(path))))
        later(self.changed)

    def on_saving(self, doc, path):
        if not self.managed(path):
            return
        name = os.path.basename(path)
        state = self.locks.state(path)
        stale = os.path.exists(path) and self.changed_on_disk(doc)
        if state.status == locks.OTHER:
            holder = who(state.info)
            later(lambda: QtWidgets.QMessageBox.warning(
                main_window(), "CoBench",
                tr("You saved {name} while {who} holds it. If the save succeeded, their next save "
                   "will overwrite yours (or yours overwrote theirs). Agree with them on which "
                   "version to keep.", name=name, who=holder)))
            return
        if state.status in (locks.FREE, locks.ORPHAN):
            locks.set_read_only(path, False)
            self.locks.acquire(path)
            later(lambda: status_message(tr("{name} saved and locked: release it when you are done.",
                                            name=name)))
        if stale:
            later(lambda: QtWidgets.QMessageBox.warning(
                main_window(), "CoBench",
                tr("{name} had been saved by someone else after you opened it. Your save replaced "
                   "their version.", name=name)))

    def on_saved(self, doc, path):
        self.loaded[_norm(path)] = _mtime(path)
        later(self.changed)

    def on_recomputed(self, doc):
        for listener in list(self.recompute_listeners):
            try:
                listener(doc)
            except Exception as exc:
                App.Console.PrintWarning("CoBench: %s\n" % exc)


class _DocumentObserver:
    """FreeCAD calls these methods by name (App.addDocumentObserver)."""

    def __init__(self, session):
        self.session = session

    def _safe(self, method, *args):
        try:
            method(*args)
        except Exception as exc:
            App.Console.PrintWarning("CoBench: %s\n" % exc)

    def slotCreatedDocument(self, doc):
        # FileName may still be empty while the file is being read.
        later(lambda: self._safe(self.session.on_opened, doc) if _alive(doc) else None)

    def slotFinishRestoreDocument(self, doc):
        self._safe(self.session.remember, doc)

    def slotDeletedDocument(self, doc):
        self._safe(self.session.on_closed, doc)

    def slotStartSaveDocument(self, doc, path):
        self._safe(self.session.on_saving, doc, path)

    def slotFinishSaveDocument(self, doc, path):
        self._safe(self.session.on_saved, doc, path)

    def slotRecomputedDocument(self, doc):
        self._safe(self.session.on_recomputed, doc)


def _alive(doc):
    try:
        return doc.Name in App.listDocuments()
    except Exception:
        return False
