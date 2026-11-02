# SPDX-License-Identifier: LGPL-2.1-or-later
"""One CoBench session per FreeCAD run.

The session starts with FreeCAD, whatever the workbench.  It owns the locks
taken by this FreeCAD and, every few seconds, looks at the project folder:

* lock changes of the others (notifications, crossed locks);
* parts saved by others, reloaded once the file is stable;
* requests to release a part.

It also refuses changes to project files that are not locked by this
FreeCAD: entering edit mode is stopped before the task panel opens, and any
other change is undone as soon as its command ends.
"""

import atexit
import contextlib
import datetime
import os
import threading
import time
import uuid

import FreeCAD as App
import FreeCADGui as Gui

from ..core import fcstd, locks, requests, stamps, supabase, syncstate
from ..core.identity import Identity
from ..core.project import Project, find_root
from ..i18n import tr
from . import prefs
from .qt import QtCore, QtWidgets

_session = None

PENDING = "pending"   # my lock, not sent by the sync client yet

# Property changes that never need a lock (showing/hiding a part).
FREE_PROPERTIES = {"Visibility"}


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


def later(function, msecs=0):
    """Run after the current FreeCAD call returns (never inside a save)."""
    QtCore.QTimer.singleShot(msecs, function)


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
    return tr("{user} on {host}, since {when}", user=info.user, host=info.host, when=lock_time(info))


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0]


class Connectivity:
    """Is the computer online?  Checked in a thread so FreeCAD never waits."""

    def __init__(self):
        self.value = True
        self.checked = 0.0
        self._running = False

    def poll(self, max_age=4.0):
        """Last known answer; starts a new check when it is older than max_age."""
        if not self._running and time.monotonic() - self.checked > max_age:
            self._running = True
            threading.Thread(target=self._run, daemon=True).start()
        return self.value

    def _run(self):
        try:
            self.value = syncstate.online()
        finally:
            self.checked = time.monotonic()
            self._running = False

    def now(self):
        """Ask right away (for an action the user just asked for)."""
        self.value = syncstate.online()
        self.checked = time.monotonic()
        return self.value


class Session:
    def __init__(self):
        version = ".".join(App.Version()[:3])
        self.session_id = uuid.uuid4().hex
        self.identity = Identity(prefs.user_name())
        self.app_name = "FreeCAD " + version
        self.locks = locks.LockManager(self.identity, self.session_id, self.app_name)
        self.project = None
        self.parts = []           # project parts found at the last tick
        self.states = {}          # part path -> LockState at the last tick
        self.loaded = {}          # normalised path -> mtime when loaded or saved by us
        self.shown = set()        # normalised paths opened on purpose (kept in the tree)
        self.listeners = []       # callables run when locks or documents change
        self.recompute_listeners = []
        self.activity = []        # (time, text), newest last
        self._pending_reload = {}  # normalised path -> mtime seen at the previous tick
        self._newer_told = {}     # normalised path -> mtime already reported as newer
        self._crossed_told = set()
        self._requests_seen = set()
        self._last_holder = {}    # part path -> user name of the last other holder seen
        self._quiet = 0
        self._tx = {}             # document name -> {"bad": bool, "checked": bool}
        self._recomputing = set()
        self._last_refusal = {}
        self.connectivity = Connectivity()
        self._lock_taken = {}     # part path -> (monotonic time, lock seen online since then)
        self._lock_sent = set()   # part paths whose lock reached the server
        self._offline_told = set()
        self._waiting = {}        # normalised path -> (path, sha1, size): locked, waiting for the file
        self._store_error = ""
        self.observer = _DocumentObserver(self)
        App.addDocumentObserver(self.observer)
        self.gui_observer = _GuiObserver(self)
        try:
            Gui.addDocumentObserver(self.gui_observer)
        except Exception:
            pass
        for doc in App.listDocuments().values():
            self.remember(doc)
        atexit.register(self.shutdown)
        last = prefs.last_project()
        if last and os.path.isdir(last):
            self.project = Project(last)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(prefs.refresh_seconds() * 1000)
        self.use_project_locking()
        later(self.tick, 500)

    # -- notifications -----------------------------------------------------
    def changed(self):
        for listener in list(self.listeners):
            try:
                listener()
            except Exception as exc:  # a closed widget must not break FreeCAD
                App.Console.PrintWarning("CoBench: %s\n" % exc)

    def notify(self, text, warning=False):
        self.activity.append((datetime.datetime.now(), text))
        del self.activity[:-50]
        window = main_window()
        if window is not None:
            window.statusBar().showMessage(text, 10000)
        if not prefs.notifications():
            App.Console.PrintMessage("CoBench: %s\n" % text)
            return
        if warning:
            App.Console.PrintWarning("CoBench: %s\n" % text)
        elif hasattr(App.Console, "PrintNotification"):
            App.Console.PrintNotification("CoBench: %s\n" % text)
        else:
            App.Console.PrintMessage("CoBench: %s\n" % text)

    @contextlib.contextmanager
    def quiet(self):
        """CoBench's own changes: no blocking, no reload."""
        self._quiet += 1
        try:
            yield
        finally:
            self._quiet -= 1

    # -- identity and project ----------------------------------------------
    def set_user(self, name):
        prefs.set_user_name(name)
        old = self.identity
        self.identity = Identity(name)
        self.locks.identity = self.identity
        # Locks already held were written with the old name: rewrite them.
        for part in list(self.locks.held):
            info = self.locks.state(part).info
            if info is not None and info.session == self.session_id and info.user == old.user:
                self.locks.force(part)
        self.tick()

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
        self.states = {}
        self.use_project_locking()
        self.tick()
        return self.project

    # -- where the locks live ------------------------------------------------
    def store(self):
        """'files' or 'supabase'."""
        return getattr(self.locks, "store", "files")

    def use_project_locking(self):
        """Use the lock store chosen for the project (files or Supabase).

        Refused while this FreeCAD holds locks in the other store.
        """
        config = self.project.locking if self.project else {"store": "files"}
        wanted = config.get("store", "files")
        if wanted == "supabase" and not (config.get("url") and config.get("key") and config.get("id")):
            wanted = "files"
        if wanted == self.store() and (wanted == "files" or (
                self.locks.client.url == config.get("url") and self.locks.project_id == config.get("id"))):
            return True
        if self.locks.held:
            self.notify(tr("Release your parts before changing where the locks are kept."), warning=True)
            return False
        if wanted == "supabase":
            manager = supabase.SupabaseLockManager(
                self.identity, self.session_id, self.app_name, config["url"], config["key"], config["id"],
                self.project.rel)
            manager.refresh_async()
            interval = min(prefs.refresh_seconds(), 2)
        else:
            manager = locks.LockManager(self.identity, self.session_id, self.app_name)
            interval = prefs.refresh_seconds()
        self.locks = manager
        self._lock_sent.clear()
        self._lock_taken.clear()
        self._waiting.clear()
        self.timer.setInterval(interval * 1000)
        self.states = {}
        return True

    def managed(self, path):
        """True if CoBench handles locks for this file."""
        if not path or not path.lower().endswith(".fcstd"):
            return False
        if self.project and self.project.contains(path):
            return True
        return find_root(path) is not None

    def editable(self, doc):
        """False for a project file this FreeCAD has not locked."""
        path = getattr(doc, "FileName", "")
        if not path or not self.managed(path):
            return True
        return self.locks.state(path).status == locks.MINE

    def state(self, path):
        return self.states.get(path) or self.locks.state(path)

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

    def dependents(self, path):
        """Open documents that use the file (assemblies, parts reading Variables)."""
        target = _norm(path)
        users = []
        for doc in App.listDocuments().values():
            if not doc.FileName or _norm(doc.FileName) == target:
                continue
            try:
                deps = doc.getDependentDocuments(False)
            except Exception:
                deps = []
            if any(d.FileName and _norm(d.FileName) == target for d in deps):
                users.append(doc)
        return users

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

    def _reopen(self, doc, show):
        """Close and open again from disk; dependents are recomputed."""
        path = doc.FileName
        users = self.dependents(path)
        active = App.ActiveDocument.Name if App.ActiveDocument else None
        with self.quiet():
            App.closeDocument(doc.Name)
            new = App.openDocument(path)
            self.remember(new)
            for user in users:
                try:
                    user.recompute()
                except Exception:
                    pass
        if show:
            self._show(new)
        elif active and active in App.listDocuments():
            self._show(App.getDocument(active))
        return new

    def _load(self, path, reload_if_changed=True):
        """Open the document, or bring back the loaded copy (reloaded if stale)."""
        self.shown.add(_norm(path))
        doc = self.find_document(path)
        if doc is not None and getattr(doc, "Partial", False):
            return self._reopen(doc, True)
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
                    self._show(doc)
                    return doc
            status_message(tr("{name} reloaded: it had changed on disk.", name=name))
            return self._reopen(doc, True)
        if doc is None:
            with self.quiet():
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
            box.setInformativeText(
                tr("Locked since {when}.", when=lock_time(state.info)) + "\n\n"
                + tr("You can ask for it, open it read-only, or take the lock if you are sure that "
                     "person no longer works on it (their unsaved work would be lost when they save)."))
            ask = box.addButton(tr("Ask for it"), QtWidgets.QMessageBox.ActionRole)
            view = box.addButton(tr("Open read-only"), QtWidgets.QMessageBox.AcceptRole)
            take = box.addButton(tr("Take the lock"), QtWidgets.QMessageBox.DestructiveRole)
            box.addButton(QtWidgets.QMessageBox.Cancel)
            box.setDefaultButton(ask)
            box.exec()
            if box.clickedButton() is ask:
                self.ask_for(path)
                return None
            if box.clickedButton() is view:
                return self.view(path)
            if box.clickedButton() is not take:
                return None
            state = self._store_call(self.locks.force, path)
        else:
            if self.store() == "files" and state.status == locks.FREE and not self._may_lock_offline(name):
                return None
            state = self._store_call(self.locks.acquire, path)
        if state is None:
            return None
        if state.status != locks.MINE:
            QtWidgets.QMessageBox.warning(
                main_window(), "CoBench",
                tr("{name} was locked by {who} a moment ago.", name=name, who=who(state.info)))
            self.tick()
            return None
        locks.set_read_only(path, False)
        answer = self._copy_is_latest(path)
        if answer == "wait":
            self.tick()
            return None
        if not answer:
            self.locks.release(path)
            self.tick()
            return None
        try:
            doc = self._load(path)
        except Exception:
            self.locks.release(path)
            self.tick()
            raise
        status_message(tr("{name} locked: you can edit it.", name=name))
        self.tick()
        return doc

    def _store_call(self, method, path):
        """Take or force a lock; None (after telling the user) when the store cannot be used."""
        try:
            return method(path)
        except locks.Offline:
            QtWidgets.QMessageBox.warning(
                main_window(), "CoBench",
                tr("Cannot reach the lock database (offline?): {name} was not locked.",
                   name=os.path.basename(path)))
        except supabase.StoreError as exc:
            QtWidgets.QMessageBox.warning(main_window(), "CoBench", tr("Lock database: {error}", error=str(exc)))
        self.tick()
        return None

    def _may_lock_offline(self, name):
        """True when online, or when the user takes the part anyway."""
        if not prefs.offline_check() or self.connectivity.now():
            return True
        box = QtWidgets.QMessageBox(main_window())
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle("CoBench")
        box.setText(tr("This computer is offline: the others will not see your lock on {name} "
                       "until it is back online.", name=name))
        box.setInformativeText(tr("Someone could take the same part meanwhile. Lock your parts "
                                  "before going offline."))
        anyway = box.addButton(tr("Take it anyway"), QtWidgets.QMessageBox.DestructiveRole)
        box.addButton(QtWidgets.QMessageBox.Cancel)
        box.exec()
        return box.clickedButton() is anyway

    def _copy_is_latest(self, path):
        """Warn when the last saved version of the part has not arrived yet.

        True: go on.  False: give the part back.  "wait" (Supabase): keep the
        lock and open the part by itself once the right file is there.
        """
        name = os.path.basename(path)
        if syncstate.file_state(path) == syncstate.CLOUD_ONLY:
            status_message(tr("{name} is only in the cloud: it is being downloaded.", name=name))
        if self.store() == "supabase":
            return self._database_version_check(path)
        try:
            stamp = stamps.newer_elsewhere(path)
        except OSError:
            stamp = None
        if stamp is None:
            return True
        saved = locks.parse_iso(stamp.saved)
        when = saved.astimezone().strftime("%d/%m/%Y %H:%M") if saved else "?"
        box = QtWidgets.QMessageBox(main_window())
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle("CoBench")
        box.setText(tr("The last version of {name}, saved by {user} on {when}, has not arrived on "
                       "this computer yet.", name=name, user=stamp.user, when=when))
        box.setInformativeText(tr("Wait for the sync, then edit it again. If you edit this copy, "
                                  "the other version will be lost."))
        wait = box.addButton(tr("Wait"), QtWidgets.QMessageBox.AcceptRole)
        box.addButton(tr("Edit this copy anyway"), QtWidgets.QMessageBox.DestructiveRole)
        box.setDefaultButton(wait)
        box.exec()
        return box.clickedButton() is not wait

    def _database_version_check(self, path):
        version = self.locks.version(path)
        if not version or not version.get("sha1") or self._is_version(path, version):
            return True
        name = os.path.basename(path)
        user = version.get("saved_by") or "?"
        box = QtWidgets.QMessageBox(main_window())
        box.setIcon(QtWidgets.QMessageBox.Information)
        box.setWindowTitle("CoBench")
        box.setText(tr("The last version of {name}, saved by {user}, has not arrived on this computer yet.",
                       name=name, user=user))
        box.setInformativeText(tr("The part stays locked for you: CoBench opens it as soon as the file "
                                  "has arrived. If you edit this copy, the other version will be lost."))
        wait = box.addButton(tr("Wait"), QtWidgets.QMessageBox.AcceptRole)
        anyway = box.addButton(tr("Edit this copy anyway"), QtWidgets.QMessageBox.DestructiveRole)
        box.addButton(QtWidgets.QMessageBox.Cancel)
        box.setDefaultButton(wait)
        box.exec()
        if box.clickedButton() is wait:
            self._waiting[_norm(path)] = (path, version.get("sha1"), version.get("size"))
            status_message(tr("{name} locked: waiting for the last version.", name=name))
            return "wait"
        return box.clickedButton() is anyway

    @staticmethod
    def _is_version(path, version):
        """True when the local file is this version (or was saved after it)."""
        try:
            size = os.path.getsize(path)
            if size == int(version.get("size") or -1) and stamps.fingerprint(path) == version.get("sha1"):
                return True
            saved = locks.parse_iso(str(version.get("saved_at") or ""))
            return saved is not None and os.path.getmtime(path) > saved.timestamp() + 2
        except (OSError, ValueError):
            return False

    def _check_waiting(self):
        for key, (path, sha1, size) in list(self._waiting.items()):
            if not self.locks.holds(path):
                del self._waiting[key]
                continue
            if not self._is_version(path, {"sha1": sha1, "size": size}):
                continue
            del self._waiting[key]
            self.notify(tr("{name} has arrived: opened for editing.", name=_stem(path)))
            later(lambda p=path: self._load(p))

    # -- is my lock sent? ----------------------------------------------------
    def lock_pending(self, path):
        """True while the lock I hold on path may not have reached the others,
        or (Supabase) while waiting for the last version of the file."""
        if not self.locks.holds(path):
            return False
        if _norm(path) in self._waiting:
            return True
        if self.store() == "supabase":
            return False  # the database answered: the others see it
        # locks.held keeps normalised paths (lower case on Windows): compare the same way.
        return _norm(path) not in self._lock_sent

    def waiting_for_file(self, path):
        return _norm(path) in self._waiting

    def _check_lock_sync(self):
        if self.store() != "files":
            return
        held = set(self.locks.held)
        for path in list(self._lock_taken):
            if path not in held:
                self._lock_taken.pop(path, None)
                self._lock_sent.discard(path)
                self._offline_told.discard(path)
        waiting = [p for p in held if p not in self._lock_sent and self.managed(p)]
        if not waiting:
            return
        is_online = self.connectivity.poll()
        names = {_norm(p): _stem(p) for p in self.parts}  # held paths are lower case on Windows
        now = time.monotonic()
        for path in waiting:
            since, was_online = self._lock_taken.get(path, (now, True))
            if not is_online:
                was_online = False
                self._lock_taken[path] = (now, False)  # the delay starts again once back online
                if path not in self._offline_told:
                    self._offline_told.add(path)
                    self.notify(tr("Offline: the lock on {name} may not have reached the others yet.",
                                   name=names.get(path, _stem(path))), warning=True)
                continue
            if path not in self._lock_taken or not was_online:
                self._lock_taken[path] = (now, True)
                since = now
            state = syncstate.file_state(locks.lock_path(path))
            sent = state == syncstate.SYNCED or (
                state == syncstate.UNKNOWN and now - since >= prefs.sync_delay())
            if sent:
                self._lock_sent.add(path)
                self.notify(tr("Lock on {name} sent: you can go offline.", name=names.get(path, _stem(path))))

    def view(self, path):
        """Open without locking."""
        was_open = self.find_document(path) is not None
        doc = self._load(path)
        state = self.locks.state(path)
        if state.status == locks.OTHER and was_open:
            status_message(tr("{name} opened read-only: {who} is editing it.",
                              name=os.path.basename(path), who=who(state.info)))
        self.tick()
        return doc

    def open_assembly(self, path):
        """Open an assembly; the parts it loads stay out of the tree."""
        doc = self.view(path)
        later(self.tick, 200)
        return doc

    def release(self, path, ask=True):
        """Give the part back.  Offers to save unsaved changes first."""
        doc = self.find_document(path)
        name = self.display_name(path)
        if ask and doc is not None and self.is_modified(doc):
            answer = QtWidgets.QMessageBox.question(
                main_window(), "CoBench",
                tr("{name} has unsaved changes. Save before releasing it?", name=name),
                QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Save)
            if answer == QtWidgets.QMessageBox.Cancel:
                return False
            if answer == QtWidgets.QMessageBox.Save:
                try:
                    doc.save()
                except Exception as exc:
                    QtWidgets.QMessageBox.warning(
                        main_window(), "CoBench",
                        tr("{name} could not be saved, so it stays locked for you.\n\n{error}",
                           name=name, error=exc))
                    return False
                try:
                    # App's save leaves the window's "modified" mark: clear it like a save from the menu
                    Gui.getDocument(doc.Name).Modified = False
                except Exception:
                    pass
            elif answer == QtWidgets.QMessageBox.Discard:
                # Back to the saved version: others will see exactly that file.
                self._reopen(doc, False)
        if self.store() == "supabase" and self.locks.version_unsent(path):
            QtWidgets.QMessageBox.warning(
                main_window(), "CoBench",
                tr("The new version of {name} could not be recorded in the lock database, so it stays "
                   "locked for you (otherwise others could edit an older copy).\n\n{error}",
                   name=name, error=self.locks.error))
            return False
        try:
            self.locks.release(path)
        except supabase.StoreError as exc:
            QtWidgets.QMessageBox.warning(main_window(), "CoBench", str(exc))
            return False
        request = requests.Request.read(path)
        if request is not None and not self.identity.same_as(request.user, request.host):
            requests.clear(path)
        status_message(tr("{name} released.", name=name))
        self.tick()
        return True

    def display_name(self, path):
        """The file name as written on disk (held paths are lower case on Windows)."""
        target = _norm(path)
        for part in self.parts:
            if _norm(part) == target:
                return os.path.basename(part)
        doc = self.find_document(path)
        if doc is not None and doc.FileName:
            return os.path.basename(doc.FileName)
        return os.path.basename(path)

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
        self.tick()
        return True

    def ask_for(self, path):
        """Ask the holder to release the part."""
        state = self.locks.state(path)
        if state.status != locks.OTHER:
            return False
        requests.write(path, self.identity)
        self.notify(tr("Request sent to {user} for {name}.", user=state.info.user, name=_stem(path)))
        self.tick()
        return True

    def move(self, path, new_path):
        """Move or rename a part and repair every link to it.

        The part and every file linking to it must be free or ours: they are
        locked for the time of the move, saved, and given back.
        """
        project = self.project
        name = os.path.basename(path)
        if os.path.exists(new_path):
            raise RuntimeError(tr("{name} already exists.", name=project.rel(new_path)))
        graph = project.link_graph(project.parts())
        users = project.used_in(graph).get(path, [])
        blocked = [p for p in [path] + users if self.locks.state(p).status == locks.OTHER]
        if blocked:
            raise RuntimeError(tr("Cannot move {name}: {parts} locked by others.", name=name,
                                  parts=", ".join(_stem(p) for p in blocked)))
        for doc_path in [path] + users:
            doc = self.find_document(doc_path)
            if doc is not None and self.is_modified(doc) and not self.locks.holds(doc_path):
                raise RuntimeError(tr("Save or close {name} first.", name=os.path.basename(doc_path)))
        mine_before = {p for p in [path] + users if self.locks.state(p).status == locks.MINE}
        taken = []
        try:
            for doc_path in [path] + users:
                if doc_path not in mine_before:
                    if self.locks.acquire(doc_path).status != locks.MINE:
                        raise RuntimeError(tr("{name} was locked by someone a moment ago.",
                                              name=os.path.basename(doc_path)))
                    taken.append(doc_path)
                locks.set_read_only(doc_path, False)
            with self.quiet():
                docs = {}
                for doc_path in [path] + users:
                    doc = self.find_document(doc_path)
                    if doc is None:
                        doc = App.openDocument(doc_path, hidden=True)
                        self.remember(doc)
                    docs[doc_path] = doc
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                part_doc = docs[path]
                part_doc.saveAs(new_path)  # FreeCAD relinks the open documents using it
                self.remember(part_doc)
                for user in users:
                    docs[user].save()
                    self.remember(docs[user])
            # The new file was locked by the save; the old one goes away.
            locks.set_read_only(path, False)
            os.remove(path)
            self.locks.release(path)
            requests.clear(path)
            stamps.remove(path)
            if self.store() == "supabase":
                self.locks.forget_version(path)
            project.moved(path, new_path)
            if path in mine_before:
                self.locks.acquire(new_path)
            else:
                self.locks.release(new_path)
            if _norm(path) in self.shown:
                self.shown.discard(_norm(path))
                self.shown.add(_norm(new_path))
        finally:
            for doc_path in taken:
                if doc_path != path:
                    self.locks.release(doc_path)
        self.notify(tr("{old} moved to {new}; {count} files relinked.",
                       old=project.rel(path), new=project.rel(new_path), count=len(users)))
        self.tick()
        return new_path

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

    # -- periodic look at the folder ----------------------------------------
    def tick(self):
        try:
            self._tick()
        except Exception as exc:
            App.Console.PrintWarning("CoBench: %s\n" % exc)
        self.changed()

    def _follow_project_file(self):
        """Someone changed cobench.json (e.g. moved the locks to Supabase): follow."""
        try:
            mtime = os.stat(self.project.project_file).st_mtime_ns
        except OSError:
            return
        if getattr(self, "_project_mtime", None) is None:
            self._project_mtime = mtime
            return
        if mtime != self._project_mtime:
            self._project_mtime = mtime
            before = dict(self.project.locking)
            self.project.load()
            if self.project.locking != before:
                self.use_project_locking()

    def _check_store(self):
        """Tell once about a problem with the lock database, and when it is solved."""
        if self.store() != "supabase":
            return
        error = self.locks.error
        if error and error != self._store_error:
            self.notify(tr("Lock database: {error}", error=error), warning=True)
        elif not error and self._store_error:
            self.notify(tr("Lock database reachable again."))
        self._store_error = error
        self.locks.refresh_async()

    def _tick(self):
        project = self.project
        if project is None:
            self.parts, self.states = [], {}
            return
        self._follow_project_file()
        parts = project.parts()
        previous = self.states
        states = {}
        for path in parts:
            state = self.locks.state(path)
            states[path] = state
            self.apply_protection(path, state)
            if previous:
                self._compare(path, previous.get(path), state)
            if state.status == locks.OTHER and state.info:
                self._last_holder[path] = state.info.user
        self.parts, self.states = parts, states
        self._check_requests(parts, states)
        self._reload_changed()
        self._check_lock_sync()
        self._check_waiting()
        self._check_store()

    def _compare(self, path, before, now):
        name = _stem(path)
        if self.locks.holds(path) and now.status == locks.OTHER:
            key = (path, now.info.since if now.info else "")
            if key not in self._crossed_told:
                self._crossed_told.add(key)
                text = tr("Crossed locks: {who} took {name} at the same time as you. Agree on who "
                          "keeps it before saving.", who=who(now.info), name=name)
                self.notify(text, warning=True)
                later(lambda: QtWidgets.QMessageBox.warning(main_window(), "CoBench", text))
            return
        if before is None:
            return
        if before.status == locks.OTHER and now.status == locks.FREE:
            self.notify(tr("{user} released {name}.", user=before.info.user if before.info else "?",
                           name=name))
        elif before.status == locks.FREE and now.status == locks.OTHER:
            self.notify(tr("{user} took {name}.", user=now.info.user if now.info else "?", name=name))

    def _check_requests(self, parts, states):
        for path in parts:
            request = requests.Request.read(path)
            if request is None:
                continue
            state = states[path]
            mine_request = self.identity.same_as(request.user, request.host)
            if mine_request:
                if request.status == requests.DECLINED:
                    holder = state.info.user if state.info else "?"
                    requests.clear(path)
                    self.notify(tr("{user} keeps {name} for now.", user=holder, name=_stem(path)))
                elif state.status in (locks.FREE, locks.ORPHAN):
                    requests.clear(path)
                    self.notify(tr("{name} is free: you can take it.", name=_stem(path)))
                continue
            if state.status == locks.MINE and request.status == requests.PENDING:
                if request.key not in self._requests_seen:
                    self._requests_seen.add(request.key)
                    later(lambda p=path, r=request: self._answer_request(p, r))

    def _answer_request(self, path, request):
        box = QtWidgets.QMessageBox(main_window())
        box.setIcon(QtWidgets.QMessageBox.Question)
        box.setWindowTitle("CoBench")
        box.setText(tr("{user} would like to edit {name}.", user=request.user, name=_stem(path)))
        give = box.addButton(tr("Release it"), QtWidgets.QMessageBox.AcceptRole)
        box.addButton(tr("Not now"), QtWidgets.QMessageBox.RejectRole)
        box.setDefaultButton(give)
        box.exec()
        if box.clickedButton() is give:
            if self.release(path):
                return
        requests.decline(path, request)
        self.tick()

    def _reload_changed(self):
        """Reload parts saved by others, once the synchronised file is complete."""
        if self._quiet or not prefs.auto_reload():
            return
        for doc in list(App.listDocuments().values()):
            path = doc.FileName
            if not path or not self.project.contains(path) or not self.changed_on_disk(doc):
                self._pending_reload.pop(_norm(path) if path else None, None)
                continue
            key = _norm(path)
            mtime = _mtime(path)
            if self._pending_reload.get(key) != mtime:
                self._pending_reload[key] = mtime  # wait until it stops changing
                continue
            if fcstd.read_part(path).error:
                continue  # still being written
            name = _stem(path)
            if self.is_modified(doc) or self.locks.holds(path):
                if self._newer_told.get(key) != mtime:
                    self._newer_told[key] = mtime
                    self.notify(tr("A newer {name} was saved by someone else; your copy has "
                                   "unsaved changes and was not reloaded.", name=name), warning=True)
                continue
            self._pending_reload.pop(key, None)
            author = fcstd.read_part(path).meta.get("LastModifiedBy") or self._last_holder.get(path, "")
            self._reopen(doc, show=False)
            if author:
                self.notify(tr("{name} updated (saved by {user}).", name=name, user=author))
            else:
                self.notify(tr("{name} updated.", name=name))

    # -- blocking changes to files not locked --------------------------------
    def refuse(self, doc, action=""):
        path = doc.FileName
        name = _stem(path)
        state = self.locks.state(path)
        if state.status == locks.OTHER:
            text = tr("{name} is locked by {who}: it cannot be changed.", name=name, who=who(state.info))
        else:
            text = tr("{name} is not locked: click Edit (CoBench) before changing it.", name=name)
        status_message(text)
        now = datetime.datetime.now()
        last = self._last_refusal.get(path)
        if last is None or (now - last).total_seconds() > 20:
            self._last_refusal[path] = now
            QtWidgets.QMessageBox.information(main_window(), "CoBench", text)

    def on_open_transaction(self, doc, name):
        if self._quiet or not prefs.strict():
            return
        self._tx[doc.Name] = {"bad": False, "checked": False}

    def on_changed(self, obj, prop):
        if self._quiet or prop in FREE_PROPERTIES:
            return
        doc = obj.Document
        if doc.Name in self._recomputing:
            return
        tx = self._tx.get(doc.Name)
        if tx is None or tx["checked"]:
            return
        tx["checked"] = True
        if not self.editable(doc):
            tx["bad"] = True

    def on_commit(self, doc):
        tx = self._tx.pop(doc.Name, None)
        if tx and tx["bad"]:
            later(lambda: self._undo(doc))

    def on_abort(self, doc):
        self._tx.pop(doc.Name, None)

    def _undo(self, doc):
        try:
            with self.quiet():
                doc.undo()
                doc.recompute()
        except Exception as exc:
            App.Console.PrintWarning("CoBench: %s\n" % exc)
        self.refuse(doc)

    def on_undo_redo(self, doc, redo):
        """Ctrl+Z / Ctrl+Y on a file that is not locked: put it back as it was.

        The history is kept: once the part is locked again, Ctrl+Z works again.
        """
        if self._quiet or not prefs.strict() or not _alive(doc) or self.editable(doc):
            return

        def revert():
            if not _alive(doc):
                return
            try:
                with self.quiet():
                    if redo:
                        doc.undo()
                    else:
                        doc.redo()
                    doc.recompute()
            except Exception as exc:
                App.Console.PrintWarning("CoBench: %s\n" % exc)
            self.refuse(doc)
        later(revert)

    def on_in_edit(self, view_provider):
        if self._quiet or not prefs.strict():
            return
        doc = view_provider.Object.Document
        if self.editable(doc):
            return

        def stop():
            with self.quiet():
                try:
                    Gui.Control.closeDialog()
                except Exception:
                    pass
                try:
                    Gui.getDocument(doc.Name).resetEdit()
                except Exception:
                    pass
                try:
                    doc.abortTransaction()
                except Exception:
                    pass
            self.refuse(doc)
        later(stop)

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
        later(self.changed, 100)  # the tree shows every new document: hide again

    def on_closed(self, doc):
        path = getattr(doc, "FileName", "")
        self._tx.pop(getattr(doc, "Name", ""), None)
        if not path:
            return
        self.loaded.pop(_norm(path), None)
        if not self._quiet:
            self.shown.discard(_norm(path))
        if self.locks.holds(path) and not self._quiet:
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
            try:
                self.locks.acquire(path)
            except (locks.Offline, supabase.StoreError) as exc:
                App.Console.PrintWarning("CoBench: %s\n" % exc)
            if not self._quiet:
                later(lambda: status_message(tr("{name} saved and locked: release it when you are done.",
                                                name=name)))
        if stale and not self._quiet:
            later(lambda: QtWidgets.QMessageBox.warning(
                main_window(), "CoBench",
                tr("{name} had been saved by someone else after you opened it. Your save replaced "
                   "their version.", name=name)))

    def on_saved(self, doc, path):
        self.loaded[_norm(path)] = _mtime(path)
        if self.managed(path) and self.locks.holds(path):
            try:
                if self.store() == "supabase":
                    self.locks.set_version(path, stamps.fingerprint(path), os.path.getsize(path))
                else:
                    stamps.write(path, self.identity)
            except (OSError, supabase.StoreError) as exc:
                App.Console.PrintWarning("CoBench: %s\n" % exc)
        later(self.changed)

    def on_recomputing(self, doc):
        self._recomputing.add(doc.Name)

    def on_recomputed(self, doc):
        self._recomputing.discard(doc.Name)
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

    def slotBeforeRecomputeDocument(self, doc):
        self._safe(self.session.on_recomputing, doc)

    def slotRecomputedDocument(self, doc):
        self._safe(self.session.on_recomputed, doc)

    def slotOpenTransaction(self, doc, name):
        self._safe(self.session.on_open_transaction, doc, name)

    def slotCommitTransaction(self, doc):
        self._safe(self.session.on_commit, doc)

    def slotAbortTransaction(self, doc):
        self._safe(self.session.on_abort, doc)

    def slotChangedObject(self, obj, prop):
        self._safe(self.session.on_changed, obj, prop)

    def slotUndoDocument(self, doc):
        self._safe(self.session.on_undo_redo, doc, False)

    def slotRedoDocument(self, doc):
        self._safe(self.session.on_undo_redo, doc, True)


class _GuiObserver:
    """FreeCAD calls these methods by name (Gui.addDocumentObserver)."""

    def __init__(self, session):
        self.session = session

    def slotInEdit(self, view_provider):
        try:
            self.session.on_in_edit(view_provider)
        except Exception as exc:
            App.Console.PrintWarning("CoBench: %s\n" % exc)


def _alive(doc):
    try:
        return doc.Name in App.listDocuments()
    except Exception:
        return False
