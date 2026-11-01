# SPDX-License-Identifier: LGPL-2.1-or-later
"""CoBench preferences, stored in FreeCAD's user parameters."""

import FreeCAD as App

PATH = "User parameter:BaseApp/Preferences/Mod/CoBench"


def _group():
    return App.ParamGet(PATH)


def user_name():
    return _group().GetString("UserName", "")


def set_user_name(name):
    _group().SetString("UserName", name.strip())


def last_project():
    return _group().GetString("LastProject", "")


def set_last_project(path):
    _group().SetString("LastProject", path or "")


def protect_files():
    """Make parts locked by others read-only on this computer."""
    return _group().GetBool("ProtectFiles", True)


def set_protect_files(value):
    _group().SetBool("ProtectFiles", bool(value))


def show_overlay():
    """Draw lock boxes over parts in assemblies."""
    return _group().GetBool("ShowOverlay", True)


def set_show_overlay(value):
    _group().SetBool("ShowOverlay", bool(value))


def refresh_seconds():
    return max(2, _group().GetInt("RefreshSeconds", 5))


def icon_view():
    return _group().GetBool("IconView", True)


def set_icon_view(value):
    _group().SetBool("IconView", bool(value))


def freecad_author():
    return App.ParamGet("User parameter:BaseApp/Preferences/Document").GetString("prefAuthor", "")


def set_freecad_author(name):
    """FreeCAD writes this name in LastModifiedBy when a document is saved."""
    group = App.ParamGet("User parameter:BaseApp/Preferences/Document")
    group.SetString("prefAuthor", name)
    group.SetBool("prefSetAuthorOnSave", True)
