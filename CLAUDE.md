# CLAUDE.md

Context for whoever (human or Claude) picks this project up next. This
whole project was built in a single Claude.ai chat session and then moved
into this repository — nothing here has been run on real Framework
hardware. Read the "Not yet verified" section before assuming anything
works.

## What this is

A Tkinter GUI for [framework_tool](https://github.com/FrameworkComputer/framework-system),
the official CLI for controlling Framework laptop/desktop firmware (fans,
battery charge limits, keyboard backlight, USB-C PD ports, etc). The GUI
shells out to the CLI and parses its text output — it has no direct hardware
access of any kind.

It has since grown past framework_tool, by explicit request, into three more
tabs that shell out to *other* programs: **Power (TDP)** (RyzenAdj, Linux
powercap, Windows powercfg), **Setup** (installing those helpers), and
**Drivers** (Framework's driver bundles and vendor drivers for swapped-in
parts). Same shape as the rest of the app — run a program, parse its output
best-effort — and the same rule: the app never touches hardware itself.

Two distribution targets only, by explicit request: a Windows exe/installer
and a Linux Flatpak. (An earlier Linux "script installer" was built and then
deliberately dropped — don't re-add it unless asked.) Releases are published
by GitHub Actions; see "Releasing" below.

Hard requirement carried through the whole project: **no background
processes.** No services, timers, tray icons, or autostart entries on either
OS. A subprocess is spawned only when the user clicks a button, and exits
when that command finishes.

## Quick orientation

```
framework_gui.py      Tk app — UI, command execution, the 14 "Tools" workflows
parsers.py             Pure-Python: regex parsers + detect_model(). No tkinter
                        import, so it's unit-testable without a display.
power.py               CPU power-limit (TDP) backends — ryzenadj / RAPL /
                        powercfg. Builds commands, does no I/O of its own.
deps.py                Helper-tool registry: detect, and build install plans.
drivers.py             Framework driver-page catalog, link scraping, download.
                        (all three follow parsers.py's rules: stdlib only, no
                        tkinter, I/O injected as arguments)
tests/test_parsers.py  Unit tests for parsers.py. Run anywhere, no display needed.
tests/test_power.py    Unit tests for power.py — unit conversions especially.
tests/test_deps.py     Unit tests for deps.py — every install plan path.
tests/test_drivers.py  Unit tests for drivers.py — board matching + scraping.
tests/test_smoke_gui.py Full-app tests: real App(), real mainloop(), stub CLI
                        binary on PATH, assert on which buttons survive gating.
                        Needs a display (xvfb-run on headless Linux); skips
                        itself on Windows (the stub binary is POSIX-only).
tests/test_packaging.py Asserts every app module is carried by every packaging
                        path, that every install path leaves an uninstaller and
                        a Start Menu entry, and that the release workflow
                        produces exactly the assets the README links. No
                        display, no build tooling needed.
windows/               build.bat (PyInstaller), installer.iss (Inno Setup),
                        install.ps1 / install-exe.ps1 (+ .cmd wrappers), uninstall
flatpak/               manifest, .desktop, launcher script, icon, its own README
.github/workflows/ci.yml       Linux tests (Xvfb), ruff lint, Windows build
.github/workflows/release.yml  Fires on release published: Windows exe +
                        installer, Flatpak bundle, uploaded to the release
.github/actions/build-windows  Composite action shared by both workflows so
                        the released artifact is the one CI exercised
LICENSE                MIT
README.md              User-facing install/usage instructions
```

Run the tests before changing `parsers.py` or the gating logic in
`framework_gui.py` — they're fast (< 1s) and they're what caught a real race
condition during development (see "Known gotchas" below).

```bash
python3 -m unittest discover tests -v          # parser tests only, if no display
xvfb-run -a python3 -m unittest discover tests -v   # everything, headless Linux
```

## Architecture notes

- **`parsers.py`** is deliberately dependency-free (stdlib `re` only). It
  holds every regex used to scrape `framework_tool`'s text output, plus
  `detect_model()`, which turns `--versions` output into a capability dict
  (`is_laptop`, `has_touchscreen`, `has_expansion_bay`, etc). Keep new
  parsing logic here, not inline in `framework_gui.py`, so it stays testable
  without tkinter.

- **The CLI has no stable output format.** The upstream repo says so
  explicitly ("the commandline does not guarantee a stable interface").
  Every parser here was written against samples in framework-system's
  `EXAMPLES.md` and is best-effort: every caller checks whether the parse
  succeeded and falls back to showing raw output rather than crashing or
  showing nothing. If you touch a regex, keep that fallback.

- **Device detection is fail-open by design.** `detect_model()` runs
  `--versions` once (on launch and on "Rescan device"), and any field it
  can't confidently determine defaults to `True` — meaning "show the
  control." A control that doesn't apply to your device is a minor
  annoyance; a control that's hidden when it should have been there is
  worse. Do not change this default direction.

- **Model → feature gating**, current state:
  | Model | Gets | Loses |
  |---|---|---|
  | Laptop 12 | stylus, touchscreen, tablet-mode override | — |
  | Laptop 13 | touchscreen *only if the versions output shows a Touchscreen section* (optional bezel) | stylus, tablet-mode |
  | Laptop 16 | expansion bay | stylus, touchscreen, tablet-mode |
  | Desktop | RGB LED control | battery/charge-limit/kblight/fp-led/tablet-mode/touchscreen/stylus/input-deck/expansion-bay/privacy-switches (no battery, no built-in keyboard/webcam) |

  Touchscreen/stylus are gated by **content detection** (does `--versions`
  actually show that section), not just the model number — a Laptop 13
  without the touchscreen bezel and one with it should get different UIs.
  Expansion bay and RGB are gated by **model number** only, per the CLI's
  own documented restrictions (`EXAMPLES.md` says expansion bay is
  "Laptop 16 only" and RGB is "Framework Desktop" only).

- **Command execution wrapping** (`_build_cmd` in `framework_gui.py`):
  `[binary] + args`, optionally prefixed with `pkexec` (Linux, unless
  already root) and/or `flatpak-spawn --host` (when running inside the
  Flatpak sandbox — the sandbox can't reach the EC at all, so this is a
  deliberate, unavoidable sandbox hole; see `flatpak/README.md`).

- **Two command paths, on purpose.** `_build_cmd`/`_exec` are
  framework_tool-only: they put the binary from the top bar in front of the
  args. Everything on the Power/Setup/Drivers tabs runs a *different*
  program, so it goes through `_build_external`/`_exec_external`, which
  applies the same pkexec and flatpak-spawn wrapping with no binary
  prefixed. Don't route helper tools through `run()` — you'd get
  `framework_tool ryzenadj --stapm-limit=…`.

- **Everything beyond framework_tool is "shell out to someone else".** The
  app has no direct hardware access anywhere, so the three newer tabs are
  the same shape as the old ones: build a command in a pure module, run it
  in a worker thread, parse best-effort, fall back to raw output.
  - `power.py` picks a backend from (CPU vendor, OS, what's installed) and
    builds the command. **Watch the units**: RyzenAdj takes milliwatts and
    RAPL takes microwatts; the UI is in watts and `check_watts()` is the
    single conversion gate. `powercfg` is deliberately in the table even
    though it caps *frequency* rather than wattage — it needs nothing
    installed, so it's the honest fallback, and `sets_watts: False` is what
    stops the UI from labelling it as watts.
  - `deps.py` never returns "nothing I can do". Every dependency yields an
    install plan; where no package exists (RyzenAdj outside the AUR) the
    plan degrades to `KIND_MANUAL` with upstream's page. Emitting an
    `apt-get install ryzenadj` that cannot work would be worse than saying
    so. Nothing installs without a confirm dialog showing the exact command.
  - `drivers.py` matches the board string from `--versions` against a
    catalog ordered **most specific first** ("Laptop 13 Pro" must precede
    the entry that matches any "Ryzen AI 300"). Unmatched boards fall back
    to the Knowledge Base index, never to nothing. Scraping a bundle link
    out of the page is best-effort; on any failure the GUI opens the page in
    a browser. Framework's URLs live only in `CATALOG`/`EXTRA`, so fixing a
    dead link is a one-line change.

- **Blocked commands** (`App.BLOCKED` in `framework_gui.py`):
  `--flash-ec`, `--flash-ro-ec`, `--flash-rw-ec`, `--flash-gpu-descriptor*`,
  `-f`/`--force`. These can brick the hardware; they're excluded from every
  button *and* from the free-form custom-args field. `--console follow` is
  also blocked in the custom-args field specifically because it never
  returns, which would hang a worker thread forever. Don't add UI for any
  of these without discussing it first — this was a deliberate, repeated
  decision across the project, not an oversight.

- **Threading model**: every command runs on a background `threading.Thread`
  so the UI never blocks; results come back via `self.after(0, ...)`. The
  14 "Tools" (fan sweep, thermal monitor, etc.) are multi-step sequences
  with a shared cancel flag (`self._cancel`) checked between steps, and a
  Cancel button in the top bar. State-changing tools (fan duty, kb
  backlight, fingerprint LED) always restore the previous/auto state in a
  `finally` block, including on cancel.

## Known gotchas (learned the hard way — don't reintroduce these)

1. **PyInstaller and flatpak-builder both fail on SMB/CIFS/network paths.**
   `windows/build.bat` copies sources to `%TEMP%` before running PyInstaller
   and copies the result back. `flatpak/README.md` tells the builder to copy
   the repo to local disk first — flatpak-builder needs OSTree hardlinks/
   xattrs that network filesystems don't support, and there's no code-level
   workaround for that one.

2. **PowerShell's execution policy blocks `.ps1` files launched directly
   from a network share.** Every `.ps1` in `windows/` has a matching `.cmd`
   wrapper (`install.cmd`, `install-exe.cmd`, `uninstall.cmd`) that runs it
   with `-ExecutionPolicy Bypass`. Point people at the `.cmd` files, not the
   `.ps1` files directly.

3. **`build.bat` only builds — it never installs anything.** This was a
   real gap during development: someone ran `build.bat`, got an exe in
   `windows/dist/`, and it never showed up in their Start Menu because
   nothing put it there. `install-exe.ps1`/`.cmd` is the separate step that
   copies the exe locally and creates the Start Menu shortcut. Keep these
   as two distinct steps (build once centrally, deploy per-device) — don't
   collapse them back into one script without preserving both use cases.

4. **Starting a background thread that touches a `tk.Variable` before
   `mainloop()` is actually running throws
   `RuntimeError: main thread is not in main loop`.** This bit the initial
   device-scan-on-launch: it originally called `self._rescan()` directly
   at the end of `__init__`, which raced Tk's startup. Fixed with
   `self.after(150, self._rescan)` so the scan is scheduled through Tk's
   own event loop instead of firing immediately. If you add more
   startup-time background work, schedule it the same way — don't call
   `threading.Thread(...).start()` directly from `__init__`.

5. **The app is two modules, and every packaging path has to carry both.**
   `framework_gui.py` imports `parsers.py`. The original single-file
   packaging (PyInstaller work dir, `install.ps1`, the Flatpak manifest)
   shipped only `framework_gui.py`, which produces an exe/Flatpak that
   dies with `ModuleNotFoundError: No module named 'parsers'` on launch —
   invisible until you run the *packaged* build, since running from a
   source checkout always works. `tests/test_packaging.py` now fails if a
   root-level module is missing from any packaging path; if you add a
   module, update `windows/build.bat`, `windows/install.ps1`, and
   `flatpak/io.github.frameworkgui.FrameworkGUI.yml` (both the
   `install -Dm644` command and the `sources:` list).

6. **Testing Tk apps needs a real `mainloop()`, not a polling loop.**
   Calling `app.update()` in a `while` loop from test code hits the same
   cross-thread RuntimeError as #4, because Tkinter only marshals
   background-thread Tk calls while the interpreter is genuinely inside
   `mainloop()`. `tests/test_smoke_gui.py` runs `app.mainloop()` for real
   and uses `app.after(...)` as its own polling/timeout mechanism, quitting
   the loop once results are captured. Follow that pattern for any new
   GUI test.

7. **Sequential Tk interpreters in one test process need explicit
   teardown.** Each GUI test builds a fresh `App()`. If the previous one is
   left to the garbage collector, its Tk variables' `__del__` (which calls
   into Tcl) can run at an arbitrary later moment — including from the
   *next* app's device-scan thread — which corrupts Tcl's async state and
   leaves the next scan permanently pending. Symptom: an intermittent test
   timeout in whichever GUI test happened to run later, plus
   `RuntimeError: main thread is not in main loop` and
   `Tcl_AsyncDelete: async handler deleted by the wrong thread` on stderr.
   `_drive_app()` therefore cancels its pending `after` timer, destroys the
   app, drops the reference, and calls `gc.collect()` while still on the
   main thread with no mainloop running. Keep that teardown. (This is
   test-harness-only: real users get one App per process.)

8. **Re-packing a widget moves it to the end of the pack order.**
   `_build_tabs()` destroys and rebuilds the notebook on every rescan. When
   it packed the new notebook straight into the window, the tabs landed
   *below* the output pane and the status bar the moment the first device
   scan finished — the app looked fine until detection returned, which is
   why it survived so long. The notebook now lives in a `tabs_holder` frame
   packed exactly once in `__init__`. Anything else rebuilt at runtime needs
   the same treatment.

9. **Screenshots of a Tk app under Xvfb lie if you only call
   `update_idletasks()`.** Half the widgets come out blank — the geometry is
   right, the paint hasn't happened. `update()` plus a short `after()` delay
   before grabbing gives a true picture. Worth knowing before "fixing" a
   layout bug that isn't there.

## Not yet verified (be skeptical, not confident)

- **Never run against real `framework_tool` or real hardware.** All
  testing uses a stub Python script standing in for the binary, with output
  samples copied from the upstream repo's `EXAMPLES.md`. If a real device's
  output differs even slightly from those samples (formatting change
  between CLI versions, locale differences, etc.), a parser could silently
  return nothing and fall back to raw text — which is the intended failure
  mode, but it means "the regex matched the docs" is not the same
  guarantee as "the regex matches your CLI version." If you have access to
  a real Framework device, that's the highest-value next step: run each
  Info/Tools button and diff actual output against the samples in
  `tests/test_parsers.py`.
- **`windows/build.bat` now runs for real in CI** (via the
  `.github/actions/build-windows` composite action, which invokes the script
  itself rather than a reimplementation, and CI uploads the resulting
  `FrameworkGUI.exe` + `FrameworkGUI-Setup.exe`) — so a green badge means
  both *build*. It does not mean anyone has *launched* them on a real
  Windows desktop: the `--uac-admin` self-elevation, the Start Menu
  shortcut/uninstaller scripts (`install.ps1` / `install-exe.ps1` /
  `uninstall.ps1`), the Apps & features registration and the whole
  Mark-of-the-Web/SMB story are still unexercised.
- **`windows/installer.iss` now compiles in CI** (same composite action
  installs Inno Setup if the runner image lacks it), so syntax errors show
  up on push. Nobody has *run* the resulting `FrameworkGUI-Setup.exe`: the
  install/uninstall round trip, the Start Menu group and the `AppId`-based
  upgrade path are unverified.
- **`flatpak/io.github.frameworkgui.FrameworkGUI.yml` is now built by
  `.github/workflows/release.yml`** (release-published and
  `workflow_dispatch`, not on every push — it compiles Tcl/Tk and CPython
  from source). It had never been built when that job was written, so the
  first run may well fail; rehearse it with `workflow_dispatch` before
  relying on a release. `tests/test_packaging.py` still only checks the
  manifest's *structure*, and the `flatpak-spawn --host` runtime behavior
  remains unexercised regardless of whether the build goes green.
- **The release workflow itself has never fired.** The
  `gh release upload` steps, the tag→version derivation and the
  `/releases/latest/download/...` links in the README all go live the first
  time a release is published. A `workflow_dispatch` run exercises
  everything except the upload.
- **No power-limit backend has ever run.** `power.py`'s command builders are
  unit-tested, but no `ryzenadj`, no RAPL write and no `powercfg` call has
  been executed against real silicon from this app. The RyzenAdj `-i` parser
  was written against upstream's README sample, exactly the same
  "matched the docs, not your version" caveat as the framework_tool parsers.
  Sanity-check on real hardware by applying a limit and reading it back —
  the Power tab does that read-back automatically after Apply.
- **No driver page has ever been scraped successfully.** `find_downloads()`
  is tested against synthetic markup. Framework's Knowledge Base returned
  403 to a scripted fetch during development, so the browser fallback may
  turn out to be the *normal* path rather than the exception. If it is,
  consider dropping the scrape and just opening the page.
- **The Framework Knowledge Base URLs in `drivers.py` were collected from
  search results, not by loading each page.** They are the right shape and
  the right articles, but a moved article shows up as a 404 in someone's
  browser. Worth one pass with a real browser to confirm all twelve.
- The Flatpak app icon (`io.github.frameworkgui.FrameworkGUI.svg`) is a
  crude placeholder, not real artwork.

## Deliberately out of scope

- **Persisting power limits across reboots.** The limits the Power tab sets
  are volatile — that is a property of the SoC registers, not a bug. Making
  them stick needs something to re-apply them at boot and after resume: a
  systemd unit, a scheduled task, a tray agent. All of those are background
  processes, which is the one requirement this project has never bent. The
  UI states the limitation instead. If this comes back, it is a decision to
  drop the no-background-processes rule, not a small feature.
- **Driving ThrottleStop.** It has no command line. The Setup tab can point
  at it and the Drivers tab can link it, but nothing here can script it. On
  Intel, `powercfg` (Windows) and RAPL (Linux) are what the app can actually
  drive.
- **Running downloaded installers.** The Drivers tab downloads a bundle and
  stops there. Executing a vendor installer unattended, as an elevated
  process, is not something this app should do on a user's behalf.

## Releasing

Publishing a GitHub Release (tag `vX.Y.Z`) triggers
`.github/workflows/release.yml`, which builds and attaches three assets:

| Asset | Built by |
|---|---|
| `FrameworkGUI-Setup.exe` | `windows/installer.iss` via Inno Setup |
| `FrameworkGUI.exe` | `windows/build.bat` via PyInstaller |
| `FrameworkGUI.flatpak` | `flatpak/…FrameworkGUI.yml` via flatpak-builder |

**Those three filenames are a contract**: README links
`/releases/latest/download/<name>` for each, and
`tests/test_packaging.py` fails if the workflow and the README disagree.
Rename an asset in one place and you must rename it in both.

The version comes from the tag with any leading `v` stripped, and is passed
to Inno as `/DAppVersion=`. Manual `workflow_dispatch` runs build everything
under version `0.0.0-dev` and skip only the upload — use that to rehearse,
especially the Flatpak job, which had never been run when it was written.

## Suggested next steps, roughly in priority order

1. Get access to a real Framework device (any model) and validate the
   parsers/detection against real `--versions`/`--power`/`--thermal`/
   `--pdports` output. This is the single highest-value thing to do next.
2. Rehearse `.github/workflows/release.yml` with `workflow_dispatch` and fix
   whatever the Flatpak job turns up — it is the one build step that had
   never executed anywhere before it was added.
3. Run `FrameworkGUI-Setup.exe` on a real Windows machine: install,
   Start Menu group, uninstall, reinstall over the top. CI proves it
   compiles, nothing yet proves it installs.
4. Same for the script installers (`install-exe.cmd`) from an SMB share,
   including the uninstaller they now drop in `%LOCALAPPDATA%\FrameworkGUI`.
5. Apply a power limit on a real AMD Framework with RyzenAdj installed and
   confirm the read-back matches — then do the same for RAPL on Intel Linux
   and `powercfg` on Windows.
6. Open all twelve Knowledge Base URLs in `drivers.py` in a browser, and see
   whether "Find downloads on that page" scrapes anything or always falls
   back to opening the browser.
7. Real app icon for the Flatpak `.desktop`/icon file.
