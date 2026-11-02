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
    "Split into part files...": "Découper en pièces...",
    "One file per part, shared variables in Variables.FCStd and links in Assemblage.FCStd "
    "(the original file is not modified)":
        "Un fichier par pièce, variables partagées dans Variables.FCStd et liens dans "
        "Assemblage.FCStd (le fichier d'origine n'est pas modifié)",
    "Save the document first.": "Enregistrez d'abord le document.",
    "Save the document first: the split uses the saved file.":
        "Enregistrez d'abord le document : le découpage part du fichier enregistré.",
    "The folder {folder} is not empty.": "Le dossier {folder} n'est pas vide.",
    "Close the document named {name} first.": "Fermez d'abord le document nommé {name}.",
    "No part found (PartDesign bodies, App::Part or solids).":
        "Aucune pièce trouvée (corps PartDesign, App::Part ou solides).",
    "Could not keep the names of: {names}": "Impossible de garder les noms de : {names}",
    "{count} variable sets in {file}": "{count} ensembles de variables dans {file}",
    "{part} uses {others}: a copy of them is inside its file.":
        "{part} utilise {others} : une copie se trouve dans son fichier.",
    "{part}: {count} expressions could not be restored.":
        "{part} : {count} expressions n'ont pas pu être rétablies.",
    "{count} parts written.": "{count} pièces écrites.",
    "Central assembly: {file}": "Assemblage central : {file}",
    "Where to create the folder of parts?": "Où créer le dossier des pièces ?",
    "Split {name} into one file per part in:\n{folder}\n\nThe original file is not modified.":
        "Découper {name} en un fichier par pièce dans :\n{folder}\n\nLe fichier d'origine "
        "n'est pas modifié.",
    'A file name cannot contain < > : " / \\ | ? *':
        'Un nom de fichier ne peut pas contenir < > : " / \\ | ? *',
    'A newer {name} was saved by someone else; your copy has unsaved changes and was not reloaded.':
        "Une version plus récente de {name} a été enregistrée par quelqu'un d'autre ; votre copie a des modifications non enregistrées et n'a pas été rechargée.",
    'Activity':
        'Activité',
    'An arrow goes from a file to the parts it uses. Click to select, double-click to edit.':
        "Une flèche va d'un fichier vers les pièces qu'il utilise. Clic pour sélectionner, double-clic pour modifier.",
    'Ask for it':
        'La demander',
    'Ask for the part':
        'Demander la pièce',
    'Ask the person editing it to release it':
        'Demander à la personne qui la modifie de la libérer',
    'Ask the person editing the selected part to release it':
        'Demander à la personne qui modifie la pièce sélectionnée de la libérer',
    'Broken link: {file} not found':
        'Lien cassé : {file} introuvable',
    'Cannot move {name}: {parts} locked by others.':
        "Impossible de déplacer {name} : {parts} verrouillé par quelqu'un d'autre.",
    'Choose a folder inside the project.':
        'Choisissez un dossier dans le projet.',
    'Crossed locks: {who} took {name} at the same time as you. Agree on who keeps it before saving.':
        "Verrous croisés : {who} a pris {name} en même temps que vous. Mettez-vous d'accord sur qui la garde avant d'enregistrer.",
    'Filter (name, folder or #tag)':
        'Filtrer (nom, dossier ou #tag)',
    'Folders':
        'Dossiers',
    'Hide from the tree the files an assembly loads':
        "Masquer dans l'arborescence les fichiers chargés par un assemblage",
    'Hide parts without links':
        'Masquer les pièces sans lien',
    'Links between parts':
        'Liens entre les pièces',
    'More':
        'Plus',
    'Move to folder...':
        'Déplacer vers un dossier...',
    'Move {name} to':
        'Déplacer {name} vers',
    'New name for {name}:':
        'Nouveau nom pour {name} :',
    'No links between the parts of this project.':
        'Aucun lien entre les pièces de ce projet.',
    'Not now':
        'Pas maintenant',
    'Notify me when a part is locked, released or asked for':
        'Me prévenir quand une pièce est verrouillée, libérée ou demandée',
    'Part':
        'Pièce',
    'Refuse changes to parts I have not locked':
        "Refuser les modifications des pièces que je n'ai pas verrouillées",
    'Release it':
        'La libérer',
    'Reload parts saved by others automatically':
        'Recharger automatiquement les pièces enregistrées par les autres',
    'Rename...':
        'Renommer...',
    'Request sent to {user} for {name}.':
        'Demande envoyée à {user} pour {name}.',
    'Requested by {user}':
        'Demandée par {user}',
    'Save or close {name} first.':
        "Enregistrez ou fermez d'abord {name}.",
    'Show the links between parts':
        'Afficher les liens entre les pièces',
    'Show which file uses which part, coloured by who edits them':
        'Quel fichier utilise quelle pièce, en couleur selon qui les modifie',
    'State':
        'État',
    'Switch between folders and thumbnails':
        'Basculer entre dossiers et vignettes',
    'Tags for {name}, separated by spaces (known: {known}):':
        'Tags de {name}, séparés par des espaces (existants : {known}) :',
    'Tags...':
        'Tags...',
    'Thumbnails':
        'Vignettes',
    'You can ask for it, open it read-only, or take the lock if you are sure that person no longer works on it (their unsaved work would be lost when they save).':
        "Vous pouvez la demander, l'ouvrir en lecture seule, ou prendre le verrou s'il est certain que cette personne n'y travaille plus (son travail non enregistré serait perdu quand elle enregistrera).",
    '{count} broken links: a linked file was moved or deleted.':
        '{count} liens cassés : un fichier lié a été déplacé ou supprimé.',
    '{name} already exists.':
        '{name} existe déjà.',
    '{name} is free: you can take it.':
        '{name} est libre : vous pouvez la prendre.',
    '{name} is locked by {who}: it cannot be changed.':
        '{name} est verrouillée par {who} : impossible de la modifier.',
    '{name} is not locked: click Edit (CoBench) before changing it.':
        "{name} n'est pas verrouillée : cliquez sur Modifier (CoBench) avant de la changer.",
    '{name} updated (saved by {user}).':
        '{name} mise à jour (enregistrée par {user}).',
    '{name} updated.':
        '{name} mise à jour.',
    '{name} was locked by someone a moment ago.':
        "{name} vient d'être verrouillée par quelqu'un.",
    '{old} moved to {new}; {count} files relinked.':
        '{old} déplacée vers {new} ; {count} fichiers reliés.',
    '{user} keeps {name} for now.':
        '{user} garde {name} pour le moment.',
    '{user} released {name}.':
        '{user} a libéré {name}.',
    '{user} took {name}.':
        '{user} a pris {name}.',
    '{user} would like to edit {name}.':
        '{user} voudrait modifier {name}.',
    'A lock counts as sent after staying online:':
        'Un verrou est considéré comme envoyé après être resté en ligne :',
    'Edit this copy anyway':
        'Modifier cette copie quand même',
    'Free: lock the selected part (or the active document) and open it':
        "Libre : verrouiller la pièce sélectionnée (ou le document actif) et l'ouvrir",
    'Lock and edit':
        'Verrouiller et modifier',
    'Lock on {name} sent: you can go offline.':
        'Verrou de {name} envoyé : vous pouvez vous déconnecter.',
    'Offline: the lock on {name} may not have reached the others yet.':
        "Hors ligne : le verrou de {name} n'est peut-être pas encore arrivé chez les autres.",
    'Refuse to lock a part when this computer is offline':
        'Refuser de verrouiller une pièce quand cet ordinateur est hors ligne',
    'Someone could take the same part meanwhile. Lock your parts before going offline.':
        "Quelqu'un pourrait prendre la même pièce entre-temps. Verrouillez vos pièces avant de vous déconnecter.",
    'Take it anyway':
        'Prendre quand même',
    'The last version of {name}, saved by {user} on {when}, has not arrived on this computer yet.':
        "La dernière version de {name}, enregistrée par {user} le {when}, n'est pas encore arrivée sur cet ordinateur.",
    'This computer is offline: the others will not see your lock on {name} until it is back online.':
        "Cet ordinateur est hors ligne : les autres ne verront votre verrou sur {name} qu'au retour de la connexion.",
    'Used when the sync client does not say whether the lock was sent':
        "Utilisé quand le client de synchro n'indique pas si le verrou est parti",
    'Wait':
        'Attendre',
    'Wait for the sync, then edit it again. If you edit this copy, the other version will be lost.':
        "Attendez la synchro puis modifiez-la à nouveau. Si vous modifiez cette copie, l'autre version sera perdue.",
    'you are editing (lock being sent)':
        "vous la modifiez (verrou en cours d'envoi)",
    '{name} is only in the cloud: it is being downloaded.':
        "{name} n'était que dans le cloud : elle est en cours de téléchargement.",
    'Lock':
        'Verrou',
    'Select a part of the project to lock or release it':
        'Sélectionnez une pièce du projet pour la verrouiller ou la libérer',
    'You are editing it; the lock is being sent (wait before going offline). Click to release it':
        "Vous la modifiez ; le verrou est en cours d'envoi (attendez avant de vous déconnecter). Cliquez pour la libérer",
    'You are editing it. Click to release it':
        'Vous la modifiez. Cliquez pour la libérer',
    'Locked by someone else. Click to ask for it':
        "Verrouillée par quelqu'un d'autre. Cliquez pour la demander",
    'Take back':
        'Reprendre',
    'Your own lock left by a FreeCAD that closed. Click to take it back':
        'Votre propre verrou laissé par un FreeCAD fermé. Cliquez pour le reprendre',
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
