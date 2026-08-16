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
- Scales label and title type with the badge height.
- Records how long the foreground app, window, or page stays on top.
- Includes an in-app colour palette for background, text, and border.
- Supports a transparent background while keeping the edit control available.
- Stores preferences locally and has no runtime dependencies.

## Requirements

- Windows 10 or Windows 11
- Python 3.11 or newer when running from source

Context Badge currently uses Win32 APIs directly and does not support macOS or
Linux. The packaged `.exe` embeds Python, so end users do not need a separate
interpreter.

## Quick start

### Windows executable

Download [`ContextBadge.exe`](https://github.com/XBsleepy/context-badge/releases)
from the latest release, then double-click it. No Python install is required.

The executable is a single file. Stop the app from its Edit menu.

### From source

Clone the repository and run:

```powershell
git clone https://github.com/XBsleepy/context-badge.git
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
64–260 px high. The application label and window title scale with the badge
height; extra width is used for wrapping rather than larger type.

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

### Time analysis

Context Badge records how long the current top-level window stays in the
foreground. Browser and editor titles are stored as pages when the application
name can be stripped from the native title.

Stays shorter than `dwell_noise_seconds` (default 8) are treated as noise and
are not written. Once a stay crosses that threshold, the in-progress duration
is checkpointed, then refreshed every `dwell_checkpoint_seconds` (default 60)
so an unexpected shutdown still has a recent value to recover.

Both knobs live in the ordinary preferences JSON and are created with defaults
on first launch if they are missing:

```json
{
  "dwell_noise_seconds": 8,
  "dwell_checkpoint_seconds": 60
}
```

History is an append-only JSONL file with a sibling `.bak` copy. The open
session is a small JSON file with its own `.bak`. If a write is interrupted,
the reader skips a truncated last line and falls back to the last good backup.

Choose `Time analysis` to open a separate day report. It shows:

- App totals for the selected date, ranked by dwell time
- A compact 24-hour ribbon, with consecutive same-app stays merged
- A scrollable action timeline of each recorded switch

Use `‹` / `›` to change date, or `Today` to jump back. Scroll the colour bar to
zoom into a stretch of the day (for example 06:00–09:00), drag to pan, and
double-click to return to the full day. Apps and the action list follow the
visible window. The timeline list stays scrollable for busy days.

### Exit

Choose `Exit Context Badge` to close the app immediately.

## Preferences and privacy

When you run from source, preferences are stored in `.context-badge.json`
beside the repository. The packaged Windows executable stores the same settings
in `%LOCALAPPDATA%\Context Badge\preferences.json`. Dwell history uses
`.context-badge-dwell.jsonl` and `.context-badge-dwell-active.json` in the
source checkout, or `dwell.jsonl` and `dwell-active.json` under
`%LOCALAPPDATA%\Context Badge` when packaged. All of these files are local only
and contain UI preferences plus foreground app/page titles and durations.

The current version reads the foreground window handle, executable name, and
visible native window title, and it stores local dwell records derived from
those values. It does not capture screenshots, record keystrokes, or send data
over the network.

## Current limitations

- Recognition is based on the process and native window title; semantic labels
  such as `LeetCode` and `RSI Research` are not implemented yet.
- A browser or editor tab can only be observed when its title is exposed through
  the top-level window title.
- Browser URLs and VS Code workspace metadata will require optional extensions
  or accessibility integrations.
- Full-screen applications may choose to render above third-party overlays.
- Dwell records are stored locally; the first in-app report covers one day at a time.

## Development

The codebase uses only the Python standard library:

```text
context_badge/
├── app.py              UI state and interactions
├── analysis_window.py  day report window
├── dwell.py            foreground stay tracking
├── dwell_report.py     app totals and day slices
├── dwell_store.py      dual-backup JSON/JSONL persistence
├── layout.py           size-dependent type and spacing
├── paths.py            source vs packaged config locations
├── surface.py          page labels from window titles
├── text_layout.py      measured wrapping and ellipsis
├── theme.py            palette and theme helpers
└── win32.py            Windows API boundary
```

Run checks with:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app.py context_badge
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) for
contribution and agent guidelines. The turn-level development log is
[docs/dev-log.md](docs/dev-log.md).

## Packaging

Build a windowed, single-file Windows executable with:

```powershell
.\build.ps1
```

The result is `dist\ContextBadge.exe`. Double-click it to start Context Badge
without a console window. PyInstaller is a build-time dependency only; the
runtime still uses the Python standard library.

## Roadmap

- User-defined rules mapping applications and title patterns to stable contexts
- Browser extension support for URLs and in-window tab changes
- VS Code extension support for workspaces and active files
- A richer in-app colour picker
- System tray integration and launch-at-login support

## License

Context Badge is available under the [MIT License](LICENSE).
