# SPDX-License-Identifier: LGPL-2.1-or-later
"""Proposals in FreeCAD: propose a change, look at it, comment, integrate or refuse.

The data and the rules are in ``core/proposals.py``; this module adds the
dialogs, the list in the panel, the notifications, and the superposition of
a proposed part on the current one.
"""

import os

import FreeCAD as App
import FreeCADGui as Gui

from ..core import locks, proposals, stamps, supabase
from ..i18n import tr
from . import prefs
from . import session as session_mod
from .qt import Qt, QtCore, QtGui, QtWidgets

CURRENT_COLOR = (0.62, 0.62, 0.62)
CURRENT_TRANSPARENCY = 70
PROPOSED_COLOR = (0.18, 0.63, 0.26)


def _escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def _when(value):
    moment = locks.parse_iso(value)
    return moment.astimezone().strftime("%d/%m/%Y %H:%M") if moment else (value or "")


def status_text(proposal):
    return {
        proposals.OPEN: tr("open"),
        proposals.INTEGRATED: tr("integrated by {user}", user=proposal.closed_by()),
        proposals.REFUSED: tr("refused by {user}", user=proposal.closed_by()),
        proposals.WITHDRAWN: tr("withdrawn"),
    }.get(proposal.status, proposal.status)


def conflict_text(conflict):
    if conflict.reason == proposals.CHANGED:
        return tr("changed since the proposal: integrate it by hand")
    if conflict.reason == proposals.NOT_ARRIVED:
        return tr("the last version has not arrived on this computer yet")
    if conflict.reason == proposals.MISSING:
        return tr("the part was moved or deleted")
    if conflict.reason == proposals.UNREADABLE:
        return tr("the proposed file has not arrived yet")
    if conflict.reason == proposals.LOCKED:
        return tr("locked by {user}", user=conflict.detail or "?")
    return conflict.reason


def latest_for(session, proposal):
    """sha1 of the last saved version of a part, as known outside this computer."""
    created = locks.parse_iso(proposal.created)

    def latest(path):
        if session.store() == "supabase":
            version = session.locks.version(path)
            return version.get("sha1") if version else None
        stamp = stamps.Stamp.read(path)
        saved = locks.parse_iso(stamp.saved) if stamp is not None else None
        # A stamp written before the proposal says nothing new (the base may be an unstamped save).
        if stamp is not None and stamp.sha1 and saved is not None and created is not None and saved > created:
            return stamp.sha1
        return None
    return latest


def mine(session, proposal):
    return proposal.is_author(session.identity)


# -- periodic look ------------------------------------------------------------------

def scan(session):
    """Read the proposals of the project, protect their files, tell what changed."""
    project = session.project
    if project is None:
        session.proposals = []
        return
    found = proposals.list_proposals(project.root)
    seen = getattr(session, "_proposals_seen", None)
    now = {}
    for proposal in found:
        protect(session, proposal)
        comments = [c for c in proposal.comments() if c.kind == "comment"]
        now[proposal.id] = (proposal.status, len(comments))
        if seen is None:
            continue
        before = seen.get(proposal.id)
        title = proposal.title or proposal.id
        if before is None:
            if proposal.is_open and not mine(session, proposal):
                session.notify(tr("{user} proposes a change: {title}", user=proposal.user, title=title))
            continue
        if before[0] == proposals.OPEN and not proposal.is_open and mine(session, proposal):
            session.notify(tr("Your proposal {title}: {status}.", title=title, status=status_text(proposal)),
                           warning=proposal.status == proposals.REFUSED)
        elif len(comments) > before[1] and comments and not session.identity.same_as(
                comments[-1].user, comments[-1].host) and (mine(session, proposal) or before[1]):
            session.notify(tr("{user} commented on the proposal {title}.", user=comments[-1].user, title=title))
    session._proposals_seen = now
    session.proposals = found


def protect(session, proposal):
    """Proposed files are read-only, except for their author while the proposal is open."""
    writable = proposal.is_open and mine(session, proposal)
    if not writable and not prefs.protect_files():
        return
    for item in proposal.files:
        try:
            locks.set_read_only(proposal.stored_path(item), not writable)
        except OSError:
            pass


def editable(session, path):
    """For a file of the proposals folder: may this FreeCAD change it?"""
    proposal = proposals.owner_of(session.project.root, path) if session.project else None
    return proposal is not None and proposal.is_open and mine(session, proposal)


def is_proposal_file(session, path):
    return bool(session.project and path and proposals.is_proposal_path(session.project.root, path))


# -- actions ------------------------------------------------------------------------

def _warn(parent, text):
    QtWidgets.QMessageBox.warning(parent or session_mod.main_window(), "CoBench", text)


def _base(session, path):
    """The version the proposal starts from; None (after telling) if it is not the latest one."""
    name = os.path.basename(path)
    doc = session.find_document(path)
    if doc is not None and session.is_modified(doc):
        _warn(None, tr("{name} has unsaved changes: save it or close it before proposing a change.", name=name))
        return None
    base = proposals.base_of(path)
    if session.store() == "supabase":
        version = session.locks.version(path)
        if version and version.get("sha1") and not session._is_version(path, version):
            _warn(None, tr("The last version of {name}, saved by {user}, has not arrived on this computer "
                           "yet. Wait for the sync before proposing a change.",
                           name=name, user=version.get("saved_by") or "?"))
            return None
        if version and version.get("sha1") == base["sha1"]:
            base["saved_by"] = version.get("saved_by") or ""
            base["saved_at"] = str(version.get("saved_at") or "")
    else:
        try:
            stamp = stamps.newer_elsewhere(path)
        except OSError:
            stamp = None
        if stamp is not None:
            _warn(None, tr("The last version of {name}, saved by {user}, has not arrived on this computer "
                           "yet. Wait for the sync before proposing a change.", name=name, user=stamp.user))
            return None
    return base


def propose(session, path, parent=None):
    """Ask for a title, copy the part into a new (or one of my) proposals, open the copy."""
    if session.project is None or not os.path.exists(path):
        return None
    base = _base(session, path)
    if base is None:
        return None
    own = [p for p in session.proposals if p.is_open and mine(session, p)]
    dialog = NewProposalDialog(path, own, parent)
    if dialog.exec() != QtWidgets.QDialog.Accepted:
        return None
    target, title, message = dialog.values()
    try:
        if target is None:
            proposal = proposals.create(session.project.root, session.identity, [path], title, message,
                                        bases={path: base})
        else:
            proposal = target
            if proposal.file_for(path) is None:
                proposals.add_parts(proposal, session.identity, [path], bases={path: base})
    except (OSError, proposals.ProposalError) as exc:
        _warn(parent, tr("The proposal could not be saved: {error}", error=exc))
        return None
    item = proposal.file_for(path)
    session.notify(tr("Proposal {title}: change the copy of {name}, save it, and the others will see it.",
                      title=proposal.title or proposal.id, name=_stem(path)))
    session.tick()
    open_item(session, proposal, item)
    return proposal


def open_item(session, proposal, item, original=False):
    """Open the proposed copy of a part (or the part itself)."""
    if original:
        path = proposal.part_path(item)
        if not os.path.exists(path):
            _warn(None, tr("{name} not found.", name=item.part))
            return None
        return session.view(path)
    path = proposal.stored_path(item)
    if not os.path.exists(path):
        _warn(None, tr("The proposed file has not arrived on this computer yet."))
        return None
    doc = session._load(path)
    if not editable(session, path):
        session_mod.status_message(tr("Proposal opened read-only."))
    return doc


def _roots(doc):
    """Top-level shapes of a document, as shown in its 3D view."""
    found = []
    for obj in doc.Objects:
        if obj.InList or obj.TypeId == "App::Origin":
            continue
        if not (hasattr(obj, "Shape") or obj.isDerivedFrom("App::Part") or obj.isDerivedFrom("App::Link")):
            continue
        try:
            if not obj.ViewObject.Visibility:
                continue
        except Exception:
            pass
        found.append(obj)
    return found


def _paint(obj, color, transparency):
    view = getattr(obj, "ViewObject", None)
    if view is None:
        return
    try:
        view.ShapeColor = color
        view.Transparency = transparency
    except Exception:
        pass


def compare(session, proposal, item):
    """A new document showing the current part (grey, transparent) and the proposed one (green).

    It holds frozen copies of the shapes, not links: nothing is written in
    the project, nothing has to be saved, and closing it asks nothing.
    """
    import Part

    part, stored = proposal.part_path(item), proposal.stored_path(item)
    if not os.path.exists(stored):
        _warn(None, tr("The proposed file has not arrived on this computer yet."))
        return None
    current = session.view(part) if os.path.exists(part) else None
    proposed = session._load(stored)
    for source in (current, proposed):
        if source is not None:
            source.recompute()
    with session.quiet():
        doc = App.newDocument("Comparison")
        doc.Label = "%s - %s" % (_stem(part), tr("Superimpose"))
        for source, label, color, transparency in (
                (current, tr("Current: {name}", name=_stem(part)), CURRENT_COLOR, CURRENT_TRANSPARENCY),
                (proposed, tr("Proposed: {name}", name=_stem(part)), PROPOSED_COLOR, 0)):
            if source is None:
                continue
            group = doc.addObject("App::DocumentObjectGroup", "Group")
            group.Label = label
            for obj in _roots(source):
                try:
                    shape = Part.getShape(obj)
                except Exception:
                    continue
                if shape.isNull():
                    continue
                copy = doc.addObject("Part::Feature", "Shape")
                copy.Shape = shape
                copy.Label = obj.Label
                group.addObject(copy)
                _paint(copy, color, transparency)
        doc.recompute()
    try:
        Gui.getDocument(doc.Name).Modified = False
    except Exception:
        pass
    session._show(doc)
    try:
        Gui.activeDocument().activeView().viewIsometric()
        Gui.SendMsgToActiveView("ViewFit")
    except Exception:
        pass
    session_mod.status_message(tr("Grey: the current part. Green: the proposed one."))
    return doc


def integrate(session, proposal, text="", parent=None):
    """Replace the parts by the proposed versions, after checks and confirmation."""
    latest = latest_for(session, proposal)
    conflicts = proposals.check(proposal, latest, session.locks)
    if conflicts:
        _warn(parent, tr("This proposal cannot be integrated:") + "\n\n" + "\n".join(
            "%s: %s" % (c.part, conflict_text(c)) for c in conflicts))
        return False
    for item in proposal.files:
        doc = session.find_document(proposal.part_path(item))
        if doc is not None and session.is_modified(doc):
            _warn(parent, tr("Save or close {name} first.", name=os.path.basename(item.part)))
            return False
    answer = QtWidgets.QMessageBox.question(
        parent or session_mod.main_window(), "CoBench",
        tr("Replace {count} parts by the versions proposed by {user}?\n\nThe current versions are kept in "
           "the proposal folder.", count=len(proposal.files), user=proposal.user),
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
    if answer != QtWidgets.QMessageBox.Yes:
        return False
    try:
        with session.quiet():
            result = proposals.integrate(proposal, session.identity, session.locks, text, latest)
    except locks.Offline:
        _warn(parent, tr("Cannot reach the lock database (offline?): nothing was changed."))
        return False
    except (supabase.StoreError, proposals.ProposalError, OSError) as exc:
        _warn(parent, tr("The proposal could not be integrated: {error}", error=exc))
        session.tick()
        return False
    if not result:
        _warn(parent, tr("This proposal cannot be integrated:") + "\n\n" + "\n".join(
            "%s: %s" % (c.part, conflict_text(c)) for c in result.conflicts))
        session.tick()
        return False
    for path in result.parts:
        doc = session.find_document(path)
        if doc is not None:
            session._reopen(doc, False)
        session.loaded.pop(session_mod._norm(path), None)
    for path, error in result.warnings:
        _warn(parent, tr("The new version of {name} could not be recorded in the lock database, so it stays "
                         "locked for you (otherwise others could edit an older copy).\n\n{error}",
                         name=os.path.basename(path), error=error))
    session.notify(tr("Proposal {title} integrated: {count} parts replaced.",
                      title=proposal.title or proposal.id, count=len(result.parts)))
    session.tick()
    return True


def refuse(session, proposal, text, parent=None):
    if not text.strip():
        _warn(parent, tr("Say why in the comment box before refusing."))
        return False
    try:
        proposals.refuse(proposal, session.identity, text)
    except (OSError, proposals.ProposalError) as exc:
        _warn(parent, tr("The proposal could not be closed: {error}", error=exc))
        return False
    session.notify(tr("Proposal {title} refused.", title=proposal.title or proposal.id))
    session.tick()
    return True


def withdraw(session, proposal, text="", parent=None):
    answer = QtWidgets.QMessageBox.question(
        parent or session_mod.main_window(), "CoBench", tr("Withdraw your proposal {title}?",
                                                           title=proposal.title or proposal.id),
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
    if answer != QtWidgets.QMessageBox.Yes:
        return False
    try:
        proposals.withdraw(proposal, session.identity, text)
    except (OSError, proposals.ProposalError) as exc:
        _warn(parent, tr("The proposal could not be closed: {error}", error=exc))
        return False
    session.tick()
    return True


# -- dialogs --------------------------------------------------------------------------

class NewProposalDialog(QtWidgets.QDialog):
    """Title and message of a new proposal, or one of my open proposals to add the part to."""

    def __init__(self, path, own, parent=None):
        super().__init__(parent or session_mod.main_window())
        self.setWindowTitle(tr("Propose a change"))
        self.own = own
        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(tr(
            "CoBench copies {name} into a proposal, without locking it. Change the copy and save it: the "
            "others see the proposal in their panel, comment on it, and integrate or refuse it.",
            name="<b>%s</b>" % _escape(_stem(path))))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QtWidgets.QFormLayout()
        self.target = QtWidgets.QComboBox()
        self.target.addItem(tr("New proposal"))
        for proposal in own:
            self.target.addItem(tr("Add to: {title}", title=proposal.title or proposal.id))
        self.target.currentIndexChanged.connect(self._target_changed)
        form.addRow(tr("Proposal"), self.target)
        self.title = QtWidgets.QLineEdit()
        self.title.setPlaceholderText(tr("What does it change? (e.g. Plate 6 mm thick)"))
        form.addRow(tr("Title"), self.title)
        self.message = QtWidgets.QPlainTextEdit()
        self.message.setPlaceholderText(tr("Why, and what to check"))
        self.message.setMinimumHeight(90)
        form.addRow(tr("Message"), self.message)
        layout.addLayout(form)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(460, 300)

    def _target_changed(self, index):
        self.title.setEnabled(index == 0)
        self.message.setEnabled(index == 0)

    def _accept(self):
        if self.target.currentIndex() == 0 and not self.title.text().strip():
            self.title.setFocus()
            return
        self.accept()

    def values(self):
        index = self.target.currentIndex()
        target = self.own[index - 1] if index > 0 else None
        return target, self.title.text().strip(), self.message.toPlainText().strip()


class ProposalDialog(QtWidgets.QDialog):
    """One proposal: what it changes, its comments, and what can be done with it."""

    def __init__(self, session, proposal, parent=None):
        super().__init__(parent or session_mod.main_window())
        self.session = session
        self.proposal = proposal
        self.setWindowTitle(tr("Proposal: {title}", title=proposal.title or proposal.id))
        self.setAttribute(Qt.WA_DeleteOnClose)
        layout = QtWidgets.QVBoxLayout(self)
        self.header = QtWidgets.QLabel()
        self.header.setTextFormat(Qt.RichText)
        self.header.setWordWrap(True)
        self.header.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.header)

        self.files = QtWidgets.QTreeWidget()
        self.files.setHeaderLabels([tr("Part"), tr("State")])
        self.files.setRootIsDecorated(False)
        self.files.header().setStretchLastSection(True)
        self.files.itemDoubleClicked.connect(lambda *_: self._open(False))
        self.files.itemSelectionChanged.connect(self._update_buttons)
        self.files.setMaximumHeight(140)
        layout.addWidget(self.files)
        row = QtWidgets.QHBoxLayout()
        self.open_button = QtWidgets.QPushButton(tr("Open the proposal"))
        self.open_button.clicked.connect(lambda: self._open(False))
        self.original_button = QtWidgets.QPushButton(tr("Open the current part"))
        self.original_button.clicked.connect(lambda: self._open(True))
        self.compare_button = QtWidgets.QPushButton(tr("Superimpose"))
        self.compare_button.setToolTip(tr("Show the current part in grey and the proposed one in green"))
        self.compare_button.clicked.connect(self._compare)
        for button in (self.open_button, self.original_button, self.compare_button):
            row.addWidget(button)
        layout.addLayout(row)

        self.comments = QtWidgets.QTextBrowser()
        self.comments.setOpenLinks(False)
        layout.addWidget(self.comments, 1)
        self.comment_box = QtWidgets.QPlainTextEdit()
        self.comment_box.setPlaceholderText(tr("Comment"))
        self.comment_box.setMaximumHeight(70)
        layout.addWidget(self.comment_box)

        actions = QtWidgets.QHBoxLayout()
        self.comment_button = QtWidgets.QPushButton(tr("Comment"))
        self.comment_button.clicked.connect(self._comment)
        self.integrate_button = QtWidgets.QPushButton(tr("Integrate"))
        self.integrate_button.setToolTip(tr("Replace the parts by the proposed versions"))
        self.integrate_button.clicked.connect(self._integrate)
        self.refuse_button = QtWidgets.QPushButton(tr("Refuse"))
        self.refuse_button.setToolTip(tr("Close the proposal with the comment above"))
        self.refuse_button.clicked.connect(self._refuse)
        self.withdraw_button = QtWidgets.QPushButton(tr("Withdraw"))
        self.withdraw_button.clicked.connect(self._withdraw)
        actions.addWidget(self.comment_button)
        actions.addStretch(1)
        for button in (self.withdraw_button, self.refuse_button, self.integrate_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.resize(560, 560)
        self.session.listeners.append(self.refresh)
        self.finished.connect(self._closed)
        self.refresh()

    def _closed(self, *_args):
        try:
            self.session.listeners.remove(self.refresh)
        except ValueError:
            pass

    def refresh(self):
        proposal = self.proposal.reload()
        author = mine(self.session, proposal)
        lines = ["<b>%s</b>" % _escape(proposal.title or proposal.id),
                 tr("Proposed by {user} on {when}", user=_escape(proposal.user), when=_when(proposal.created))
                 + " &middot; " + _escape(status_text(proposal))]
        if proposal.message:
            lines.append(_escape(proposal.message).replace("\n", "<br>"))
        self.header.setText("<br>".join(lines))
        conflicts = {c.part: c for c in proposals.check(proposal, latest_for(self.session, proposal),
                                                         self.session.locks)} if proposal.is_open else {}
        selected = self._selected_part()
        self.files.clear()
        for item in proposal.files:
            if item.part in conflicts:
                state, color = conflict_text(conflicts[item.part]), QtGui.QColor(208, 52, 44)
            elif proposal.is_open:
                state, color = tr("ready to integrate"), QtGui.QColor(46, 160, 67)
            else:
                state, color = "", None
            if item.base.get("saved_by"):
                state += ("  " if state else "") + tr("(from the version saved by {user})", user=item.base["saved_by"])
            row = QtWidgets.QTreeWidgetItem([item.part, state])
            row.setData(0, Qt.UserRole, item.part)
            if color is not None:
                row.setForeground(1, color)
            self.files.addTopLevelItem(row)
            if item.part == selected or (selected is None and self.files.topLevelItemCount() == 1):
                row.setSelected(True)
        self.files.resizeColumnToContents(0)
        html = []
        for entry in proposal.comments():
            what = {proposals.INTEGRATED: tr("integrated"), proposals.REFUSED: tr("refused"),
                    proposals.WITHDRAWN: tr("withdrawn")}.get(entry.kind, "")
            head = "<b>%s</b> <small>%s</small>%s" % (_escape(entry.user), _escape(_when(entry.date)),
                                                     (" &middot; <i>%s</i>" % _escape(what)) if what else "")
            html.append("<p>%s<br>%s</p>" % (head, _escape(entry.text).replace("\n", "<br>")))
        self.comments.setHtml("".join(html) or "<i>%s</i>" % _escape(tr("No comment yet.")))
        is_open = proposal.is_open
        self.comment_box.setEnabled(is_open)
        self.comment_button.setEnabled(is_open)
        self.integrate_button.setVisible(is_open and not author)
        self.integrate_button.setEnabled(is_open and not conflicts)
        self.refuse_button.setVisible(is_open and not author)
        self.withdraw_button.setVisible(is_open and author)
        self.open_button.setText(tr("Edit the proposal") if (is_open and author) else tr("Open the proposal"))
        self._update_buttons()

    def _selected_part(self):
        items = self.files.selectedItems()
        return items[0].data(0, Qt.UserRole) if items else None

    def _selected_item(self):
        part = self._selected_part()
        for item in self.proposal.files:
            if item.part == part:
                return item
        return None

    def _update_buttons(self):
        has = self._selected_item() is not None
        for button in (self.open_button, self.original_button, self.compare_button):
            button.setEnabled(has)

    def _run(self, action, *args):
        try:
            return action(*args)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "CoBench", str(exc))
            return None

    def _open(self, original):
        item = self._selected_item()
        if item is not None:
            self._run(open_item, self.session, self.proposal, item, original)

    def _compare(self):
        item = self._selected_item()
        if item is not None:
            self._run(compare, self.session, self.proposal, item)

    def _comment(self):
        text = self.comment_box.toPlainText().strip()
        if not text:
            return
        try:
            proposals.comment(self.proposal, self.session.identity, text)
        except OSError as exc:
            _warn(self, str(exc))
            return
        self.comment_box.clear()
        self.refresh()

    def _integrate(self):
        if self._run(integrate, self.session, self.proposal, self.comment_box.toPlainText(), self):
            self.comment_box.clear()
        self.refresh()

    def _refuse(self):
        if self._run(refuse, self.session, self.proposal, self.comment_box.toPlainText(), self):
            self.comment_box.clear()
        self.refresh()

    def _withdraw(self):
        if self._run(withdraw, self.session, self.proposal, self.comment_box.toPlainText(), self):
            self.comment_box.clear()
        self.refresh()


_dialogs = {}


def show(session, proposal, parent=None):
    """Open (or bring back) the window of a proposal."""
    dialog = _dialogs.get(proposal.id)
    try:
        if dialog is not None and dialog.isVisible():
            dialog.raise_()
            dialog.activateWindow()
            return dialog
    except RuntimeError:  # deleted on close
        pass
    dialog = ProposalDialog(session, proposal, parent)
    _dialogs[proposal.id] = dialog
    dialog.show()
    return dialog


class ProposalList(QtWidgets.QWidget):
    """The proposals of the project, folded under the parts in the panel."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._signature = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QtWidgets.QHBoxLayout()
        self.toggle = QtWidgets.QToolButton()
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.RightArrow)
        self.toggle.setAutoRaise(True)
        self.toggle.toggled.connect(self._toggled)
        top.addWidget(self.toggle, 1)
        self.closed = QtWidgets.QCheckBox(tr("closed too"))
        self.closed.toggled.connect(lambda _on: self.refresh(force=True))
        self.closed.hide()
        top.addWidget(self.closed)
        layout.addLayout(top)
        self.list = QtWidgets.QListWidget()
        self.list.setMaximumHeight(130)
        self.list.itemActivated.connect(self._activated)
        self.list.itemDoubleClicked.connect(self._activated)
        self.list.hide()
        layout.addWidget(self.list)

    def _toggled(self, shown):
        self.list.setVisible(shown)
        self.closed.setVisible(shown)
        self.toggle.setArrowType(Qt.DownArrow if shown else Qt.RightArrow)

    def refresh(self, force=False):
        found = list(getattr(self.session, "proposals", []))
        opened = [p for p in found if p.is_open]
        shown = found if self.closed.isChecked() else opened
        signature = tuple((p.id, p.status, p.title, len(p.files)) for p in shown)
        self.toggle.setText(tr("Proposals ({count} open)", count=len(opened)))
        if signature == self._signature and not force:
            return
        self._signature = signature
        self.list.clear()
        for proposal in shown:
            parts = ", ".join(_stem(f.part) for f in proposal.files)
            text = "%s  —  %s  (%s)" % (proposal.title or proposal.id, proposal.user, parts)
            if not proposal.is_open:
                text += "  [%s]" % status_text(proposal)
            row = QtWidgets.QListWidgetItem(text)
            row.setData(Qt.UserRole, proposal.folder)
            row.setToolTip(proposal.message or proposal.title)
            if not proposal.is_open:
                row.setForeground(QtGui.QColor(150, 150, 150))
            self.list.addItem(row)
        if not shown:
            row = QtWidgets.QListWidgetItem(tr("No proposal. Right-click a part > Propose a change."))
            row.setFlags(Qt.NoItemFlags)
            self.list.addItem(row)

    def _activated(self, row):
        folder = row.data(Qt.UserRole)
        if folder:
            show(self.session, proposals.Proposal.load(folder), self.window())
