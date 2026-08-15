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
python -m py_compile app.py context_badge\*.py
```

## Pull requests

- Keep changes focused and explain the user-visible behaviour.
- Preserve click-through and no-focus behaviour outside edit modes.
- Test changes with multiple windows and, when relevant, multiple monitors.
- Do not commit `.context-badge.json`; it contains personal UI preferences.

The project is currently alpha software. Small, reviewable improvements are
preferred over large framework migrations.
