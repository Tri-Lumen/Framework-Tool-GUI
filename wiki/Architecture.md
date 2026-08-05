# Architecture

For anyone changing the code. `CLAUDE.md` in the repository is the long
version and the authority; this is the shape of it.

## The one rule everything follows

**The app never touches hardware.** It builds a command, runs it in a worker
thread, parses the output best-effort, and falls back to raw text when the
parse fails. That is true of `framework_tool`, of RyzenAdj, of the package
managers, of everything.

## Module layout

| Module | Responsibility |
| --- | --- |
| `framework_gui.py` | Layout, command execution, the diagnostics |
| `widgets.py` | Reusable UI pieces |
| `theme.py` | Every colour, size and spacing step, plus the Qt style sheet rendered from them |
| `navigation.py` | Rail groups and the declarative content of every gated pane |
| `parsers.py` | Every regex, plus `detect_model()` |
| `power.py` | CPU power-limit backends |
| `deps.py` | Helper-tool registry and install plans |
| `drivers.py` | Framework's per-build download pages |
| `device_images.py` | Board → photograph, and chassis geometry |
| `module_icons.py` | Expansion-card marks and the classifier |
| `app_icon.py` | Where each packaging path finds the app icon |
| `appstate.py` | The two persisted UI choices |
| `backdrop.py` | Compositing probe and the Windows 11 backdrop call |

**Only `framework_gui.py` and `widgets.py` import PySide6.** A test fails if
that changes. That line is what keeps the gating rules, the token table and
every parser testable in milliseconds on a machine with no Qt platform
plugin.

## Rules that are not obvious

**Navigation is data.** Rows name a *key*; the UI maps the key to a method.
A list holding bound methods could only be tested by constructing the app,
which needs a display.

**One token table, no colour literals.** A typo in a token name raises
`KeyError` at render time instead of silently producing an unstyled widget.

**Icon paths spell every command out.** SVG's implicit-lineto and
repeated-arc shorthands are legal but are not reliably parsed by the Qt in
the packaged build — it drops the rest of the path. A test counts the
arguments after each command letter.

**Two command paths.** `_build_cmd`/`_exec` are framework_tool-only and put
the configured binary in front of the arguments.
`_build_external`/`_exec_external` are for every other program and prefix
nothing. Routing a helper through the first gives you
`framework_tool ryzenadj --stapm-limit=…`.

**Threading.** Every command runs on a background thread and results come
back by emitting a Qt signal. A worker thread must never touch a widget —
the signals are the entire interface between them.

**Check `_busy` before touching any UI.** A handler that marks a row running
and starts a spinner *before* `run_tool` refuses leaves all of it stranded,
because nothing then emits the completion signal.

**Progress has two shapes.** A tool whose length is known before it starts
gets one animated bar driven by the clock. A sequence whose steps each take
an unknowable time gets the cell grid, where "4 of 6" is the honest answer.

## Testing

```bash
python3 -m unittest discover tests -v                            # logic only
QT_QPA_PLATFORM=offscreen python3 -m unittest discover tests -v  # everything
xvfb-run -a python3 -m unittest discover tests -v                # or this
```

Qt's wheels bring Qt but not the X/EGL libraries it links against. On a bare
Linux box the GUI tests **silently skip** until those are installed —
green-but-testing-nothing is the failure mode to watch for.
