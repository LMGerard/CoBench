# SPDX-License-Identifier: LGPL-2.1-or-later
"""Is this computer online, and has the sync client sent a file?

``file_state`` reads the per-file state that Windows sync clients publish
through the Cloud Files API (the "Status" column of the file explorer):
OneDrive, Nextcloud with virtual files, and others.  It never downloads a
file.  Everywhere else it answers UNKNOWN and CoBench falls back on a delay.
"""

import os
import socket
import sys

SYNCED = "synced"          # the client says the server has this version
PENDING = "pending"        # inside a synced folder, not sent yet
CLOUD_ONLY = "cloud-only"  # only a placeholder on this computer
UNKNOWN = "unknown"        # no client tells us anything here

# Well known public servers; only a TCP connection is opened, nothing is sent.
PROBES = (("1.1.1.1", 443), ("8.8.8.8", 443), ("9.9.9.9", 443))


def online(timeout=1.5):
    for host, port in PROBES:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


# -- Windows Cloud Files API ------------------------------------------------
_PLACEHOLDER = 0x1
_SYNC_ROOT = 0x2
_IN_SYNC = 0x8
_PARTIAL = 0x10
_INVALID = 0xFFFFFFFF
_ATTR_OFFLINE = 0x1000
_ATTR_RECALL_ON_DATA_ACCESS = 0x400000
_ATTR_RECALL_ON_OPEN = 0x40000

_api = None


def _windows_api():
    """(kernel32, cldapi) or False when not available."""
    global _api
    if _api is not None:
        return _api
    _api = False
    if sys.platform != "win32":
        return _api
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        cldapi = ctypes.WinDLL("cldapi")
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                         wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
        kernel32.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
                                                          wintypes.DWORD]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        cldapi.CfGetPlaceholderStateFromFileInfo.restype = ctypes.c_uint
        cldapi.CfGetPlaceholderStateFromFileInfo.argtypes = [wintypes.LPVOID, ctypes.c_int]
        _api = (ctypes, wintypes, kernel32, cldapi)
    except Exception:
        _api = False
    return _api


def _placeholder_state(path):
    """(Cloud Files state flags, file attributes) of path, or None."""
    api = _windows_api()
    if not api:
        return None
    ctypes, wintypes, kernel32, cldapi = api

    class TagInfo(ctypes.Structure):
        _fields_ = [("FileAttributes", wintypes.DWORD), ("ReparseTag", wintypes.DWORD)]

    read_attributes = 0x80
    share_all = 0x1 | 0x2 | 0x4
    open_existing = 3
    flags = 0x02000000 | 0x00200000  # backup semantics (folders), open reparse point (no download)
    handle = kernel32.CreateFileW(path, read_attributes, share_all, None, open_existing, flags, None)
    if handle is None or handle == wintypes.HANDLE(-1).value:
        return None
    try:
        info = TagInfo()
        file_attribute_tag_info = 9
        if not kernel32.GetFileInformationByHandleEx(handle, file_attribute_tag_info,
                                                     ctypes.byref(info), ctypes.sizeof(info)):
            return None
        state = cldapi.CfGetPlaceholderStateFromFileInfo(ctypes.byref(info), file_attribute_tag_info)
        return state, info.FileAttributes
    finally:
        kernel32.CloseHandle(handle)


def _in_synced_tree(folder):
    """True when a Cloud Files sync client manages this folder."""
    for _ in range(64):
        found = _placeholder_state(folder)
        if found is not None and found[0] != _INVALID and found[0] & (_PLACEHOLDER | _SYNC_ROOT):
            return True
        parent = os.path.dirname(folder)
        if parent == folder:
            return False
        folder = parent
    return False


def file_state(path):
    """SYNCED, PENDING, CLOUD_ONLY or UNKNOWN for an existing file."""
    try:
        found = _placeholder_state(path)
        if found is None:
            return UNKNOWN
        state, attributes = found
        if state == _INVALID:
            return UNKNOWN
        if attributes & (_ATTR_OFFLINE | _ATTR_RECALL_ON_DATA_ACCESS | _ATTR_RECALL_ON_OPEN) \
                or state & _PARTIAL:
            return CLOUD_ONLY
        if state & _PLACEHOLDER:
            return SYNCED if state & _IN_SYNC else PENDING
        # A new file is not a placeholder until the client has sent it.
        return PENDING if _in_synced_tree(os.path.dirname(os.path.abspath(path))) else UNKNOWN
    except Exception:
        return UNKNOWN
