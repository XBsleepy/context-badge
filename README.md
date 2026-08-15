# Context Badge

A persistent, always-on-top badge that shows the active Windows application and
window title. The badge follows the active window to its monitor, never takes
keyboard focus, and lets mouse clicks pass through it.

## Step 1: run the prototype

Requirements: Windows 10/11 and Python 3.11+.

```powershell
.\run.ps1
```

Switch between browser, VS Code, terminal, and other windows. The badge should
update within 200 ms and remain visible. Stop it with `Ctrl+C` in the PowerShell
window that launched it.

## Move the badge

The badge is click-through during normal use, except for the pencil inside its
right edge. Click the pencil to open the edit menu, then choose `Move badge`.
Its border turns blue and `MOVE MODE` appears in the label. Drag anywhere on the
badge with the left mouse button, then click the check mark to lock it. The
position is saved when dragging finishes and again when move mode is closed, and
is restored immediately on future launches.

The edit menu is action-based so later versions can add operations such as
renaming a context, choosing a colour, or creating a matching rule.

Choose `× Exit Context Badge` in the edit menu to close the application
immediately.

## Current scope

- Observes every standard top-level Windows application.
- Distinguishes windows through their live title and process.
- Stays above full-screen/maximized windows that permit topmost overlays.
- Follows the active window across monitors.
- Does not yet classify titles into human-friendly work contexts.
- Does not yet observe tabs whose title is hidden from the native window title.

The next step is a local rules file that maps application/title patterns to a
stable context name such as `LeetCode` or `RSI Research`.
