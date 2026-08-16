# Changelog

All notable changes to Context Badge are documented here.

## [Unreleased]

### Changed

- README leads with the AI-coding context-switch story, badge screenshots, and Time analysis as a crude local report (LLM summaries called out as future work). Install documents the v0.2.0 `.exe` and that no system Python is required.

## [0.2.0] - 2026-08-16

### Added

- Application label and window title grow only part-way with badge height so extra height can show more title lines; wrapping still follows the current width.
- Foreground dwell tracking with configurable noise/checkpoint intervals and dual-backup local storage.
- In-app Time analysis window with per-app totals and a scrollable day timeline.
- Colour-bar zoom and pan so a day report can be inspected by time window.
- Right-edge Menu / List / Hide / Close tabs; Hide minimizes the overlay to the taskbar.
- Long-press Menu to drag the badge; a short click still opens the menu.
- Drag the badge body to move it; Menu → Fix locks the position, makes the body click-through, and replaces the right tabs with Unlock.
- List tab shows or hides a per-tab todo panel under the badge, stored in dual-backup JSON.
- List header is an editable note; an empty note shows the current window/page name as a placeholder.
- Transparent is a Background fill value (`transparent`) at the same level as the solid swatches; old `background_transparent` flags are migrated.
- Colours includes a List background row with the same palette and transparent swatch.
- List type and row height follow the badge height scale.
- Cleaner page labels: strip Edge “and N other pages” chrome, read the selected tab/URL via UI Automation, and key Cursor todos by workspace or Agents chat title.

## [0.1.0] - 2026-08-16

### Added

- Persistent, always-on-top Windows context badge.
- Foreground application and native window-title detection.
- Click-through normal mode with an embedded Edit control.
- Move and resize modes with persistent layout settings.
- In-app palettes for background, text, and border colours.
- Transparent background support.
- Bounded wrapping and ellipsis for long titles.
- Extensible Edit menu with a direct Exit action.
- Windowed single-file Windows executable via PyInstaller.
- Packaged builds store preferences under `%LOCALAPPDATA%\Context Badge`.
