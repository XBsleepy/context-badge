# Changelog

All notable changes to Context Badge are documented here.

## [Unreleased]

### Added

- Application label and window title now scale with the badge height while wrapping still follows the current width.
- Foreground dwell tracking with configurable noise/checkpoint intervals and dual-backup local storage.
- In-app Time analysis window with per-app totals and a scrollable day timeline.
- Colour-bar zoom and pan so a day report can be inspected by time window.
- Right-edge Edit / Hide / Close tabs; Hide minimizes the overlay to the taskbar.

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
