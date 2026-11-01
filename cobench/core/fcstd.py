# SPDX-License-Identifier: LGPL-2.1-or-later
"""Read what we need from a .FCStd file without FreeCAD.

A .FCStd file is a zip archive.  ``thumbnails/Thumbnail.png`` holds the
preview FreeCAD saves (when "Save thumbnail" is enabled, the default) and
``Document.xml`` holds the document properties and the external links.
"""

import os
import xml.etree.ElementTree as ET
import zipfile

THUMBNAIL = "thumbnails/Thumbnail.png"
DOCUMENT = "Document.xml"
META_PROPERTIES = ("Label", "CreatedBy", "CreationDate", "LastModifiedBy",
                   "LastModifiedDate", "Comment", "Company")


class PartFile:
    """Metadata of one .FCStd file (cached by modification time and size)."""

    def __init__(self, path):
        self.path = path
        self.thumbnail = None   # PNG bytes or None
        self.meta = {}          # Document property name -> text
        self.links = []         # files referenced by App::Link (as written)
        self.error = None


_cache = {}


def _key(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def read_part(path):
    key = _key(path)
    cached = _cache.get(path)
    if cached is not None and cached[0] == key:
        return cached[1]
    part = PartFile(path)
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if THUMBNAIL in names:
                part.thumbnail = archive.read(THUMBNAIL)
            if DOCUMENT in names:
                with archive.open(DOCUMENT) as stream:
                    _parse_document(stream, part)
    except (OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        # Often a file still being written by FreeCAD or the sync client.
        part.error = str(exc)
    _cache[path] = (key, part)
    return part


def _parse_document(stream, part):
    """Document properties come first; links are XLink elements anywhere."""
    depth = 0
    current = None
    links = []
    for event, elem in ET.iterparse(stream, events=("start", "end")):
        if event == "start":
            depth += 1
            if elem.tag == "Property" and depth == 3:
                # <Document><Properties><Property name=...><String value=.../>
                current = elem.get("name")
            continue
        # end
        if current and depth == 4 and current in META_PROPERTIES:
            value = elem.get("value")
            if value is not None and current not in part.meta:
                part.meta[current] = value
        if elem.tag == "Property" and depth == 3:
            current = None
        if elem.tag == "XLink":
            target = elem.get("file")
            if target and target not in links:
                links.append(target)
        if elem.tag == "Object" and depth >= 3:
            elem.clear()  # keep memory low on big documents
        depth -= 1
    part.links = links


def resolve_link(owner_path, target):
    """Absolute path of a link target written relative to the owner file."""
    target = target.replace("\\", "/")
    if os.path.isabs(target):
        return os.path.normpath(target)
    return os.path.normpath(os.path.join(os.path.dirname(owner_path), target))


def clear_cache():
    _cache.clear()
