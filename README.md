# Context Badge

AI coding makes it cheap to open another workspace, another agent chat, another
browser tab. The expensive part is coming back. After a few hours of hopping
across Cursor windows, docs, and chats, the last page's intent is gone — and
that context-switch tax is a reliable way to burn out.

So I vibed this: a longer always-on-top badge that tracks the page you are
actually looking at. Pin a short description and a todo list to *this* page.
Next time you land here, the work is still on the glass. Less reloading of
context. Easier to stay focused.

![A floating Context Badge over Cursor, with a page note and a todo for the current task](docs/images/badge-page-todos.png)

The badge follows the foreground window. In a browser it keys off the tab and
URL when it can; in Cursor it keys off the workspace (or the current Agents
chat). The list belongs to that page, not to a global dump of every thought
you had today.

![The badge over AGENTS.md, with a workspace note and a checked-off list item](docs/images/badge-workspace-notes.png)

Because the overlay already knows which app and page you are on, it is a short
step to asking: *what did I actually do today, and how did the hours split?*
Context Badge records foreground stays and opens a day report — app totals, a
colour ribbon, a timeline of switches.

The analysis is still crude. It will show you that an afternoon was 200
switches across ten apps; it will not yet write a narrative of the work. A
later pass can hang an LLM on this log for daily summaries. For now the point
is visibility: time allocation you can see, not a vibe you reconstruct at
midnight.

![Time analysis for a full day: hours tracked, app share, switch count, and a fragmented day ribbon](docs/images/time-day.png)

![A closer session: most of the time in Cursor, with a timeline of files, chats, and other apps](docs/images/time-session.png)

## Install

Windows 10 or 11. Nothing else.

### Executable (recommended)

Download [`ContextBadge.exe`](https://github.com/XBsleepy/context-badge/releases)
from the [latest GitHub Release](https://github.com/XBsleepy/context-badge/releases/tag/v0.2.0)
and double-click it.

You do **not** need a system Python, Anaconda, pip, or any other runtime. The
release is a single-file PyInstaller build: it already embeds Python and
Tkinter. It talks to APIs that ship with Windows (`user32`, UI Automation).
There is no installer and no extra Visual C++ package to hunt down.

Windows SmartScreen may warn on the first launch because the binary is not
code-signed. Choose *More info* → *Run anyway* if you trust the release.

Stop the app with the `Close` tab. Preferences, dwell history, and lists live
under `%LOCALAPPDATA%\Context Badge` so they survive the temp folder PyInstaller
uses at runtime.

### From source

Python 3.11+ is required only if you run the checkout, not the `.exe`:

```powershell
git clone https://github.com/XBsleepy/context-badge.git
cd context-badge
.\run.ps1
```

Or:

```powershell
python -m context_badge
```

Stop with the `Close` tab, or `Ctrl+C` in the terminal that launched it.

## Using the badge

Four tabs sit on the right edge: `Menu`, `List`, `Hide`, `Close`. Drag the
badge body to move it. Long-press `Menu` is a second handle; a short click
opens the function menu.

### Fix

`Menu` → `Fix` locks the overlay. The body becomes click-through, dragging
stops, and the four tabs collapse to a single `Unlock` on the right edge.
Click `Unlock` to restore them. Click-through follows `Fix` only — a
transparent background does not by itself pass clicks through. The lock is
remembered as `position_locked`.

### Resize

`Resize badge`, then drag the body. Range: 280–1000 px wide, 64–260 px high.
Extra width is wrapping room. Extra height grows type only part-way so more of
the window title can wrap onto additional lines. List type and row height
follow the same scale.

### Colours

`Colours` configures:

- Badge background (including a crossed-out **transparent** swatch)
- List panel background (same palette, independent of the badge)
- Text
- Border

Transparent is a fill value (`transparent`), not a separate flag. Old
`background_transparent` preferences are migrated on launch.

### List

`List` shows or hides a todo panel under the badge. Hidden, it takes no space.

- Browsers: keyed by page URL when it can be read, otherwise the cleaned tab title
- Cursor / VS Code: keyed by workspace, so file hops in the same repo keep one list
- Cursor Agents: keyed by the current chat title

Rows can be checked, edited, added, and deleted. Checked items stay. The
header is an editable note; if it is empty, the current window or page name is
only a placeholder and is not stored. Empty lists with no note are not written
to disk.

### Time analysis

Foreground stays shorter than `dwell_noise_seconds` (default 8) are treated as
noise. Once a stay crosses that threshold it is checkpointed, then refreshed
every `dwell_checkpoint_seconds` (default 60) so a crash still has a recent
value.

`Time analysis` opens a separate day report:

- App totals for the selected date, ranked by dwell time
- A compact 24-hour ribbon (consecutive same-app stays merged)
- A scrollable timeline of each recorded switch

`‹` / `›` change date; `Today` jumps back. Scroll the colour bar to zoom, drag
to pan, double-click to reset. This is an early, local report — not an AI
summary.

### Hide and Close

`Hide` minimizes the badge to the taskbar. Dwell tracking keeps running.
`Close` quits.

## Privacy

When you run from source, files sit beside the checkout
(`.context-badge.json`, `.context-badge-dwell.jsonl`,
`.context-badge-lists.json`, plus `.bak` copies). The packaged `.exe` uses the
same data under `%LOCALAPPDATA%\Context Badge`.

The app reads the foreground window handle, executable name, visible title,
and (when available) UI Automation tab names, address-bar URLs, and Cursor
chat titles. It stores local dwell records and per-tab todos derived from
those values. It does **not** capture screenshots, record keystrokes, or send
data over the network.

## Limitations

- Recognition is process + native title + UI Automation hints when they exist.
- Semantic labels such as `LeetCode` or `RSI Research` are not implemented yet.
- Full-screen apps may render above third-party overlays.
- The day report is one date at a time; there is no LLM summary yet.

## Development

Stdlib only: Tkinter, ctypes/Win32, local JSON/JSONL. No runtime packages.

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

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app.py context_badge
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md). The
turn-level log is [docs/dev-log.md](docs/dev-log.md).

## Packaging

```powershell
.\build.ps1
```

Produces `dist\ContextBadge.exe`. PyInstaller is a **build-time** dependency
only. End users of the `.exe` still do not install Python.

## Roadmap

- User-defined rules mapping apps and title patterns to stable contexts
- LLM daily / weekly work summaries on top of the local dwell log
- Browser and VS Code extensions for URLs, workspaces, and active files
- A richer in-app colour picker
- System tray and launch-at-login

## License

Context Badge is available under the [MIT License](LICENSE).
