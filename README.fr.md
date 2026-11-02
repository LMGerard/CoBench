# CoBench

Un atelier FreeCAD pour travailler à plusieurs sur un même projet. Les fichiers
`.FCStd` du projet sont dans n'importe quel dossier partagé : partage réseau, ou dossier
synchronisé par Nextcloud, Dropbox, Google Drive, OneDrive, Syncthing... CoBench ne
dépend d'aucun d'eux.

- **Verrous.** Modifier une pièce la verrouille. Les autres voient qui la modifie, et le
  fichier est en lecture seule chez eux jusqu'à ce qu'elle soit libérée. Fermer la pièce
  la libère.
- **Panneau.** Toutes les pièces du projet avec leur aperçu, leur état (libre, modifiée par
  vous, verrouillée par quelqu'un), qui l'a enregistrée en dernier et où elle est utilisée.
- **Vue assemblage.** Dans un assemblage, les pièces modifiées par quelqu'un d'autre ont un
  cadre rouge en pointillés avec son nom, les vôtres un cadre vert (jaune tant que votre verrou
  n'est pas parvenu aux autres). Dans tout fichier du projet qui contient plusieurs liens vers
  d'autres fichiers et que vous n'avez pas verrouillé (lecture seule), toute la pièce s'éclaire
  au survol et un clic ouvre un petit menu : ouvrir en lecture seule, modifier ou demander, voir
  dans le panneau. Les faces et arêtes n'y sont pas sélectionnables ; verrouillez le fichier
  pour les sélectionner à nouveau.
- **Découper en pièces.** Transforme un document qui contient plusieurs corps en un fichier
  par pièce, un `Variables.FCStd` avec tous les VarSets et tableurs (les pièces continuent à
  les lire : changer une cote met tout à jour) et un `Assemblage.FCStd` qui relie les pièces
  à leur place. Le fichier d'origine n'est pas modifié.
- **On ne modifie que ce qu'on a verrouillé.** Une pièce non verrouillée ne peut pas être
  changée : le mode édition est refusé avant l'ouverture de son panneau, et toute autre
  modification est annulée aussitôt (option).
- **Projet vivant.** Toutes les quelques secondes, CoBench regarde le dossier : les pièces
  enregistrées par les autres sont rechargées dès que le fichier est complètement arrivé, et
  un message signale quand quelqu'un prend ou libère une pièce. *La demander* envoie une
  demande à la personne qui modifie une pièce ; elle répond *La libérer* ou *Pas maintenant*.
- **Dossiers, tags et liens.** Le panneau range les pièces par dossier (ou en vignettes),
  filtre par nom ou par `#tag`, signale les liens cassés et dessine les liens entre pièces.
  Renommez ou déplacez une pièce depuis le panneau : tous les fichiers qui l'utilisent sont
  reliés à nouveau.
- **Arborescence propre.** Les fichiers chargés par un assemblage n'encombrent plus
  l'arborescence de FreeCAD.

FreeCAD 1.0 ou plus récent. Interface en français, anglais, allemand, espagnol, italien, portugais, polonais et chinois (suit la langue de FreeCAD).

## Installation

En attendant le catalogue du gestionnaire d'extensions, copiez ce dossier dans le dossier
`Mod` de FreeCAD puis redémarrez FreeCAD :

| Système | Dossier |
|---------|---------|
| Windows | `%APPDATA%\FreeCAD\Mod\CoBench` (FreeCAD 1.0) ou `%APPDATA%\FreeCAD\v1-1\Mod\CoBench` (1.1) |
| Linux   | `~/.local/share/FreeCAD/Mod/CoBench` (`.../v1-1/Mod/CoBench` en 1.1) |
| macOS   | `~/Library/Application Support/FreeCAD/Mod/CoBench` (`.../v1-1/Mod/CoBench` en 1.1) |

Avec git : `git clone https://github.com/LMGerard/CoBench` dans ce dossier `Mod`.

## Utilisation

1. Choisissez l'atelier **CoBench**. Indiquez votre nom dans *CoBench > Mon nom et options* :
   c'est ce que les autres voient sur vos verrous.
2. *Ouvrir le dossier du projet* et choisissez le dossier des pièces. CoBench y écrit un petit
   `cobench.json` (nom du projet et assemblage central). Si une pièce fait le lien vers les
   autres, elle devient l'assemblage central (★) ; clic droit sur une pièce pour en choisir
   une autre.
3. Double-cliquez une pièce pour l'ouvrir en lecture seule. Pour la modifier, cliquez sur le
   cadenas (ou *Modifier*) : elle est verrouillée et ouverte. Travaillez,
   enregistrez, fermez : le verrou est rendu à la fermeture du document, ou avec *Libérer*.
4. *Ouvrir l'assemblage central* montre qui travaille sur quoi. Cliquez une pièce dans la
   vue 3D pour l'ouvrir en lecture seule, la modifier ou la demander.

CoBench démarre avec FreeCAD : verrous, protection et notifications fonctionnent dans tous
les ateliers, même sans jamais ouvrir l'atelier CoBench. Fermer une pièce la libère, et
enregistrer une pièce libre du projet la verrouille. Chaque option se désactive dans
*Mon nom et options*.

### Couleurs

| Couleur | Signification |
|---------|---------------|
| gris    | libre |
| vert    | vous la modifiez |
| rouge   | quelqu'un d'autre la modifie (nom et ordinateur affichés) |
| orange  | votre propre verrou laissé par un FreeCAD fermé sans le rendre |

## Fonctionnement

`Piece.FCStd` est verrouillée par un fichier `Piece.FCStd.cobench-lock` posé à côté, qui
contient le nom, l'ordinateur et l'heure. Il voyage avec la pièce dans n'importe quel outil
de synchronisation. Son nom ne commence ni par un point ni par `~`, car les clients de
synchronisation ignorent ces fichiers.

- Un verrou laissé par un plantage sur votre ordinateur est repris sans question.
- Le verrou de quelqu'un d'autre peut être pris avec *Prendre le verrou*, après avertissement.
- Si le fichier a changé sur le disque depuis son ouverture, CoBench le recharge avant de
  vous laisser le modifier, et vous prévient si vous enregistrez par-dessus une version
  plus récente.
- Les copies en conflit créées par la synchronisation sont signalées dans le panneau.

**Hors ligne.** CoBench refuse de verrouiller une pièce quand l'ordinateur est hors ligne
(*Prendre quand même* reste possible). Après la prise, le cadenas est jaune tant que le
verrou n'est pas parti, puis vert : vous pouvez alors couper Internet. Sous Windows, CoBench
lit l'état donné par le client de synchro (OneDrive, Nextcloud en fichiers virtuels...) ;
ailleurs, il attend que l'ordinateur soit resté en ligne quelques secondes (10 s, réglable).
À chaque enregistrement, `Piece.FCStd.cobench-stamp` note qui a enregistré et l'empreinte du
fichier : si votre copie est plus ancienne quand vous prenez la pièce, CoBench vous le dit.

**Verrous en temps réel (option Supabase).** Par défaut, les verrous sont des fichiers à côté
des pièces et voyagent avec la synchro. Pour des verrous instantanés, un projet peut les garder
dans une base Supabase gratuite ; les fichiers des pièces restent dans le dossier partagé.
1. Créez un projet sur supabase.com.
2. Dans FreeCAD, *CoBench > Mon nom et options > Verrous du projet* : cochez *Base Supabase*,
   cliquez sur *Copier le script SQL*, collez-le dans Supabase > *SQL Editor* et cliquez sur
   *Run* (une seule fois).
3. Collez l'URL du projet et la clé **anon / publishable** (Supabase > *Project Settings* >
   *API*), jamais la clé *service_role / secret*. *Tester*, puis *OK*.

Le réglage est enregistré dans `cobench.json` : vos collègues n'ont rien à faire. La base
refuse un second verrou sur la même pièce, et retient l'empreinte de la dernière version de
chaque pièce : si votre copie n'est pas encore arrivée par la synchro, CoBench garde la pièce
pour vous et l'ouvre dès qu'elle est là. Hors ligne, on ne peut ni prendre ni rendre une pièce
(un rendu en attente part au retour de la connexion).

**Limite :** avec un dossier synchronisé, deux personnes qui ouvrent la même pièce dans le
délai de synchronisation ne verront pas le verrou de l'autre. Sur un partage réseau, le
verrou est immédiat.

Rien n'est écrit dans vos documents FreeCAD : les cadres colorés n'existent que dans la
vue 3D.

## Licence

LGPL-2.1 ou ultérieure, comme FreeCAD.
