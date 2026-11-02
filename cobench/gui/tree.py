# SPDX-License-Identifier: LGPL-2.1-or-later
"""Keep the tree readable: files loaded only because an assembly uses them
are hidden from FreeCAD's tree.  They stay loaded; editing one with CoBench,
or making it the active document, shows it again.

FreeCAD has no option for this, so CoBench hides the document rows of the
tree widget itself.  Nothing is changed in the documents.
"""

import os

import FreeCAD as App
import FreeCADGui as Gui

from . import prefs
from .qt import QtWidgets


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


class TreeHider:
    def __init__(self, session):
        self.session = session
        session.listeners.append(self.apply)

    def hidden_labels(self):
        if not prefs.hide_dependencies():
            return set()
        documents = list(App.listDocuments().values())
        active = App.ActiveDocument
        used = set()
        for doc in documents:
            if not doc.FileName or not self.session.managed(doc.FileName):
                continue
            try:
                deps = doc.getDependentDocuments(False)
            except Exception:
                deps = []
            for dep in deps:
                if dep is not doc and dep.FileName:
                    used.add(_norm(dep.FileName))
        labels = set()
        for doc in documents:
            path = doc.FileName
            if not path or _norm(path) not in used or not self.session.managed(path):
                continue
            if active is not None and doc.Name == active.Name:
                continue
            if _norm(path) in self.session.shown or self.session.locks.holds(path):
                continue
            labels.add(doc.Label)
        return labels

    def apply(self):
        try:
            window = Gui.getMainWindow()
        except Exception:
            return
        if window is None:
            return
        hidden = self.hidden_labels()
        labels = {d.Label for d in App.listDocuments().values()}
        for tree in window.findChildren(QtWidgets.QTreeWidget):
            for index in range(tree.topLevelItemCount()):
                item = tree.topLevelItem(index)
                text = item.text(0)
                if text not in labels:
                    continue
                should_hide = text in hidden
                if item.isHidden() != should_hide:
                    item.setHidden(should_hide)
