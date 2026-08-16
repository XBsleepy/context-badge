# Contributing

Thanks for helping improve Context Badge.

## Local setup

Context Badge targets Windows 10/11 and Python 3.11 or newer. It has no runtime
dependencies.

```powershell
git clone <your-fork-url>
cd context-badge
python -m context_badge
```

Run the test suite before submitting a pull request:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app.py context_badge
```

Build a packaged Windows executable with:

```powershell
.\build.ps1
```

Do not commit `dist/` or `build/`; they are generated artifacts.

## Pull requests

- Keep changes focused and explain the user-visible behaviour.
- Preserve click-through and no-focus behaviour outside edit modes.
- Test changes with multiple windows and, when relevant, multiple monitors.
- Do not commit `.context-badge.json`, `.context-badge-dwell*`, or
  `.context-badge-lists*`; they contain personal UI preferences, local dwell
  history, and per-tab todo lists.
- Follow [AGENTS.md](AGENTS.md): keep `docs/dev-log.md` current and do not add
  runtime dependencies.

The project is currently alpha software. Small, reviewable improvements are
preferred over large framework migrations.
