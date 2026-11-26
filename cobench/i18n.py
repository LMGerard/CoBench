# SPDX-License-Identifier: LGPL-2.1-or-later
"""Translations.  English is the source language; the language follows FreeCAD's.

French is below; other languages are JSON files in cobench/translations/
(<code>.json: English text -> translation).  To add one, copy a JSON file,
translate the values and add the language to _FREECAD_NAMES.
"""

import json
import locale
import os

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
    "Select a part. Double-click to open it read-only.":
        "Sélectionnez une pièce. Double-cliquez pour l'ouvrir en lecture seule.",
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
    'An arrow goes from a file to the parts it uses. Click to select, double-click to open read-only.':
        "Une flèche va d'un fichier vers les pièces qu'il utilise. Clic pour sélectionner, double-clic pour ouvrir en lecture seule.",
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
    'Cannot reach the lock database (offline?): {name} was not locked.':
        "Impossible de joindre la base des verrous (hors ligne ?) : {name} n'a pas été verrouillée.",
    'Cannot reach {url} ({error}).':
        'Impossible de joindre {url} ({error}).',
    'Copy the SQL script':
        'Copier le script SQL',
    'Enter the project URL and the anon / publishable key.':
        "Saisissez l'URL du projet et la clé anon / publishable.",
    'Lock database reachable again.':
        'Base des verrous de nouveau joignable.',
    'Lock database: {error}':
        'Base des verrous : {error}',
    'Lock files next to the parts (any shared folder)':
        'Fichiers de verrou à côté des pièces (tout dossier partagé)',
    'Locks of the project':
        'Verrous du projet',
    'Locks of the project {name}':
        'Verrous du projet {name}',
    'Paste it once in Supabase > SQL Editor, then Run':
        'À coller une fois dans Supabase > SQL Editor, puis Run',
    'Project URL:':
        'URL du projet :',
    'Public key:':
        'Clé publique :',
    'Release your parts before changing where the locks are kept.':
        "Libérez vos pièces avant de changer l'endroit où sont gardés les verrous.",
    'SQL script copied. In Supabase, open SQL Editor, paste it and click Run.':
        'Script SQL copié. Dans Supabase, ouvrez SQL Editor, collez-le et cliquez sur Run.',
    'Saved in cobench.json: everybody opening the project uses the same locks. The part files stay in the shared folder.':
        'Enregistré dans cobench.json : tous ceux qui ouvrent le projet utilisent les mêmes verrous. Les fichiers des pièces restent dans le dossier partagé.',
    'Supabase database (real time)':
        'Base Supabase (temps réel)',
    'Supabase refused the key ({status}). Use the anon / publishable key.':
        'Supabase a refusé la clé ({status}). Utilisez la clé anon / publishable.',
    'Test':
        'Tester',
    'The CoBench tables are missing: run the SQL script in Supabase.':
        'Les tables CoBench sont absentes : lancez le script SQL dans Supabase.',
    'The anon / publishable key, never the service_role / secret key':
        'La clé anon / publishable, jamais la clé service_role / secret',
    'The last version of {name}, saved by {user}, has not arrived on this computer yet.':
        "La dernière version de {name}, enregistrée par {user}, n'est pas encore arrivée sur cet ordinateur.",
    'The lock database is ready.':
        'La base des verrous est prête.',
    'The part stays locked for you: CoBench opens it as soon as the file has arrived. If you edit this copy, the other version will be lost.':
        "La pièce reste verrouillée pour vous : CoBench l'ouvre dès que le fichier est arrivé. Si vous modifiez cette copie, l'autre version sera perdue.",
    'you are editing (waiting for the last version)':
        'vous la modifiez (en attente de la dernière version)',
    '{name} has arrived: opened for editing.':
        '{name} est arrivée : ouverte pour modification.',
    '{name} locked: waiting for the last version.':
        '{name} verrouillée : en attente de la dernière version.',
    '{what}: Supabase error {status} {message}':
        '{what} : erreur Supabase {status} {message}',
    "{name} could not be saved, so it stays locked for you.\n\n{error}":
        "{name} n'a pas pu être enregistrée : elle reste verrouillée pour vous.\n\n{error}",
    "The new version of {name} could not be recorded in the lock database, so it stays locked for you (otherwise others could edit an older copy).\n\n{error}":
        "La nouvelle version de {name} n'a pas pu être inscrite dans la base des verrous : la pièce reste verrouillée pour vous (sinon les autres pourraient modifier une copie plus ancienne).\n\n{error}",
    "In assemblies, pick whole parts and show a small menu (instead of selecting faces)":
        "Dans les assemblages, désigner des pièces entières et afficher un petit menu (au lieu de sélectionner des faces)",
    "Show in the panel": "Voir dans le panneau",
    "CoBench selection in assemblies":
        "Sélection CoBench dans les assemblages",
    "On: clicking a part of an assembly opens the CoBench menu. Off: FreeCAD's normal selection (several parts, tree, Space to hide)":
        "Activée : un clic sur une pièce d'un assemblage ouvre le menu CoBench. Désactivée : sélection normale de FreeCAD (plusieurs pièces, arborescence, Espace pour masquer)",
    "CoBench selection in assemblies: on":
        "Sélection CoBench dans les assemblages : activée",
    "CoBench selection in assemblies: off (FreeCAD's normal selection)":
        "Sélection CoBench dans les assemblages : désactivée (sélection normale de FreeCAD)",
    "Show in the tree":
        "Montrer dans l'arborescence",
    "Hide":
        "Masquer",
    "Switch to FreeCAD selection":
        "Passer à la sélection FreeCAD",
    # Connection state (core/health.py)
    'CoBench version':
        'Version de CoBench',
    'Lock database':
        'Base des verrous',
    'Identity':
        'Identité',
    'Connected and up to date':
        'Connecté et à jour',
    ' and {count} more':
        ' et {count} autres',
    'Server → this computer':
        'Serveur → ce PC',
    'This computer → server':
        'Ce PC → serveur',
    'Not checked: no copy of the files is watched on the server for this project.':
        "Non vérifié : aucune copie des fichiers n'est surveillée sur le serveur pour ce projet.",
    '{count} problems: {problem}':
        '{count} problèmes : {problem}',
    'Problem: {problem}':
        'Problème : {problem}',
    'Restart FreeCAD.':
        'Redémarrez FreeCAD.',
    'Update CoBench (Add-on manager, or git pull in its folder), then restart FreeCAD.':
        "Mettez CoBench à jour (gestionnaire d'extensions, ou git pull dans son dossier), puis redémarrez FreeCAD.",
    'CoBench {running} is too old: this project needs {minimum} or newer.':
        'CoBench {running} est trop ancien : ce projet demande la version {minimum} ou plus récente.',
    'Lock files next to the parts':
        'Fichiers de verrou à côté des pièces',
    'The server stopped reporting its files {minutes} min ago: the sync cannot be checked.':
        "Le serveur ne donne plus l'état de ses fichiers depuis {minutes} min : la synchro ne peut pas être vérifiée.",
    'Tell whoever runs the server (cobench_scanner).':
        'Prévenez la personne qui gère le serveur (cobench_scanner).',
    'Check the sync client (Nextcloud...) of this computer: is it running, connected, without errors? Restart it if needed.':
        'Vérifiez le client de synchro (Nextcloud...) de ce PC : est-il lancé, connecté, sans erreur ? Relancez-le si besoin.',
    'You appear as {user}: choose the name the others see.':
        'Vous apparaissez comme {user} : choisissez le nom que voient les autres.',
    'CoBench > My name and options.':
        'CoBench > Mon nom et options.',
    '{user} on {host}':
        '{user} sur {host}',
    'CoBench {installed} is installed but FreeCAD still runs {running}.':
        'CoBench {installed} est installé mais FreeCAD utilise encore la {running}.',
    'Cannot reach the lock database: {error}':
        'Base des verrous injoignable : {error}',
    'Check the internet connection of this computer.':
        'Vérifiez la connexion internet de ce PC.',
    'Checking...':
        'Vérification...',
    'CoBench {latest} is available (you have {running}).':
        'CoBench {latest} est disponible (vous avez la {running}).',
    "Check the project's lock settings (cobench.json).":
        'Vérifiez les réglages des verrous du projet (cobench.json).',
    'CoBench {running}, up to date':
        'CoBench {running}, à jour',
    'CoBench {running}':
        'CoBench {running}',
    'Connecting to the lock database...':
        'Connexion à la base des verrous...',
    'Connected':
        'Connectée',
    '{name} cannot be locked: CoBench is not connected as it should be.':
        "Impossible de verrouiller {name} : CoBench n'est pas connecté comme il faut.",
    '{name} is released as soon as the sync client has sent it to the server.':
        "{name} sera libérée dès que le client de synchro l'aura envoyée sur le serveur.",
    '{name} stays locked for you.':
        '{name} reste verrouillée pour vous.',
    'Fix this first: otherwise you could edit an old copy, or your work could stay on this computer. The CoBench panel shows the state of the connection.':
        "Réglez d'abord ce problème : sinon vous pourriez modifier une ancienne copie, ou votre travail pourrait rester sur ce PC. Le panneau CoBench montre l'état de la connexion.",
    '{name} cannot be moved: CoBench is not connected as it should be ({problem}).':
        "Impossible de déplacer {name} : CoBench n'est pas connecté comme il faut ({problem}).",
    'CoBench: no project':
        'CoBench : aucun projet',
    '{name} has reached the server: released.':
        '{name} est arrivée sur le serveur : libérée.',
    "{name} released (the server's copy can no longer be checked).":
        '{name} libérée (la copie du serveur ne peut plus être vérifiée).',
    'CoBench is connected as it should be again.':
        'CoBench est de nouveau connecté comme il faut.',
    'parts cannot be locked until it is fixed.':
        "impossible de verrouiller une pièce tant que ce n'est pas réglé.",
    'being sent to the server (released once it has arrived)':
        'envoi vers le serveur (libérée dès son arrivée)',
    'State of the connection: click for details':
        'État de la connexion : cliquez pour le détail',
    'Parts cannot be locked until this is fixed.':
        "Impossible de verrouiller une pièce tant que ce n'est pas réglé.",
    'Tell me when a new version of CoBench is available':
        'Me prévenir quand une nouvelle version de CoBench est disponible',
    '{count} files saved on the server have not arrived here for more than {minutes} min: {names}':
        '{count} fichiers enregistrés sur le serveur ne sont pas arrivés sur ce PC depuis plus de {minutes} min : {names}',
    'Receiving {count} files: {names}':
        'Réception de {count} fichiers : {names}',
    'Up to date':
        'À jour',
    '{count} files changed here have not reached the server for more than {minutes} min: {names}':
        '{count} fichiers modifiés sur ce PC ne sont pas arrivés sur le serveur depuis plus de {minutes} min : {names}',
    'Sending {count} files: {names}':
        'Envoi de {count} fichiers : {names}',
    'Everything sent':
        'Tout est envoyé',
}

# Other languages live in cobench/translations/<code>.json (English text -> translation).
_HERE = os.path.dirname(os.path.abspath(__file__))
_FREECAD_NAMES = {  # first word of the language name in FreeCAD's preferences -> code
    "french": "fr", "german": "de", "spanish": "es", "italian": "it",
    "portuguese": "pt", "polish": "pl", "chinese": "zh",
}

_catalog = None


def catalog(code):
    """The translations for a language code ('' or 'en' -> none)."""
    if code == "fr":
        return FR
    if not code or code == "en":
        return {}
    try:
        with open(os.path.join(_HERE, "translations", code + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _detect():
    name = ""
    try:
        import FreeCAD
        name = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/General").GetString("Language", "")
    except Exception:
        pass
    if name:
        first = name.replace(",", " ").split()[0].lower() if name.split() else ""
        return catalog(_FREECAD_NAMES.get(first, ""))
    try:
        code = (locale.getlocale()[0] or "")[:2].lower()
    except Exception:
        code = ""
    return catalog(code if code in _FREECAD_NAMES.values() else "")


def tr(text, **values):
    global _catalog
    if _catalog is None:
        _catalog = _detect()
    result = _catalog.get(text, text)
    return result.format(**values) if values else result
