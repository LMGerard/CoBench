# SPDX-License-Identifier: LGPL-2.1-or-later
"""Rewrite FreeCAD expressions so they point to objects in another document.

``Socle.Largeur + 2 mm`` becomes ``Variables#Socle.Largeur + 2 mm`` and
``<<Socle>>.Largeur`` becomes ``Variables#<<Socle>>.Largeur``.  Text inside
string literals (``<<...>>`` used as strings) and references that already
name a document are left alone.
"""

import re

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"


def rewrite(expression, names, labels, document):
    """Prefix references to ``names`` (object names) or ``labels`` with ``document#``."""
    if not names and not labels:
        return expression
    out = []
    i = 0
    n = len(expression)
    while i < n:
        # <<label>> references
        if expression.startswith("<<", i):
            end = expression.find(">>", i + 2)
            if end < 0:
                out.append(expression[i:])
                break
            label = expression[i + 2:end]
            token = expression[i:end + 2]
            if label in labels and _followed_by_dot(expression, end + 2) and not _after_hash(expression, i):
                out.append("%s#%s" % (document, token))
            else:
                out.append(token)
            i = end + 2
            continue
        match = re.compile(_IDENT).match(expression, i)
        if match:
            word = match.group(0)
            prev = expression[i - 1] if i > 0 else ""
            if (word in names and prev not in (".", "#") and not prev.isalnum() and prev != "_"
                    and _followed_by_dot(expression, match.end())):
                out.append("%s#%s" % (document, word))
            else:
                out.append(word)
            i = match.end()
            continue
        if expression[i].isdigit():  # numbers like 1e5 must not start an identifier
            match = re.compile(r"\d+(\.\d*)?([eE][+-]?\d+)?").match(expression, i)
            out.append(match.group(0))
            i = match.end()
            continue
        out.append(expression[i])
        i += 1
    return "".join(out)


def _followed_by_dot(text, index):
    return index < len(text) and text[index] == "."


def _after_hash(text, index):
    return index > 0 and text[index - 1] == "#"


def references(expression, names, labels):
    """True if the expression mentions one of the objects."""
    return rewrite(expression, names, labels, "\x00") != expression
