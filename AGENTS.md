# Agent notes

These rules apply to every conversation in this repository.

## Development log

Keep `docs/dev-log.md` current across chats. After each user-visible turn,
append one new section to that file before finishing:

- Continue the existing turn numbering (`Turn N · YYYY-MM-DD HH:MM`).
- Record the user message verbatim.
- Record only the assistant's dialog reply: what changed and how to use it.
- Do not store code, diffs, tool traces, hidden context, or internal planning.
- One file is enough. Do not split the log by date or feature.

If the file is missing, recreate it with the same turn-level Markdown format.

## Dependencies

Stay on the Python standard library. Do not add runtime packages, UI
frameworks, databases, or plotting libraries.

Tkinter, ctypes/Win32, and local JSON/JSONL files are the UI and persistence
stack. New work should fit that constraint, including crash-safe dual-backup
writes already used for dwell history.
