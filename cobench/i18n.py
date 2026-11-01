# SPDX-License-Identifier: LGPL-2.1-or-later
"""Translations.  English is the source language; the language follows FreeCAD's.

To add a language, copy the FR dictionary, translate the values and register
it in CATALOGS under the name FreeCAD gives the language in its preferences.
"""

import locale

FR = {
    "you": "vous",
    "Project panel": "Panneau du projet",
    "Show the parts of the project, their previews and who edits them":
        "Afficher les pièces du projet, leurs aperçus et qui les modifie",
    "Open project folder...": "Ouvrir le dossier du projet...",
    "Choose the folder holding the project's .FCStd files (local, network or synchronised)":
        "Choisir le dossier qui contient les fichiers .FCStd du projet (local, réseau ou synchronisé)",
    "Open central assembly": "Ouvrir l'assemblage central",
    "Open the project's central assembly; locked parts are shown in colour":
        "Ouvrir l'assemblage central du projet ; les pièces verrouillées apparaissent en couleur",
    "Use active document as central assembly": "Utiliser le document actif comme assemblage central",
    "Remember the active document as the project's central assembly":
        "Retenir le document actif comme assemblage central du projet",
    "Edit part": "Modifier la pièce",
    "Lock the selected part (or the active document) and open it for editing":
        "Verrouiller la pièce sélectionnée (ou le document actif) et l'ouvrir pour la modifier",
    "Release part": "Libérer la pièce",
    "Release the lock of the active document so others can edit it":
        "Libérer le verrou du document actif pour que les autres puissent le modifier",
    "Release all my parts": "Libérer toutes mes pièces",
    "Release every part locked by this FreeCAD (unsaved changes are offered for saving)":
        "Libérer toutes les pièces verrouillées par ce FreeCAD (les modifications non enregistrées "
        "sont proposées à l'enregistrement)",
    "My name and options...": "Mon nom et options...",
    "Name shown on your locks, read-only protection, boxes in assemblies":
        "Nom affiché sur vos verrous, protection en lecture seule, cadres dans les assemblages",
    "Name shown on your locks:": "Nom affiché sur vos verrous :",
    "Also write it as author when FreeCAD saves": "L'inscrire aussi comme auteur à chaque enregistrement",
    "Make parts locked by others read-only on this computer":
        "Mettre en lecture seule sur cet ordinateur les pièces verrouillées par d'autres",
    "Show locks as coloured boxes in assemblies": "Afficher les verrous en cadres colorés dans les assemblages",
    "Computer: {host}": "Ordinateur : {host}",
    "Select a part of the project (in the 3D view, the tree or the CoBench panel).":
        "Sélectionnez une pièce du projet (dans la vue 3D, l'arborescence ou le panneau CoBench).",
    "locked by {user}": "verrouillée par {user}",
    "free": "libre",
    "you are editing": "modifiée par vous",
    "your old lock (FreeCAD closed)": "votre ancien verrou (FreeCAD fermé)",
    "Name shown to the others on your locks:": "Nom affiché aux autres sur vos verrous :",
    "Choose the project folder": "Choisir le dossier du projet",
    "Open the central assembly": "Ouvrir l'assemblage central",
    "Refresh": "Actualiser",
    "Filter parts": "Filtrer les pièces",
    "List": "Liste",
    "Switch between thumbnails and a compact list": "Basculer entre vignettes et liste compacte",
    "Edit": "Modifier",
    "Lock the part and open it": "Verrouiller la pièce et l'ouvrir",
    "Open read-only": "Ouvrir en lecture seule",
    "Release": "Libérer",
    "Give the part back so others can edit it": "Rendre la pièce pour que les autres puissent la modifier",
    "Take the lock": "Prendre le verrou",
    "For a lock left behind after a crash": "Pour un verrou resté en place après un plantage",
    "You appear as <b>{user}</b> (<a href='#'>change</a>)": "Vous apparaissez comme <b>{user}</b> (<a href='#'>changer</a>)",
    "Saved {when}{by}": "Enregistrée le {when}{by}",
    "Use as central assembly": "Utiliser comme assemblage central",
    "Show in file explorer": "Afficher dans l'explorateur de fichiers",
    "<b>No project</b><br>Choose a folder holding .FCStd files.":
        "<b>Aucun projet</b><br>Choisissez un dossier qui contient des fichiers .FCStd.",
    "Uses: {parts}": "Utilise : {parts}",
    "Used in: {parts}": "Utilisée dans : {parts}",
    "Show": "Afficher",
    "Select a part. Double-click to edit it.": "Sélectionnez une pièce. Double-cliquez pour la modifier.",
    "Could not read the file (still syncing?).": "Lecture du fichier impossible (synchronisation en cours ?).",
    "{name} not found.": "{name} introuvable.",
    "Conflict copies made by the sync client: {files}":
        "Copies en conflit créées par la synchronisation : {files}",
    "by {user}": "par {user}",
    "{user} on {host}, since {when}": "{user} sur {host}, depuis le {when}",
    "{name} locked: you can edit it.": "{name} verrouillée : vous pouvez la modifier.",
    "{name} released.": "{name} libérée.",
    "{name} reloaded: it had changed on disk.": "{name} rechargée : elle avait changé sur le disque.",
    "{name} is being edited by {who}.": "{name} est en cours de modification par {who}.",
    "Locked since {when}.": "Verrouillée depuis le {when}.",
    "You can open it read-only, or take the lock if you are sure that person no longer works on it "
    "(their unsaved work would be lost when they save).":
        "Vous pouvez l'ouvrir en lecture seule, ou prendre le verrou si vous êtes sûr que cette "
        "personne n'y travaille plus (son travail non enregistré serait perdu à son prochain "
        "enregistrement).",
    "{name} was locked by {who} a moment ago.": "{name} vient d'être verrouillée par {who}.",
    "{name} opened read-only: {who} is editing it.": "{name} ouverte en lecture seule : {who} la modifie.",
    "{name} has unsaved changes. Save before releasing it?":
        "{name} a des modifications non enregistrées. Enregistrer avant de la libérer ?",
    "Take the lock of {name} from {who}?\n\nOnly do this if that person no longer works on it, "
    "for example after a crash.":
        "Prendre le verrou de {name} à {who} ?\n\nÀ faire seulement si cette personne n'y travaille "
        "plus, par exemple après un plantage.",
    "{name} was saved by someone else after you opened it, and your copy has unsaved changes.\n\n"
    "Reload the file and lose your changes?":
        "{name} a été enregistrée par quelqu'un d'autre après votre ouverture, et votre copie a des "
        "modifications non enregistrées.\n\nRecharger le fichier et perdre vos modifications ?",
    "You saved {name} while {who} holds it. If the save succeeded, their next save will overwrite "
    "yours (or yours overwrote theirs). Agree with them on which version to keep.":
        "Vous avez enregistré {name} alors que {who} la détient. Si l'enregistrement a réussi, son "
        "prochain enregistrement écrasera le vôtre (ou le vôtre a écrasé le sien). Mettez-vous "
        "d'accord sur la version à garder.",
    "{name} saved and locked: release it when you are done.":
        "{name} enregistrée et verrouillée : libérez-la quand vous avez fini.",
    "{name} had been saved by someone else after you opened it. Your save replaced their version.":
        "{name} avait été enregistrée par quelqu'un d'autre après votre ouverture. Votre "
        "enregistrement a remplacé sa version.",
}

CATALOGS = {"French": FR}
_LOCALE_CATALOGS = {"fr": FR}

_catalog = None


def _detect():
    name = ""
    try:
        import FreeCAD
        name = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/General").GetString("Language", "")
    except Exception:
        pass
    if name:
        return CATALOGS.get(name, {})
    try:
        code = (locale.getlocale()[0] or "")[:2].lower()
    except Exception:
        code = ""
    return _LOCALE_CATALOGS.get(code, {})


def tr(text, **values):
    global _catalog
    if _catalog is None:
        _catalog = _detect()
    result = _catalog.get(text, text)
    return result.format(**values) if values else result
