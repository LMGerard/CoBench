# CoBench

*Version française : [README.fr.md](README.fr.md)*

A FreeCAD workbench to work on one project with other people. Put the project's
`.FCStd` files in any shared folder: a network share, or a folder synchronised by
Nextcloud, Dropbox, Google Drive, OneDrive, Syncthing... CoBench does not depend
on any of them.

- **Locks.** Editing a part locks it. Everybody else sees who edits it, and the file is
  read-only on their computer until it is released. Closing the part releases it.
- **Panel.** Every part of the project with its preview, its state (free, edited by you,
  locked by someone), who saved it last and which parts use it.
- **Assembly view.** In an assembly, parts edited by someone else are boxed in red with
  the person's name, yours in green. Double-click a part in the 3D view to edit its file.
- **Split into part files.** Turns one document holding many bodies into one file per part,
  a `Variables.FCStd` with every VarSet and spreadsheet (parts keep reading them, so changing
  a value still updates everything) and an `Assemblage.FCStd` linking the parts in place.
  The original file is not modified.
- **Only edit what you locked.** A part you have not locked cannot be changed: edit mode is
  refused before its panel opens, and any other change is undone at once (option).
- **Live project.** Every few seconds CoBench looks at the folder: parts saved by others are
  reloaded once the file has fully arrived, and you are told when someone takes or releases
  a part. *Ask for it* sends a request to the person editing a part; they answer
  *Release it* or *Not now*.
- **Folders, tags and links.** The panel shows the parts by folder (or as thumbnails), filters
  by name or `#tag`, flags broken links, and draws the links between parts. Rename or move a
  part from the panel: every file using it is relinked.
- **Clean tree.** The files an assembly loads stay out of FreeCAD's tree.

FreeCAD 1.0 or later. English and French.

## Install

Until CoBench is in the Addon Manager catalogue, copy this folder into FreeCAD's
`Mod` folder and restart FreeCAD:

| System  | Folder |
|---------|--------|
| Windows | `%APPDATA%\FreeCAD\Mod\CoBench` (FreeCAD 1.0) or `%APPDATA%\FreeCAD\v1-1\Mod\CoBench` (1.1) |
| Linux   | `~/.local/share/FreeCAD/Mod/CoBench` (`.../v1-1/Mod/CoBench` for 1.1) |
| macOS   | `~/Library/Application Support/FreeCAD/Mod/CoBench` (`.../v1-1/Mod/CoBench` for 1.1) |

With git: `git clone https://github.com/LMGerard/CoBench` in that `Mod` folder.

## Use

1. Select the **CoBench** workbench. Set your name with *CoBench > My name and options*:
   it is what others see on your locks.
2. *Open project folder* and pick the folder holding the parts. CoBench writes a small
   `cobench.json` there (project name and central assembly). If one part links to the
   others, it becomes the central assembly (★); right-click a part to choose another.
3. Double-click a part (or *Edit*) to lock and open it. Work, save, close: the lock is
   released when you close the document, or with *Release*.
4. *Open central assembly* shows who works on what. Double-click a part in the 3D view,
   or select it and use *Edit part* (also in the right-click menu), to edit its file.

CoBench starts with FreeCAD: locks, protection and notifications work in every workbench,
even if you never open the CoBench one. Closing a part releases it, and saving a free part
of the project locks it. Each option can be turned off in *My name and options*.

### What the colours mean

| Colour | Meaning |
|--------|---------|
| grey   | free |
| green  | you are editing it |
| red    | someone else is editing it (name and machine shown) |
| orange | your own lock left by a FreeCAD that closed without releasing it |

## How it works

`Part.FCStd` is locked by a file `Part.FCStd.cobench-lock` next to it, holding the
name, the computer and the time. It travels with the part through any sync tool.
The name does not start with a dot or `~` because sync clients skip such files.

- A lock left by a crash on your own computer is taken back silently next time.
- Someone else's lock can be taken with *Take the lock*, after a warning.
- If the file changed on disk since you opened it, CoBench reloads it before you edit,
  and warns you if you save over a newer version.
- Conflict copies made by the sync client are listed in the panel.

**Limit:** with a synchronised folder, two people who open the same part within the
synchronisation delay will not see each other's lock. On a network share the lock is
immediate.

Nothing is written into your FreeCAD documents: the coloured boxes exist only in the
3D view.

## Tests

The lock, project and file logic does not need FreeCAD:

```
python -m pytest tests
```

## Licence

LGPL-2.1-or-later, like FreeCAD.
