# CLAUDE.md

Context for whoever (human or Claude) picks this project up next. This
whole project was built in a single Claude.ai chat session and then moved
into this repository — nothing here has been run on real Framework
hardware. Read the "Not yet verified" section before assuming anything
works.

## What this is

A PySide6/Qt GUI for [framework_tool](https://github.com/FrameworkComputer/framework-system),
the official CLI for controlling Framework laptop/desktop firmware (fans,
battery charge limits, keyboard backlight, USB-C PD ports, etc). The GUI
shells out to the CLI and parses its text output — it has no direct hardware
access of any kind.

It has since grown past framework_tool, by explicit request, into three more
sections: **CPU limits** (RyzenAdj, Linux powercap, Windows powercfg),
**Setup** (installing those helpers), and **Drivers** (links to Framework's
downloads list per device build, plus vendor drivers for swapped-in parts).
Same shape as the rest of the app — run a program, parse its output
best-effort — and the same rule: the app never touches hardware itself.

**It was a Tkinter app until the desktop redesign.** A design handoff
(`Framework GUI - Desktop.dc.html`, direction 1b) replaced the top bar +
nine-tab notebook + output pane with a rail/pane/content/drawer window, and
the toolkit went with it. The handoff named two routes and put Qt first:
Tkinter cannot composite acrylic, has no real translucency, and its widget
styling does not reach these screens. Everything below the UI —
`parsers.py`, `power.py`, `deps.py`, `drivers.py` — carried over unchanged,
as did all the command plumbing and the `BLOCKED` flag set.

Two distribution targets only, by explicit request: a Windows exe/installer
and a Linux Flatpak. (An earlier Linux "script installer" was built and then
deliberately dropped — don't re-add it unless asked.) Releases are published
by GitHub Actions; see "Releasing" below.

Hard requirement carried through the whole project: **no background
processes.** No services, timers, tray icons, or autostart entries on either
OS. A subprocess is spawned only when the user clicks a button, and exits
when that command finishes.

## Quick orientation

The app is the `frameworkgui` package; `framework_gui.py` at the repository
root is a five-line launcher that imports it, and is what every packaging
path points at. Paths below are inside the package unless stated.

```
framework_gui.py      The launcher. One import, one call to main().
frameworkgui/
  app.py               Qt app — layout, command execution, the 12 diagnostics.
                        One of only two modules that import PySide6.
  widgets.py           Reusable UI pieces: Panel, Card, Bar, TimedBar, Badge,
                        RailButton, PaneItem, Segmented, Grabber,
                        ChassisDiagram, ModuleIcon, MetricPanel, SensorRow,
                        ImageSlot, Spinner. No colour literals — tokens by
                        name only.
  theme.py             Design tokens + the Qt style sheet rendered from them.
                        No toolkit import: the sheet is a string.
  navigation.py        Rail groups, pane items, and the declarative content of
                        every gated pane (12 tools, 9 port queries, 9 settings
                        rows, 2 charge presets). Keys, not bound methods, so
                        it stays testable.
  appstate.py          The two persisted UI choices (appearance, drawer height).
  backdrop.py          Compositing probe + the Windows 11 backdrop call.
  device_images.py     Board string → product photograph, and the chassis
                        dimensions/bay count the Overview drawing is scaled
                        from. Filenames and numbers only.
  iconpaths.py         The icon path language, parsed by us: path string →
                        move/line/cubic/close, arcs converted here. Qt's SVG
                        renderer does not do this reliably in the packaged
                        Windows build. Stdlib only.
  module_icons.py      Expansion-card icon paths + the module classifier.
  app_icon.py          The app icon's filenames and where each packaging path
                        finds them. Stdlib only, like device_images.
  parsers.py           Pure-Python: regex parsers + detect_model(). No toolkit
                        import, so it's unit-testable without a display.
  power.py             CPU power-limit (TDP) backends — ryzenadj / RAPL /
                        powercfg. Builds commands, does no I/O of its own.
  deps.py              Helper-tool registry: detect, and build install plans.
  drivers.py           Framework download-page catalog. Links only, no I/O.
                        (everything except app.py and widgets.py follows
                        parsers.py's rules: stdlib only, no toolkit import,
                        I/O injected as arguments)
  assets/devices/      One product photograph per chassis, for the Overview.
  assets/icons/        The Framework mark: a multi-resolution .ico for Windows
                        and PNGs for the window icon and the Flatpak theme.
tests/test_parsers.py  Unit tests for parsers.py. Run anywhere, no display needed.
tests/test_power.py    Unit tests for power.py — unit conversions especially.
tests/test_deps.py     Unit tests for deps.py — every install plan path.
tests/test_drivers.py  Unit tests for drivers.py — board matching + catalog.
tests/test_commands.py Every flag the app can issue, checked against
                        framework_tool's published interface, plus the fixed
                        value sets for the enum-valued ones. A typo in an
                        argument is a button that fails and looks like a
                        hardware fault; nothing else catches it.
tests/test_theme.py    Token table + style sheet: both appearances complete,
                        no unrendered placeholder, every colour paintable.
tests/test_navigation.py  The gating table, without a display — the same
                        assertions the smoke tests make, in milliseconds.
tests/test_appstate.py Persisted settings, with injected I/O. A corrupt file
                        must never stop the app launching.
tests/test_backdrop.py The compositing decision table for every platform.
tests/test_device_images.py  Board → photograph, plus that every image the
                        catalog names is actually shipped and small enough.
tests/test_module_icons.py   Icon paths are well-formed and inside their
                        viewBox; the classifier declines to guess.
tests/test_iconpaths.py Every command in the path language, the arc geometry,
                        and every icon the app ships — parsed, measured and
                        bounds-checked without a display.
tests/test_smoke_gui.py Full-app tests: real App(), real event loop, stub CLI
                        binary on PATH, assert on which controls survive
                        gating. Needs PySide6 and a platform plugin
                        (QT_QPA_PLATFORM=offscreen, or xvfb-run); skips
                        itself on Windows (the stub binary is POSIX-only).
tests/test_packaging.py Asserts every app module and every device image is
                        carried by every packaging path, that only the UI
                        layer imports PySide6, that every install path leaves
                        an uninstaller and a Start Menu entry, and that the
                        release workflow produces exactly the assets the
                        README links. No display, no build tooling needed.
wiki/                  The published wiki pages, and the screenshots they
                        use. Reviewed alongside the code they describe.
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
`frameworkgui/app.py` — they're fast (< 1s) and they're what caught a real race
condition during development (see "Known gotchas" below).

```bash
pip install -r requirements.txt                     # PySide6-Essentials
python3 -m unittest discover tests -v               # logic tests, if no Qt
xvfb-run -a python3 -m unittest discover tests -v   # everything, headless Linux
QT_QPA_PLATFORM=offscreen python3 -m unittest discover tests -v   # or this
```

Qt's wheels bring Qt but not the X/EGL libraries it links against. On a bare
Linux box the smoke tests will silently skip until `libegl1 libgl1
libxkbcommon-x11-0 libxcb-cursor0` (and the rest of the list in
`.github/workflows/ci.yml`) are installed — green-but-testing-nothing is the
failure mode to watch for.

## Architecture notes

- **`parsers.py`** is deliberately dependency-free (stdlib `re` only). It
  holds every regex used to scrape `framework_tool`'s text output, plus
  `detect_model()`, which turns `--versions` output into a capability dict
  (`is_laptop`, `has_touchscreen`, `has_expansion_bay`, etc). Keep new
  parsing logic here, not inline in `app.py`, so it stays testable
  without a toolkit.

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

- **The UI layer is exactly two modules.** `app.py` and
  `widgets.py` import PySide6; nothing else does, and
  `tests/test_packaging.py` fails if that changes. That line is what keeps
  the gating rules, the token table and every parser testable in
  milliseconds on a machine with no Qt platform plugin.

- **One token table, no colour literals.** `theme.py` holds every colour,
  size, spacing step and chrome metric, and renders the Qt style sheet from
  a template against them. Qt style sheets have no variables of their own,
  so a typo in a token name raises `KeyError` at render time instead of
  silently producing an unstyled widget. Widgets that Qt cannot style (the
  bars, the rail's selection marker, the chassis drawing) paint themselves
  and ask `widgets.colour()` / `widgets.qcolour()` for the same tokens;
  `widgets.set_appearance()` is how those know which of the two surface sets
  is in force. Do not put a colour anywhere else.

- **Navigation is data.** `navigation.py` holds the five rail groups, the
  nine sections, and the declarative content of every gated pane: the 14
  diagnostics, the 9 port queries, the 9 settings rows. Rows name a *key*;
  `app.py` maps the key to a method or a widget. A list holding
  bound methods could only be tested by constructing the app, which needs a
  display — this way `tests/test_navigation.py` makes the same gating
  assertions the smoke tests make, without one.

- **Acrylic is probed, never assumed.** `backdrop.py` answers "can this
  session composite a translucent window": Windows 11 build 22621 or later
  via `DWMWA_SYSTEMBACKDROP_TYPE`, Wayland always, X11 only when something
  owns the `_NET_WM_CM_S0` selection, everything else no. An uncertain
  answer is always no, because a translucent surface with nothing composited
  behind it is worse than an opaque one. When the answer is no the app
  forces the opaque appearance, disables the Acrylic segment and shows the
  fallback strip. There is no portable blur on Linux, so acrylic there means
  translucency without one; on Windows 11 it is the real system backdrop.
  (The handoff's table numbers the `DWM_SYSTEMBACKDROP_TYPE` values one
  higher than the Windows SDK does; `backdrop.py` follows the SDK.)

- **The Windows backdrop takes four things, not one.** Setting
  `DWMWA_SYSTEMBACKDROP_TYPE` on its own returns success and changes
  nothing on screen — which is exactly what a real Windows 11 machine
  showed. All four are needed:
  1. `DwmExtendFrameIntoClientArea` with `-1` margins, or the backdrop is
     drawn behind the frame only and the client area stays as opaque as it
     was;
  2. `WA_TranslucentBackground` **and** `WA_NoSystemBackground` on the
     window, or Qt fills the client area with the palette's window brush
     before anything else paints;
  3. the call made *after* the window is shown — toggling
     `WA_TranslucentBackground` makes Qt destroy and recreate the native
     window, and the recreated one is a fresh HWND with none of these
     attributes. `App.showEvent` re-applies on every show, deferred a turn;
  4. Settings › Personalisation › Colours › "Transparency effects" on. With
     it off DWM accepts the call and draws a flat surface, so
     `backdrop.translucency_state` reads the registry value and answers
     "no" rather than letting the status bar claim an acrylic that is not
     on screen.
  `apply_windows_backdrop` returns whether the backdrop type was accepted
  and the app believes it: a refusal forces opaque and shows the strip.

- **The drawer is the output pane, one tab per program.** Every command is
  echoed as a `$ …` line into a log named for the program that ran it —
  `framework_tool`, `ryzenadj`, `apt-get` — with its output after it. Lines
  are inserted with a character format rather than as HTML so the CLI's text
  is never reformatted, which the design is explicit about. Height is
  dragged with the grabber, clamped to 70–460px, and persisted.

- **Overview readings cost three more elevated commands.** `--versions` is
  the launch scan, as it always was. The six stat cards and the bay panel
  also need `--power -vv`, `--thermal` and `--pdports` (plus
  `--charge-limit`, and `--expansion-bay` on a Laptop 16). Running those
  automatically behind `pkexec` would mean several extra password prompts on
  every launch, so they run on their own only when already root and
  otherwise wait for "Rescan device". Do not make them unconditional.

- **Device photographs are per chassis, not per mainboard.** Swapping the
  mainboard does not change what the machine looks like, which collapses the
  handoff's list of eleven images to five plus a fallback. Two things do
  change the outside and get their own image: the Laptop 13 Pro's black lid,
  and a Laptop 16 with a Graphics Module fitted (detected from
  `--expansion-bay`). `device_images.py` is the mapping and does no I/O
  beyond `path_for()`; a build shipped without the images falls back to the
  text slot in `widgets.ImageSlot` rather than showing a blank rectangle.

- **The icons are parsed by us, not by Qt.** Writing every path command out
  longhand was the first attempt at this and it was not enough: the rail
  icons still came out as fragments on a real Windows machine. Qt's SVG
  renderer is the variable, and it cannot be tested from here — the same
  strings render perfectly under the Qt in CI, so the failure only exists in
  the shipped build. `iconpaths.py` turns a path string into
  move/line/cubic/close operations (arcs converted with the spec's endpoint
  parameterization), `widgets.icon_path` walks those into a `QPainterPath`,
  and `stroke_pixmap` strokes it with a `QPen`. No QtSvg import anywhere in
  the app now. `tests/test_iconpaths.py` parses and measures every icon the
  app ships, which is the check that was impossible while Qt owned the
  parsing. The paths still spell their commands out and
  `tests/test_navigation.TestIconPaths` still checks that — a readability
  rule now rather than a workaround, since the parser handles the shorthands
  correctly.

- **Ports are read through two commands, not one.** `--pdports` uses a
  Framework-specific EC command (`0x3E23`) that not every EC firmware
  implements. Where it is missing the CLI *still exits 0*, having printed
  only errors — so the app saw a successful command, parsed zero ports, and
  left every bay reading "not read" with no clue why. `--pdports-chromebook`
  asks the same question through the generic Chromium EC path and answers
  on boards the first does not. It prints a different format
  (`USB-C Port 0 (Right Back):`, `Role:`, `Voltage Now`/`Current Lim`
  instead of `Negotiated:`), so `parse_ports` reads both and
  `readings["ports_source"]` records which one answered. Keep the fallback:
  it is the difference between the bay panel working and not.

- **The role says whether a port is in use; the wattage does not.** A real
  Laptop 13 reported `Role: Sink` on the port it was charging through with
  `Current Lim: 0 mA` beside it, so a wattage derived from voltage × current
  came out as nothing and the machine showed four idle bays while its AC
  card read 51.5 W. `parsers.port_attached` asks the role and only the role;
  `port_watts` returns None — not zero — when the numbers are missing, and
  `port_is_live` (attached *and* measurable) is what the callers that go on
  to print volts and amps use. `parse_ports` also keeps a voltage that
  arrives without a current instead of dropping both.

- **Neither port command can see the card in the bay.** USB-C and USB-A
  expansion cards are passive passthroughs: there is nothing on them to
  enumerate, so `--pdports`/`--pdports-chromebook` describe the mainboard
  port behind the card and nothing else. A bay with a USB-C card and nothing
  plugged into it therefore reads idle, correctly — it just used to say
  "disconnected · idle", which reads as a failure to detect a card that is
  visibly there. The rows say "nothing attached", the panel caption says the
  CLI cannot see which card is fitted, and `_fill_cards` spells out why
  (`App.PASSIVE_CARDS_NOTE`). Only `--dp-hdmi-info` and `--audio-card-info`
  ever name a module, and neither says which bay it is in.

- **A reading command logs its output.** The Overview scan used to run four
  commands silently, so the drawer showed four bare `$` lines and a failed
  reading was indistinguishable from a parse that returned nothing. Every
  command in the app echoes its output now; `_read_into` is the one place
  that does it for the scan.

- **DP/HDMI and Audio cards are identified but not located.** Upstream says
  so outright: the HID API it goes through abstracts away the USB topology,
  "so we can't figure out which port the card is connected to". They are
  listed under the bays as present on the machine rather than dropped into a
  row, because putting one in a particular bay would be a guess — the same
  rule that gives an unidentified bay the neutral mark.

- **The chassis drawing is the detected machine.** It was one fixed 300x112
  rectangle with four bays at hard-coded coordinates for every model.
  `device_images.CHASSIS` carries each chassis's published width/depth in
  millimetres and its expansion-bay count, and `widgets.ChassisDiagram`
  scales from those. Use **one** scale for every model
  (`ChassisDiagram.pixels_per_mm`): fitting each one to the box
  independently makes them all come out the same size, because the Framework
  laptops have nearly identical width:depth ratios and differ mainly in
  absolute size. Shape it at build time, not only when readings arrive — the
  sensor read needs elevation and may never happen.

- **A timed tool draws a bar; a stepped one draws cells.** `navigation.MODE_BAR`
  is for a tool whose length is known before it starts (a 30 s burst, six
  samples five seconds apart) and gets one animated `TimedBar` driven by the
  clock on the UI side. `MODE_STEPS` is for a sequence whose steps each take
  as long as they take — the full system report, where "4 of 6" is the only
  honest progress there is. The numbers that used to be hard-coded in each
  tool body are `params`, editable next to Run, read at Run and frozen into
  `_tool_values` so no worker thread ever reaches into a widget.

- **Check `_busy` before touching any UI.** `run_tool` refuses while a tool
  is running, but a caller that marks a row running, shows the detail panel
  and starts the spinner *first* strands all of it when `run_tool` then
  returns without starting a thread — nothing emits `sig_tool_done`, so the
  row stays lit and the bar animates for the rest of the session. Guard at
  the top of the handler. `tests/test_smoke_gui.TestBusyGuard` covers it.

- **Expansion-card marks are drawn, not shipped.** `module_icons.py` holds
  an 18×18 stroke path per module type, in the same idiom as the rail icons,
  so they tint to the port's state and stay sharp at any scale with no image
  files. Storage cards are deliberately the exception: one storage card
  looks exactly like another, so those rows show the capacity in a bordered
  box instead. **What the app can actually identify is thin** — `--pdports`
  only says whether a bay negotiated a PD contract, which means USB-C and
  nothing else does, so that is the only inference made.
  `readings["module_hints"]` is the seam where real per-bay identification
  plugs in if the CLI ever reports it; until then an unidentified bay gets
  the neutral mark, not a plausible guess.

- **A setting lives on the pane it changes.** The charge presets were
  Diagnostics entries, so running one rewrote two Settings rows from a
  different section with no sign there that anything had moved. They are
  `navigation.SETTINGS_PRESETS` now, rendered above the rows they set.

- **Read a setting with the reader its row names.** framework_tool prints
  more than one number in some of these blocks and the generic reader took
  the wrong one: `--charge-limit` prints "Minimum 0%, Maximum 80%" and the
  first percentage won, so every machine reported a 0% limit; both
  fingerprint reads print a level *and* a percentage under one heading, and
  the percentage was handed to a combo box with no such entry, so the level
  never filled in at all. `SETTINGS_ROWS["parse"]` names the reader,
  `App.SETTING_PARSERS` maps it.

- **A reading is trimmed for the line it goes on, never for the log.** The
  Overview sub-line arrives longer than it is useful from two directions: on
  Windows the CPU is `%PROCESSOR_IDENTIFIER%` — "AMD64 Family 25 Model 116
  Stepping 1, AuthenticAMD", which names a generation rather than a chip —
  and an EC version carries three component commit hashes, a build timestamp
  and the hostname of the machine that built it. On a real Laptop 13 that
  wrapped onto three lines. `app.windows_cpu_brand` reads
  `ProcessorNameString` from the registry (the name the vendor actually
  ships), `power.short_cpu_label` trims it to "Ryzen 7 7840U" and returns
  **empty** for a CPUID dump rather than shortening nonsense, and
  `parsers.short_firmware` keeps the version and drops the provenance. The
  untrimmed strings are the sub-line's tooltip (`App._device_detail`) and the
  drawer still shows every command's raw output verbatim.

- **Ask whether there is AC before reporting AC watts.** The charger voltage
  and input current are printed whether or not an adapter is attached and
  are not zero on battery, so multiplying them unconditionally showed a few
  watts of phantom draw on an unplugged machine. `parsers.ac_connected`
  decides first; None means "it did not say", which is not the same as
  "there is no adapter".

- **An Auto button only where there is an auto.** Rows whose setting has a
  real automatic mode get one (`SETTINGS_ROWS["auto"]`); the two fingerprint
  rows share `--fp-led-level auto`, because `--fp-brightness` has no auto of
  its own and that is what releases both. A row whose setting genuinely has
  none — the keyboard backlight — gets no button rather than one that
  silently does nothing.

- **Danger styling is a rule, not a decoration.** Every destructive or
  hardware-risky control gets the danger colours *at the control*, plus a
  confirmation naming the exact command before it runs: Apply limits, Max
  burst, Fan max burst, and Set on Input deck mode (the deck carries the
  keyboard and trackpad, so switching it off leaves the machine without
  either). Never give one of these a neutral button.

- **Command execution wrapping** (`_build_cmd` in `app.py`):
  `[binary] + args`, optionally prefixed with `pkexec` (Linux, unless
  already root) and/or `flatpak-spawn --host` (when running inside the
  Flatpak sandbox — the sandbox can't reach the EC at all, so this is a
  deliberate, unavoidable sandbox hole; see `flatpak/README.md`).

- **Two command paths, on purpose.** `_build_cmd`/`_exec` are
  framework_tool-only: they put the binary from the Console pane in front of
  the args. Everything on the CPU limits/Setup/Drivers panes runs a
  *different*
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
  - `deps.py` never returns "nothing I can do". **Name the binary you want**
    in a `KIND_DOWNLOAD` entry: `asset_match` alone is ambiguous, and the
    RyzenAdj release ships both `ryzenadj-win64.zip` (the CLI) and
    `libryzenadj-win64.zip` (the library — DLL, .lib and header, no
    executable). Matching on `win64` and taking the first hit downloaded the
    library, so the install "succeeded" and then reported ryzenadj.exe
    missing. `pick_asset` scores on the binary's name and penalises
    lib/debug/src builds. Unpacking then deletes the archive (`deps.cleanup`)
    — archives only: the DLLs beside ryzenadj.exe are what let it reach the
    SoC, so tidying the unpacked tree would break the tool just installed. Every dependency yields an
    install plan; where no package exists (RyzenAdj outside the AUR) the
    plan degrades to `KIND_MANUAL` with upstream's page. Emitting an
    `apt-get install ryzenadj` that cannot work would be worse than saying
    so. Nothing installs without a confirm dialog showing the exact command.
  - `drivers.py` matches the board string from `--versions` against a
    catalog ordered **most specific first** ("Laptop 13 Pro" must precede
    the entry that matches any "Ryzen AI 300"). Unmatched boards fall back
    to the Knowledge Base index, never to nothing. Framework's URLs live
    only in `CATALOG`/`EXTRA`, so fixing a dead link is a one-line change.
    It **links and does not fetch**, by request and because it works better:
    Framework keeps one downloads list per device build that is always
    current, and the Knowledge Base 403s scripted fetches anyway. An earlier
    version scraped the bundle link out of the page; `test_drivers.py` has a
    guard that fails if any networking creeps back into the module. The
    app's only network access now lives in `deps.py` (fetching a helper's
    GitHub release), which is why the Flatpak needs no `--share=network`.

- **Blocked commands** (`App.BLOCKED` in `app.py`):
  `--flash-ec`, `--flash-ro-ec`, `--flash-rw-ec`, `--flash-gpu-descriptor*`,
  `-f`/`--force`. These can brick the hardware; they're excluded from every
  button *and* from the free-form custom-args field. `--console follow` is
  also blocked in the custom-args field specifically because it never
  returns, which would hang a worker thread forever. Don't add UI for any
  of these without discussing it first — this was a deliberate, repeated
  decision across the project, not an oversight.

- **Threading model**: every command runs on a background `threading.Thread`
  so the UI never blocks; results come back by emitting a Qt signal, which
  Qt queues onto the UI thread. A worker thread must never touch a widget —
  `sig_log`, `sig_status`, `sig_detected`, `sig_progress`, `sig_readings`,
  `sig_fill` and `sig_tool_done` are the whole interface between them and
  the UI, and that is the Qt equivalent of the Tk version's `after(0, …)`
  rule. The 14 diagnostics are multi-step sequences with a shared cancel
  flag (`self._cancel`) checked between steps; the multi-step ones report
  per-step progress into the Diagnostics detail panel, whose "Cancel and
  restore auto" button stays reachable for the whole run. State-changing
  tools (fan duty, kb backlight, fingerprint LED) always restore the
  previous/auto state in a `finally` block, including on cancel.

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

4. **Schedule startup background work through the event loop, not from
   `__init__`.** In the Tk version, spawning the device-scan thread directly
   from `__init__` raced Tcl's startup and threw
   `RuntimeError: main thread is not in main loop`; the fix was
   `self.after(150, self._rescan)`. Qt is not as fragile here, but the same
   shape is kept — `QTimer.singleShot(150, self._rescan)` — because the
   window should be on screen before a scan that can take seconds reports
   back into it. Do the same for any new startup-time background work.

5. **Every packaging path has to carry the whole app, and the file list is
   what kept falling behind.** The original single-file packaging shipped
   only `framework_gui.py`, producing an exe/Flatpak that died with
   `ModuleNotFoundError: No module named 'parsers'` on launch — invisible
   until you run the *packaged* build, since a source checkout always works.
   Each new module made it more likely again, because three scripts each
   held their own list of filenames. The `frameworkgui` package is the fix:
   `windows/build.bat` and `windows/install.ps1` copy the **directory**, so
   a new module needs no edit there at all, and the assets moved inside it
   so they travel the same way. The Flatpak manifest is the one exception —
   flatpak-builder's `file` sources are one file each, so a new module still
   needs its `install -Dm644` line and its `sources:` entry there.
   `tests/test_packaging.py` fails until it does, and also fails if a Python
   file other than the launcher appears at the repository root.

   The images have one extra wrinkle: PyInstaller's `--onefile` unpacks
   bundled data into a temporary tree it advertises as `sys._MEIPASS`, so
   `device_images.asset_root()` looks there first and next to the module
   otherwise. Load a data file any other way and it works from a checkout
   and not from the exe.

6. **GUI tests need a real event loop, and a real teardown between
   apps.** Each test builds a fresh `App()` in the same process. Let the
   loop run (`app.exec()`) and quit it from a `QTimer` once results are
   captured, rather than pumping events by hand; then `close()` and
   `deleteLater()` the window and let `processEvents()` reap it before the
   next one is built. Two windows alive at once share the application-wide
   style sheet and the second one's assertions start reading the first
   one's widgets. (The Tk version needed the same discipline for a nastier
   reason — Tk variables' `__del__` calling into Tcl from the *next* app's
   worker thread, producing `Tcl_AsyncDelete: async handler deleted by the
   wrong thread` and an intermittent timeout. The lesson survived the
   toolkit change even though the mechanism did not.)

7. **Qt does not re-evaluate property selectors on its own.** Variants are
   selected with dynamic properties (`role`, `running`, `selected`), and
   setting one changes nothing visible until the widget is unpolished and
   re-polished — that is what `widgets.restyle()` is for. A running tool row
   that keeps its idle colours is this bug, not a style-sheet bug.

8. **A rebuilt widget tree has to be put back where it was.** `_build_pages()`
   destroys and rebuilds every section on each device scan, because gating
   changes which rows *exist*, not just whether they are enabled. It also
   re-applies anything already read (`_apply_readings({})`), or the panes
   would look unread the moment a rescan finished. The Tk version had a
   sharper version of the same trap: re-packing a widget moved it to the end
   of the pack order, so after the first scan the tabs landed below the
   output pane. Anything rebuilt at runtime needs its position and its state
   restored deliberately.

9. **Screenshots under Xvfb lie if you grab too early.** Widgets come out
   blank — the geometry is right, the paint hasn't happened. Let the event
   loop turn (a short `QTimer.singleShot` after `processEvents()`) before
   `window.grab()`. Worth knowing before "fixing" a
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
  diagnostic and each Ports & modules query and diff actual output against
  the samples in `tests/test_parsers.py`.
  Two rounds of that have now happened, both from a user's screenshots of a
  Laptop 13 AMD (EC `azalea_v3.4`), and between them they found five real
  mismatches: `--pdports` named no ports at all on that EC (hence the
  `--pdports-chromebook` fallback), `--charge-limit`'s two percentages were
  read in the wrong order, the AC card multiplied charger registers that are
  non-zero on battery, the charging port reported `Sink` with no current
  limit beside it so every bay read idle, and the Overview's sub-line was
  three wrapped lines of CPUID string and EC build provenance. Assume there
  are more.
- **The whole app has only ever run under Xvfb and Qt's offscreen
  platform.** The layout was checked by screenshotting all nine sections at
  the design's 1180x780 and comparing them to the handoff's captures, which
  is a real check but not the same as using it. Nothing has exercised a
  window manager, a HiDPI screen, a font that is not DejaVu, or the
  responsive collapse below 1040px on a real desktop.
- **Acrylic has never been composited here, and the Windows path has been
  wrong once already.** `backdrop.py`'s decision table is unit-tested, but
  the CI environment has no compositor, so every screenshot is the opaque
  path. On a real Windows 11 machine the first version of this did nothing
  visible: it set `DWMWA_SYSTEMBACKDROP_TYPE` on a window handle that Qt
  then replaced, never extended the frame into the client area, and left
  Qt's own opaque window brush painting over whatever DWM drew. All four
  parts of the fix — see "The Windows backdrop takes four things" above —
  are still unverified on real hardware, as are the dark native titlebar and
  translucency under a real Wayland or KWin session. If it still looks
  wrong, check in this order: is Transparency effects on in Settings; does
  the status bar say "Acrylic on" or has the app fallen back; then the
  `DWM_SYSTEMBACKDROP_TYPE` value (the handoff and the SDK disagree about
  the numbering and this follows the SDK).
- **The icons now render correctly under this renderer, which is not the
  same as under Windows.** The reason for writing `iconpaths.py` was that Qt
  rendered them differently in the packaged build than in CI, and the new
  path is exercised in exactly the same places the old one was: Xvfb and Qt
  offscreen. It has one real advantage — the geometry is ours, unit-tested,
  and no longer depends on QtSvg being collected or on which Qt the exe was
  built against — but a look at the built exe is still what confirms it.
- **IBM Plex is specified but not vendored.** `theme.py` names IBM Plex Sans
  and Mono; no font files are in the repo, so every build falls back to the
  platform's own sans and mono faces. `load_fonts()` will pick up
  `.ttf`/`.otf` files dropped into a `fonts/` directory next to the modules,
  which is the intended way to add them (they are OFL and free to bundle).
  Until then the type is right in size and weight but not in face.
- **The move to a package has not been through a packaged build.** The app
  became `frameworkgui/` with a launcher at the root, and every packaging
  path was rewritten for it: `build.bat` and `install.ps1` copy the
  directory, the Flatpak manifest installs each module into the package
  directory, PyInstaller's `--add-data` maps `frameworkgui\assets` to
  `assets` so `sys._MEIPASS` resolution is unchanged. CI builds the exe on
  every push, so a broken Windows path shows up there; the Flatpak is only
  built on release or `workflow_dispatch`, so rehearse that before cutting
  one. A copied-install simulation (launcher + package in an empty
  directory, repo off `sys.path`) does resolve both the icons and the device
  images.
- **The device photographs came from the project owner, not from a licence
  check.** They are Framework product images; the repo carries no note of
  what permits their redistribution. Sort that out before publishing a
  release, or replace them — the app is complete without them, since
  `widgets.ImageSlot` falls back to text.
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
- **The Flatpak manifest was rewritten for Qt and has not been built
  since.** It moved from `org.freedesktop.Platform//24.08` (compiling Tcl,
  Tk and CPython from source) to `org.kde.Platform//6.7` plus two pinned
  PySide6 wheels. That should be both faster and simpler, but it is a fresh,
  unbuilt manifest: expect the first `workflow_dispatch` run to turn up
  something — a wheel that wants a newer `pip`, a missing platform plugin,
  the runtime's Python being a version the `cp39-abi3` wheels do not load
  into. Rehearse it before relying on a release. `tests/test_packaging.py`
  still only checks the manifest's *structure*, and the
  `flatpak-spawn --host` runtime behaviour remains unexercised regardless of
  whether the build goes green.
- **`windows/build.bat` now installs PySide6 and bundles `assets/`, and
  neither change has been through CI yet.** The exe will be far larger than
  the Tkinter one. If it fails to launch, the first thing to check is
  whether PyInstaller collected Qt's platform plugins.
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
  the CPU limits pane does that read-back automatically after Apply.
- **The Framework Knowledge Base URLs in `drivers.py` were collected from
  search results, not by loading each page.** They are the right shape and
  the right articles, but a moved article shows up as a 404 in someone's
  browser. Now that the pane is links-only these URLs *are* the feature, so
  confirming all twelve in a real browser matters more than it used to.
- **The persistence links on the CPU limits pane have not been opened
  either.** Same caveat, smaller blast radius: a dead one costs a user a search.
- **The app icon is real artwork now but has never been seen in place.**
  `assets/icons/` carries the Framework mark as a nine-size `.ico` and as
  PNGs; the exe, the Inno installer, the Start Menu shortcut, the Qt window
  icon and the Flatpak's hicolor theme all point at it, and the placeholder
  SVG is gone. None of that has been looked at on a real desktop. One thing
  to check first: the mark is near-black (#1f1f1f) on transparency, which is
  low contrast on a dark Windows taskbar — if it disappears there, the fix
  is a light or outlined variant, not a code change.

## Deliberately out of scope

- **Persisting power limits across reboots.** The limits the CPU limits pane
  sets are volatile — that is a property of the SoC registers, not a bug. Making
  them stick needs something to re-apply them at boot and after resume: a
  systemd unit, a scheduled task, a tray agent. All of those are background
  processes, which is the one requirement this project has never bent. The
  UI states the limitation instead. If this comes back, it is a decision to
  drop the no-background-processes rule, not a small feature.
- **Driving ThrottleStop.** It has no command line. The Setup pane can point
  at it and the Drivers pane can link it, but nothing here can script it. On
  Intel, `powercfg` (Windows) and RAPL (Linux) are what the app can actually
  drive.
- **Running downloaded installers.** The Drivers pane downloads a bundle and
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

1. Rehearse `.github/workflows/release.yml` with `workflow_dispatch`. Every
   packaging path was rewritten for the `frameworkgui` package, and the
   Flatpak one has never been built successfully even before that — it went
   from source-built Tcl/Tk/CPython to the KDE runtime plus pinned PySide6
   wheels and has not been run once. This is between you and a release.
2. Launch the built exe and the built Flatpak and look at them. Everything
   so far has been Xvfb and Qt's offscreen platform — no window manager, no
   HiDPI, no real fonts. This is where a packaged-only failure (a missing
   Qt platform plugin, an asset that did not make it into `sys._MEIPASS`)
   would show up — and it is also the only way to confirm the rail icons,
   whose whole reason for being redrawn by `iconpaths.py` was that the
   packaged Qt rendered them differently from the Qt in CI.
3. Get access to a real Framework device (any model) and validate the
   parsers/detection against real `--versions`/`--power`/`--thermal`/
   `--pdports` output. Still the single highest-value thing for correctness,
   and the Overview's stat cards and bay panel are new consumers of that
   output.
4. See acrylic composited for the first time: Windows 11 for the real system
   backdrop and the dark titlebar, a Wayland or KWin session for the Linux
   translucency path. Check the fallback strip appears where it should, and
   that turning Transparency effects off in Windows Settings produces the
   strip rather than a status bar claiming an acrylic that is not there.
5. Vendor IBM Plex Sans/Mono into `fonts/` (OFL, free to bundle) so the type
   matches the design instead of falling back to the platform's faces.
6. Settle the licence position on `frameworkgui/assets/devices/*.png` and
   write it down, or replace them.
7. Run `FrameworkGUI-Setup.exe` on a real Windows machine: install,
   Start Menu group, uninstall, reinstall over the top. CI proves it
   compiles, nothing yet proves it installs.
8. Same for the script installers (`install-exe.cmd`) from an SMB share,
   including the uninstaller they now drop in `%LOCALAPPDATA%\FrameworkGUI`.
9. Apply a power limit on a real AMD Framework with RyzenAdj installed and
   confirm the read-back matches — then do the same for RAPL on Intel Linux
   and `powercfg` on Windows.
10. Open all twelve Knowledge Base URLs in `drivers.py` in a browser and
    confirm each still resolves — they are the whole Drivers pane now.
11. Confirm the app icon reads on a dark Windows taskbar and in a Linux
    shell's app grid — it is near-black on transparency, which is the one
    thing about it that might need a lighter variant.
12. Re-check the port reading on an EC that *does* implement `--pdports`.
    The two-command fallback is exercised only against a stub; a board where
    the first command answers should still take the first path, and
    `readings["ports_source"]` on the Overview says which one ran.
