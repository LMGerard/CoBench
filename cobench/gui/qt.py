# SPDX-License-Identifier: LGPL-2.1-or-later
"""Qt import that works with the Qt5 and Qt6 builds of FreeCAD."""

try:
    from PySide6 import QtCore, QtGui, QtWidgets  # noqa: F401
except ImportError:  # FreeCAD built with Qt5
    from PySide2 import QtCore, QtGui, QtWidgets  # noqa: F401

Qt = QtCore.Qt
