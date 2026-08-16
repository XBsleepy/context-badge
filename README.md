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
- Click-through follows Fix: the overlay captures the cursor until it is locked.
- Supports persistent position and size.
- Scales label, title, and list type with the badge height.
- Records how long the foreground app, window, or page stays on top.
- Includes an in-app colour palette for badge background, list background, text, and border.
- Treats transparent as a background fill, same as the solid swatches.
- Can be minimized to the taskbar from the Hide tab.
- Keeps a per-tab todo list, shown from the List tab.
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

The executable is a single file. Stop the app with the Close tab.

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

Stop the app with the Close tab, or press `Ctrl+C` in the terminal that launched
it.

## Using the badge

Four tabs sit on the right edge: `Menu` opens the function menu, `List` shows
or hides the todo panel, `Hide` minimizes the badge to the taskbar, and
`Close` quits. The rest of the badge remains click-through during normal use.
Long-press `Menu` to drag the badge.

### Move

Drag anywhere on the badge body to move it. Long-press the `Menu` tab still
works as a second handle. A short click on `Menu` opens the menu. Choose
`Fix` to lock the overlay: the body becomes click-through, Menu / List /
Hide / Close are replaced by a single right-edge `Unlock` tab, and dragging
stops. Click `Unlock` to restore the four tabs and movement. Click-through
follows `Fix`, not the transparent-background swatch. The setting is
remembered as `position_locked`.

### Resize

Choose `Resize badge`, drag the badge body to change its width and height, and
click the check mark to save. The supported range is 280–1000 px wide and
64–260 px high. Extra width is wrapping room. Extra height grows type only
part-way so more of the window title can wrap onto additional lines. List
type and row height follow the same height scale.

### Colours

Open `Colours` to configure:

- Background, including a crossed-out transparent swatch at the same level as
  the solid colours
- List panel background, with the same palette and transparent swatch
- Text
- Border

Transparent is stored as the fill value `transparent`, not a separate flag.
Old `background_transparent` preferences are migrated on launch. Resize mode
temporarily uses the default solid fill so a transparent badge stays easy to
grab. List fill is independent of the badge fill. The cursor still hits the
overlay until `Fix` is on; transparent colour does not by itself pass clicks
through.

### Time analysis

Context Badge records how long the current top-level window stays in the
foreground. Browser titles drop Edge/Chrome chrome such as `和另外 N 个页面` and
the profile suffix. When UI Automation is available, the selected tab name and
address-bar URL are used instead of the raw window title. Editors such as
Cursor are grouped by workspace (`file · workspace` on the badge; the todo list
keys off the workspace). The Cursor Agents window uses the current chat title.

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

### Tab lists

`List` on the right strip shows or hides a todo panel under the badge. Hidden,
the panel takes no space. Shown, it lists todos for the current tab or page.

Browser lists are keyed by the page URL when it can be read, otherwise by the
cleaned tab title. Cursor/VS Code lists are keyed by workspace, so switching
files in the same repo keeps the same list. Cursor Agents lists follow the
current chat title. The badge still shows a short label (tab name, `file ·
workspace`, or chat title).

Rows can be checked off, edited, added, and deleted. Checked items stay in the
list. The header is an editable note for extra context; if it is empty, the
current window or page name is shown as a placeholder and is not stored. Empty
lists with no note are not written to disk. Show/hide is remembered in
preferences as `list_bar_expanded`.

Lists are a JSON file with a sibling `.bak` copy, using the same crash-safe
write path as the other local stores: `.context-badge-lists.json` beside the
source checkout, or `lists.json` under `%LOCALAPPDATA%\Context Badge` when
packaged.

### Hide

`Hide` minimizes Context Badge to the taskbar, like a normal window. Click the
taskbar entry to restore it. Dwell tracking keeps running while it is minimized.

### Close

The `Close` tab quits the app immediately.

## Preferences and privacy

When you run from source, preferences are stored in `.context-badge.json`
beside the repository. The packaged Windows executable stores the same settings
in `%LOCALAPPDATA%\Context Badge\preferences.json`. Dwell history uses
`.context-badge-dwell.jsonl` and `.context-badge-dwell-active.json` in the
source checkout, or `dwell.jsonl` and `dwell-active.json` under
`%LOCALAPPDATA%\Context Badge` when packaged. Per-tab lists use
`.context-badge-lists.json` or `lists.json` in those same locations. All of
these files are local only and contain UI preferences plus foreground app/page
titles, optional page URLs, durations, and optional todo text.

The current version reads the foreground window handle, executable name,
visible native window title, and (when available) UI Automation tab names,
address-bar URLs, and Cursor chat titles. It stores local dwell records and
per-tab todo lists derived from those values. It does not capture screenshots,
record keystrokes, or send data over the network.

## Current limitations

- Recognition is based on the process, native window title, and UI Automation
  tab/URL/chat hints when they are available.
- Semantic labels such as `LeetCode` and `RSI Research` are not implemented yet.
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
├── list_bar.py         optional per-tab todo panel
├── list_store.py       dual-backup todo persistence
├── paths.py            source vs packaged config locations
├── surface.py          page labels from titles and UI Automation
├── text_layout.py      measured wrapping and ellipsis
├── theme.py            palette and theme helpers
├── uia.py              selected tab, URL, and chat title
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
