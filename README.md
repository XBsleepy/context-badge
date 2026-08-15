# Context Badge

Context Badge is a small, persistent Windows overlay that shows which desktop
window you are currently using. It stays above normal windows without taking
keyboard focus and keeps the rest of the badge click-through.

The project is an early foundation for a richer context reminder: browser tabs,
VS Code workspaces, research sessions, LeetCode windows, writing projects, and
other user-defined contexts.

## Features

- Observes the active top-level window across standard Windows applications.
- Displays the application/context label separately from the window title.
- Wraps and ellipsizes long titles without overlapping the label.
- Remains always on top and follows the active monitor until manually placed.
- Preserves click-through behaviour outside edit modes.
- Supports persistent position and size.
- Includes an in-app colour palette for background, text, and border.
- Supports a transparent background while keeping the edit control available.
- Stores preferences locally and has no runtime dependencies.

## Requirements

- Windows 10 or Windows 11
- Python 3.11 or newer

Context Badge currently uses Win32 APIs directly and does not support macOS or
Linux.

## Quick start

Clone the repository and run:

```powershell
git clone <repository-url>
cd context-badge
.\run.ps1
```

Alternatively:

```powershell
python -m context_badge
```

Stop the app from its Edit menu, or press `Ctrl+C` in the terminal that launched
it.

## Using the badge

The pencil on the right edge opens the Edit menu. The rest of the badge remains
click-through during normal use.

### Move

Choose `Move badge`, drag the badge body, and click the check mark to lock the
new position.

### Resize

Choose `Resize badge`, drag the badge body to change its width and height, and
click the check mark to save. The supported range is 280–1000 px wide and
64–260 px high.

### Colours

Open `Colours` to configure:

- Background
- Text
- Border
- Transparent background, represented by the crossed-out first background
  swatch

The palette is rendered inside the app; no system colour dialog is opened. A
transparent badge temporarily restores its selected background in Move and
Resize modes so it remains easy to manipulate.

### Exit

Choose `Exit Context Badge` to close the app immediately.

## Preferences and privacy

Preferences are stored in `.context-badge.json` beside the repository and are
excluded from Git. The file contains only UI preferences such as position,
dimensions, and colours.

The current version reads the foreground window handle, executable name, and
visible native window title. It does not capture screenshots, record keystrokes,
or send data over the network.

## Current limitations

- Recognition is based on the process and native window title; semantic labels
  such as `LeetCode` and `RSI Research` are not implemented yet.
- A browser or editor tab can only be observed when its title is exposed through
  the top-level window title.
- Browser URLs and VS Code workspace metadata will require optional extensions
  or accessibility integrations.
- Full-screen applications may choose to render above third-party overlays.

## Development

The codebase uses only the Python standard library:

```text
context_badge/
├── app.py          UI state and interactions
├── text_layout.py  measured wrapping and ellipsis
├── theme.py        palette and theme helpers
└── win32.py        Windows API boundary
```

Run checks with:

```powershell
python -m unittest discover -s tests -v
python -m py_compile app.py context_badge\*.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## Roadmap

- User-defined rules mapping applications and title patterns to stable contexts
- Browser extension support for URLs and in-window tab changes
- VS Code extension support for workspaces and active files
- A richer in-app colour picker
- System tray integration and launch-at-login support
- Packaged Windows releases that do not require Python

## License

Context Badge is available under the [MIT License](LICENSE).
