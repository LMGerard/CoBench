# SPDX-License-Identifier: LGPL-2.1-or-later
"""Split one FreeCAD document into one file per part.

Starting from a document holding several bodies and shared variables:

* every VarSet and spreadsheet goes into ``Variables.FCStd``;
* every part (PartDesign Body, App::Part, or loose solid at the top level)
  goes into its own file, in a sub-folder named after its group;
* expressions that used the variables now point to ``Variables#...``, so
  changing a value still updates every part;
* ``Assemblage.FCStd`` links every part at its original place and becomes the
  project's central assembly.

The original file is never modified: the work is done on a hidden copy.
"""

import os
import re
import shutil
import tempfile

import FreeCAD as App
import FreeCADGui as Gui

from ..core import expressions
from ..core.project import Project
from ..i18n import tr
from .qt import QtWidgets

VARIABLES = "Variables"
ASSEMBLY = "Assemblage"
SHARED_TYPES = ("App::VarSet", "Spreadsheet::Sheet")
PART_TYPES = ("PartDesign::Body", "App::Part")


class SplitError(Exception):
    pass


# -- analysis -----------------------------------------------------------------

def is_shared(obj):
    return obj.TypeId in SHARED_TYPES


def is_group(obj):
    return obj.TypeId == "App::DocumentObjectGroup"


def parts_of(doc):
    """Objects that become one file each, in document order."""
    found = []
    for obj in doc.Objects:
        if is_shared(obj) or is_group(obj):
            continue
        if obj.TypeId in PART_TYPES:
            if _container(obj) is None:
                found.append(obj)
            continue
        if not obj.isDerivedFrom("Part::Feature") or obj.isDerivedFrom("Part::Part2DObject"):
            continue
        if _container(obj) is not None:
            continue
        # A loose solid used by nothing else but groups (a box, an import...).
        users = [o for o in obj.InList if not is_group(o)]
        if not users:
            found.append(obj)
    return found


def _container(obj):
    """The Body or App::Part holding the object, if any."""
    try:
        parent = obj.getParentGeoFeatureGroup()
    except Exception:
        parent = None
    return parent


def group_path(obj, skip=()):
    """Labels of the groups holding the object, outermost first."""
    path = []
    current = obj
    seen = set()
    while current is not None and current.Name not in seen:
        seen.add(current.Name)
        parent = None
        for user in current.InList:
            if is_group(user) and current in user.Group:
                parent = user
                break
        if parent is None:
            break
        if parent.Label not in skip:
            path.insert(0, parent.Label)
        current = parent
    return path


_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def file_stem(label):
    stem = _BAD.sub("_", label).strip(" .")
    return stem or "Piece"


def unique(stem, taken):
    candidate = stem
    index = 2
    while candidate.lower() in taken:
        candidate = "%s_%d" % (stem, index)
        index += 1
    taken.add(candidate.lower())
    return candidate


def doc_name(stem):
    """Document internal name FreeCAD derives from a file name."""
    name = re.sub(r"[^A-Za-z0-9_]", "_", stem)
    if not name or name[0].isdigit():
        name = "_" + name
    return name


# -- the work ---------------------------------------------------------------------

class Splitter:
    def __init__(self, source_doc, folder):
        self.source = source_doc
        self.folder = folder
        self.report = []
        self.created = []   # documents we opened, closed at the end except the assembly

    def log(self, text):
        self.report.append(text)
        App.Console.PrintMessage("CoBench: %s\n" % text)

    def check(self):
        if not self.source.FileName:
            raise SplitError(tr("Save the document first."))
        if os.path.exists(self.folder) and os.listdir(self.folder):
            raise SplitError(tr("The folder {folder} is not empty.", folder=self.folder))
        for name in (VARIABLES, ASSEMBLY):
            if name in App.listDocuments():
                raise SplitError(tr("Close the document named {name} first.", name=name))

    def run(self):
        self.check()
        os.makedirs(self.folder, exist_ok=True)
        tmpdir = tempfile.mkdtemp(prefix="cobench-split-")
        work_path = os.path.join(tmpdir, "cobench_split_work.FCStd")
        shutil.copy2(self.source.FileName, work_path)
        work = App.openDocument(work_path, hidden=True)
        # Each file is saved twice (links need a saved owner): no backup files.
        params = App.ParamGet("User parameter:BaseApp/Preferences/Document")
        backups = params.GetBool("CreateBackupFiles", True)
        params.SetBool("CreateBackupFiles", False)
        try:
            return self._split(work)
        finally:
            params.SetBool("CreateBackupFiles", backups)
            try:
                App.closeDocument(work.Name)
            except Exception:
                pass
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _split(self, work):
        shared = [o for o in work.Objects if is_shared(o)]
        names = {o.Name for o in shared}
        labels = {o.Label for o in shared}
        parts = parts_of(work)
        if not parts:
            raise SplitError(tr("No part found (PartDesign bodies, App::Part or solids)."))

        # 1. Remember and remove every expression that reads a shared object,
        #    so the parts no longer depend on them and can be copied alone.
        saved = {}
        for obj in work.Objects:
            if obj.Name in names:
                continue
            for path, text in list(getattr(obj, "ExpressionEngine", []) or []):
                if expressions.references(text, names, labels):
                    saved.setdefault(obj.Name, []).append((path, text))
                    obj.setExpression(path, None)
        work.recompute()

        # 2. Variables.FCStd
        skip_groups = set()
        if shared:
            variables = App.newDocument(VARIABLES)
            self.created.append(variables)
            copies = variables.copyObject(shared, False, True)
            copies = copies if isinstance(copies, (list, tuple)) else [copies]
            renamed = [o.Name for o in shared if variables.getObject(o.Name) is None]
            if renamed:
                raise SplitError(tr("Could not keep the names of: {names}", names=", ".join(renamed)))
            folder_group = variables.addObject("App::DocumentObjectGroup", VARIABLES)
            for obj in shared:
                folder_group.addObject(variables.getObject(obj.Name))
            variables.recompute()
            variables.saveAs(os.path.join(self.folder, VARIABLES + ".FCStd"))
            self.log(tr("{count} variable sets in {file}", count=len(shared), file=VARIABLES + ".FCStd"))
            for obj in shared:
                skip_groups.update(group_path(obj))

        # 3. One file per part
        taken = {VARIABLES.lower(), ASSEMBLY.lower()}
        placed = []   # (part document, object name, group path)
        for part in parts:
            stem = unique(file_stem(part.Label), taken)
            groups = [g for g in group_path(part) if g not in skip_groups]
            subfolder = os.path.join(self.folder, *[file_stem(g) for g in groups])
            os.makedirs(subfolder, exist_ok=True)
            pdoc = App.newDocument(doc_name(stem))
            self.created.append(pdoc)
            pdoc.copyObject(part, True)
            path = os.path.join(subfolder, stem + ".FCStd")
            pdoc.saveAs(path)  # links to another file need a saved owner
            copied_names = {o.Name for o in pdoc.Objects}
            others = [p.Label for p in parts if p is not part and p.Name in copied_names]
            if others:
                self.log(tr("{part} uses {others}: a copy of them is inside its file.",
                            part=part.Label, others=", ".join(others)))
            missing = 0
            for name, entries in saved.items():
                target = pdoc.getObject(name)
                if target is None:
                    continue
                for path, text in entries:
                    try:
                        target.setExpression(path, expressions.rewrite(text, names, labels, VARIABLES))
                    except Exception as exc:
                        missing += 1
                        self.log("%s %s: %s" % (part.Label, path, exc))
            pdoc.recompute()
            self._thumbnail(pdoc)
            pdoc.save()
            root = pdoc.getObject(part.Name)
            placed.append((pdoc, root.Name if root else part.Name, groups))
            if missing:
                self.log(tr("{part}: {count} expressions could not be restored.", part=part.Label, count=missing))
        self.log(tr("{count} parts written.", count=len(parts)))

        # 4. Assemblage.FCStd
        assembly = App.newDocument(ASSEMBLY)
        self.created.append(assembly)
        assembly_path = os.path.join(self.folder, ASSEMBLY + ".FCStd")
        assembly.saveAs(assembly_path)
        group_objects = {}
        for pdoc, name, groups in placed:
            parent = None
            key = ()
            for label in groups:
                key = key + (label,)
                if key not in group_objects:
                    grp = assembly.addObject("App::DocumentObjectGroup", file_stem(label))
                    grp.Label = label
                    if parent is not None:
                        parent.addObject(grp)
                    group_objects[key] = grp
                parent = group_objects[key]
            target = pdoc.getObject(name)
            link = assembly.addObject("App::Link", doc_name(pdoc.Label or pdoc.Name))
            link.LinkedObject = target
            link.LinkTransform = True  # keep the part's own placement (and its expressions)
            link.Label = target.Label
            if parent is not None:
                parent.addObject(link)
        assembly.recompute()
        self._thumbnail(assembly)
        assembly.save()
        self.log(tr("Central assembly: {file}", file=ASSEMBLY + ".FCStd"))

        project = Project(self.folder)
        project.name = self.source.Label
        project.set_assembly(assembly_path)
        return assembly

    def _thumbnail(self, doc):
        """Isometric fit-all view, so the saved file carries a useful preview."""
        try:
            gdoc = Gui.getDocument(doc.Name)
            view = gdoc.activeView() if gdoc else None
            if view is not None:
                view.viewIsometric()
                view.fitAll()
        except Exception:
            pass

    def close_parts(self, keep):
        """Close the part files we opened; the assembly loads them again as needed."""
        for doc in self.created:
            if doc is keep:
                continue
            try:
                if doc.Name in App.listDocuments():
                    App.closeDocument(doc.Name)
            except Exception:
                pass


def split_active(session):
    doc = App.ActiveDocument
    window = Gui.getMainWindow()
    if doc is None:
        return None
    if not doc.FileName:
        QtWidgets.QMessageBox.information(window, "CoBench", tr("Save the document first."))
        return None
    try:
        modified = Gui.getDocument(doc.Name).Modified
    except Exception:
        modified = False
    if modified:
        QtWidgets.QMessageBox.information(
            window, "CoBench", tr("Save the document first: the split uses the saved file."))
        return None
    base = os.path.splitext(doc.FileName)[0] + "_pieces"
    parent = QtWidgets.QFileDialog.getExistingDirectory(
        window, tr("Where to create the folder of parts?"), os.path.dirname(doc.FileName))
    if not parent:
        return None
    folder = os.path.join(parent, os.path.basename(base))
    answer = QtWidgets.QMessageBox.question(
        window, "CoBench",
        tr("Split {name} into one file per part in:\n{folder}\n\nThe original file is not modified.",
           name=os.path.basename(doc.FileName), folder=folder))
    if answer != QtWidgets.QMessageBox.Yes:
        return None
    splitter = Splitter(doc, folder)
    QtWidgets.QApplication.setOverrideCursor(_busy())
    try:
        assembly = splitter.run()
    except SplitError as exc:
        QtWidgets.QApplication.restoreOverrideCursor()
        splitter.close_parts(None)
        QtWidgets.QMessageBox.warning(window, "CoBench", str(exc))
        return None
    except Exception:
        QtWidgets.QApplication.restoreOverrideCursor()
        splitter.close_parts(None)
        raise
    QtWidgets.QApplication.restoreOverrideCursor()
    splitter.close_parts(assembly)
    session.open_project(folder)
    QtWidgets.QMessageBox.information(window, "CoBench", "\n".join(splitter.report))
    return assembly


def _busy():
    from .qt import QtGui, Qt
    return QtGui.QCursor(Qt.WaitCursor)
