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


def strict():
    """Refuse changes to project files that are not locked."""
    return _group().GetBool("Strict", True)


def set_strict(value):
    _group().SetBool("Strict", bool(value))


def auto_reload():
    """Reload parts saved by others."""
    return _group().GetBool("AutoReload", True)


def set_auto_reload(value):
    _group().SetBool("AutoReload", bool(value))


def notifications():
    return _group().GetBool("Notifications", True)


def set_notifications(value):
    _group().SetBool("Notifications", bool(value))


def hide_dependencies():
    """Keep parts loaded by an assembly out of the tree."""
    return _group().GetBool("HideDependencies", True)


def set_hide_dependencies(value):
    _group().SetBool("HideDependencies", bool(value))


def panel_view():
    """'folders' or 'thumbnails'."""
    return _group().GetString("PanelView", "folders")


def set_panel_view(value):
    _group().SetString("PanelView", value)


def offline_check():
    """Refuse to take a lock when this computer is offline."""
    return _group().GetBool("OfflineCheck", True)


def set_offline_check(value):
    _group().SetBool("OfflineCheck", bool(value))


def sync_delay():
    """Seconds online after taking a lock before it counts as sent
    (when the sync client does not say it)."""
    return max(1, _group().GetInt("SyncDelay", 10))


def set_sync_delay(value):
    _group().SetInt("SyncDelay", int(value))
