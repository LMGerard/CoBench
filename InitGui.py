# SPDX-License-Identifier: LGPL-2.1-or-later
"""CoBench workbench: collaborate on a FreeCAD project stored in any folder."""

import os

import FreeCADGui as Gui


class CoBenchWorkbench(Gui.Workbench):
    import cobench as _package

    MenuText = "CoBench"
    ToolTip = "Lock parts while you edit them and see who works on what"
    Icon = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(_package.__file__))),
                        "Resources", "icons", "CoBench.svg")
    del _package

    def Initialize(self):
        from cobench.gui import commands
        from cobench.i18n import tr
        commands.register()
        for name, items in commands.TOOLBARS:
            self.appendToolbar(name, items)
        self.appendMenu("CoBench", commands.MENU)
        commands.start()
        self._tr = tr

    def Activated(self):
        from cobench.gui import commands, panel
        commands.start()
        panel.show_panel()

    def Deactivated(self):
        pass

    def ContextMenu(self, recipient):
        from cobench.gui import commands
        items = commands.context_items()
        if items:
            self.appendContextMenu("CoBench", items)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(CoBenchWorkbench())


def _start_session():
    """Watch saves and closes from FreeCAD start, whatever the workbench."""
    try:
        from cobench.gui import commands
        commands.start()
    except Exception as exc:  # never break FreeCAD start-up
        import FreeCAD
        FreeCAD.Console.PrintWarning("CoBench: %s\n" % exc)


try:
    from cobench.gui.qt import QtCore as _QtCore
    _QtCore.QTimer.singleShot(0, _start_session)
except Exception:
    pass
