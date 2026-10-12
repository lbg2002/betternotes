<p align="center">
  <img src="data/icons/hicolor/scalable/apps/com.github.paperhead.BetterNotes.svg" width="128" height="128" alt="BetterNotes icon">
</p>

<h1 align="center">BetterNotes</h1>

<p align="center">
  <strong>Beautiful sticky notes for your Linux desktop</strong>
</p>

<p align="center">
  <a href="#features">Features</a>&nbsp;&bull;
  <a href="#installation">Installation</a>&nbsp;&bull;
  <a href="#building-from-source">Building</a>&nbsp;&bull;
  <a href="#keyboard-shortcuts">Shortcuts</a>&nbsp;&bull;
  <a href="#supported-systems">Supported Systems</a>&nbsp;&bull;
  <a href="#license">License</a>
</p>

---

BetterNotes is a full-featured sticky notes application built with GTK4 and Libadwaita. Create colorful notes that stay on top of your desktop, organize them with tags, format your text, and find anything instantly with full-text search.

## 中文精简版 / Chinese lightweight fork (experimental)

> This fork is under development. **Do not replace a working Snap installation
> until the CI package and manual desktop tests have passed.**

### Features

- Simplified Chinese/English/system-language selection in Preferences
  (restart the app after a language change).
- Compact sticky notes: formatting toolbar hidden by default. The formatting
  button in the note header toggles it without deleting formatting or shortcuts.
- Lightweight dependency-based Debian package. GTK4/Libadwaita/Python are
  installed using your system package manager instead of bundled copies.
- Original notes, tags, search, colors, and XWayland always-on-top retained.

### Build on Ubuntu

```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
  meson ninja-build libgtk-4-dev libadwaita-1-dev gettext \
  libglib2.0-dev-bin
meson setup build --prefix=/usr
meson compile -C build
```

The `Lightweight DEB CI` workflow builds the dependency-based `.deb`.
Its package size is not a measurement of total disk usage: required shared
libraries installed by apt occupy additional space. No benchmark or Ubuntu
26.04 graphical test is claimed yet.

### Preserve note data

Do **not** run Snap and this build simultaneously against a shared note DB.
For a backup while BetterNotes is closed:

```bash
mkdir -p "$HOME/betternotes-backup"
find "$HOME/snap/betternotes" "$HOME/.local/share/betternotes" \
  -name 'notes.db*' -type f -print 2>/dev/null
```

Back up the directory containing your actual notes database, including
`-wal` and `-shm` files, before migrating. Snap user data may be isolated,
so installing the DEB will not automatically import Snap notes. Avoid copying
a database while either application is writing to it.

### Notes

- Localization currently covers many common UI strings but is **not yet a
  comprehensive audited translation**.
- Language changes require restarting; existing open note windows do not
  instantly retranslate.
- GNOME native Wayland does not offer generic application-managed always-on-top;
  the upstream XWayland strategy remains in place.
- Follow the GPL-3.0-or-later license and the upstream copyright notices.

---

## Features

**8 Vibrant Colors** &mdash; Yellow, blue, green, pink, orange, purple, red, and teal. Each note gets its own colored window with matching light and dark mode variants.

**Rich Text Editing** &mdash; Bold, italic, underline, strikethrough, and bullet lists. Format your notes the way you want.

**Always-on-Top Notes** &mdash; Sticky note windows stay above all other windows, just like real sticky notes on your monitor.

**Full-Text Search** &mdash; Powered by SQLite FTS5. Find any note instantly, even across hundreds of notes.

**Tags & Filtering** &mdash; Organize notes with tags and filter your overview by category.

**Trash & Restore** &mdash; Deleted notes go to trash first. Restore them within 30 days or empty trash permanently.

**Auto-Save** &mdash; Notes are saved automatically as you type with a 500ms debounce. Never lose your work.

**Dark Mode** &mdash; Follows your system theme via Libadwaita. All 8 note colors have carefully chosen dark variants.

**Keyboard-Driven** &mdash; Full keyboard shortcut support for power users.

## Installation

### Flatpak (Recommended)

```bash
flatpak-builder --user --install build-flatpak build-aux/flatpak/com.github.paperhead.BetterNotes.json
```

### From Source

See [Building from Source](#building-from-source) below.

## Building from Source

### Dependencies

- Python 3.10+
- GTK 4.10+
- Libadwaita 1.4+
- Meson 0.62+
- Ninja

**Ubuntu/Debian:**

```bash
sudo apt install python3 libgtk-4-dev libadwaita-1-dev meson ninja-build \
  gettext libglib2.0-dev-bin gir1.2-gtk-4.0 gir1.2-adw-1
```

**Fedora:**

```bash
sudo dnf install python3 gtk4-devel libadwaita-devel meson ninja-build \
  gettext glib2-devel
```

**Arch Linux:**

```bash
sudo pacman -S python gtk4 libadwaita meson ninja gettext
```

### Build & Install

```bash
meson setup build --prefix=/usr/local
meson compile -C build
sudo meson install -C build
```

### Development Run

To run without installing:

```bash
./run-dev.sh
```

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+N` | New note |
| `Ctrl+B` | Bold |
| `Ctrl+I` | Italic |
| `Ctrl+U` | Underline |
| `Ctrl+D` | Strikethrough |
| `Ctrl+,` | Preferences |
| `Ctrl+?` | Show all shortcuts |
| `Ctrl+Q` | Quit |

## Supported Systems

### Fully Supported

| System | Desktop | Status |
|---|---|---|
| **Ubuntu 22.04+** | GNOME (X11/XWayland) | Full support including always-on-top |
| **Ubuntu 24.04+** | GNOME (X11/XWayland) | Full support including always-on-top |
| **Fedora 38+** | GNOME (X11/XWayland) | Full support including always-on-top |
| **Arch Linux** | GNOME (X11/XWayland) | Full support including always-on-top |
| **Debian 12+** | GNOME (X11/XWayland) | Full support including always-on-top |
| **openSUSE Tumbleweed** | GNOME (X11/XWayland) | Full support including always-on-top |

### Requirements

- **Operating System:** Linux (any distribution with GTK4 and Libadwaita)
- **Desktop Environment:** GNOME 42+ recommended (works on any GTK4-compatible DE)
- **Display Server:** X11 or XWayland (required for always-on-top note windows)
- **Architecture:** x86_64, aarch64

### Notes on Wayland

BetterNotes runs under XWayland by default (`GDK_BACKEND=x11`) to enable the always-on-top feature for sticky note windows. This is transparent on GNOME Wayland sessions and there is no visual difference. Native Wayland does not allow applications to request always-on-top window placement.

## Project Structure

```
betternotes/
├── build-aux/flatpak/          # Flatpak manifest
├── data/
│   ├── icons/                  # App icon (SVG)
│   ├── resources/              # CSS stylesheet, GResource XML
│   ├── *.desktop.in            # Desktop entry
│   ├── *.metainfo.xml.in       # AppStream metadata
│   └── *.gschema.xml           # GSettings schema
├── src/
│   ├── betternotes/
│   │   ├── application.py      # App singleton, signals, actions
│   │   ├── main_window.py      # Grid overview, search, tag filters
│   │   ├── note_window.py      # Individual sticky note editor
│   │   ├── note_card.py        # Card widget for grid display
│   │   ├── note.py             # Data models
│   │   ├── note_store.py       # SQLite DAL with FTS5
│   │   ├── rich_text_serializer.py  # TextBuffer <-> JSON
│   │   ├── rich_text_toolbar.py     # Formatting toolbar
│   │   ├── auto_save.py        # Debounced auto-save
│   │   ├── colors.py           # Color definitions
│   │   ├── preferences.py      # Preferences dialog
│   │   └── shortcuts.py        # Shortcuts window
│   └── betternotes.in          # Entry point
├── po/                         # i18n scaffolding
└── meson.build                 # Build system
```

## Technology

| Component | Choice |
|---|---|
| Language | Python 3 |
| UI Toolkit | GTK4 + Libadwaita |
| Data Storage | SQLite (WAL mode) |
| Search | SQLite FTS5 |
| Rich Text | Custom JSON serialization |
| Build System | Meson |
| Packaging | Flatpak |

## License

BetterNotes is licensed under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.html) or later.

Copyright 2026 0xpaperhead
