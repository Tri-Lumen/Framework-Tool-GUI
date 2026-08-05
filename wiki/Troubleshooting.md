# Troubleshooting

The output drawer is the first place to look for all of these. Every command
the app runs is echoed there with its output underneath — if a reading is
blank, the drawer says why.

## The expansion bays all read "not read"

`--pdports` uses a Framework-specific EC command that **not every EC firmware
implements**. Where it is missing, the CLI still exits 0 having printed only
errors, so the app saw a successful command that named no ports.

The app now falls back to `--pdports-chromebook`, which asks the same
question through the generic Chromium EC path and answers on boards the first
one does not. The caption above the bay rows says which command supplied the
reading.

If *both* come back empty, the drawer will show what each one printed. That
is a CLI/firmware limitation, not something the GUI can work around.

## Charge limit shows 0% when it is set to something else

Fixed. `--charge-limit` prints two percentages — `Minimum 0%, Maximum 80%` —
and the app used to read the first one, so every machine reported 0%. It
reads the maximum now.

## AC input shows a few watts with nothing plugged in

Fixed. The charger voltage and input current registers are reported whether
or not an adapter is attached and are not zero on battery. The app checks
`AC is:` first now and shows "on battery" instead of multiplying them.

## The sidebar icons look like random lines

Fixed. The icons are drawn from SVG path strings, and four of them used
SVG's implicit-lineto shorthand. That is legal SVG, but the Qt bundled with
the packaged Windows build drew the first segment and silently dropped the
rest of the path. Every path is written longhand now, and a test rejects the
shorthand so it cannot come back.

## RyzenAdj installs but ryzenadj.exe is not found

Fixed. The release ships **two** archives matching `win64`:
`ryzenadj-win64.zip` (the CLI) and `libryzenadj-win64.zip` (the library — a
DLL, a `.lib` and a header, no executable at all). The app matched on the
substring and took the first, which was the library. It now picks the archive
that actually carries the binary, and deletes the archive once unpacked.

If you hit this on an older build, delete
`%LOCALAPPDATA%\FrameworkGUI\tools` and reinstall from the Setup section.

## Fingerprint LED level never fills in when I press Get

Fixed. Both fingerprint reads print a level *and* a percentage under one
heading, and the app read the percentage — then tried to select "55" in a
combo box whose entries are `auto`/`high`/`medium`/`low`/`ultra-low`, so
nothing happened. Each row now names the reader that understands its output.

## Every command asks for a password (Linux)

The app wraps commands in `pkexec` when it is not already root, and a
multi-step diagnostic is many commands. Launch the app elevated instead and
you get one prompt for the session. The status bar shows which mode you are
in and lets you turn pkexec off.

## The window is translucent over nothing / acrylic is greyed out

The app probes whether the session can composite: Windows 11 build 22621+,
Wayland always, X11 only when something owns the `_NET_WM_CM_S0` selection.
An uncertain answer is always "no", because a translucent surface with
nothing behind it is worse than an opaque one. When the answer is no, the
app forces opaque, disables the Acrylic control and says so in a strip at
the top.

There is no portable blur on Linux, so "acrylic" there means translucency
without one. On Windows 11 it is the real system backdrop.

## A parser shows raw output instead of a nice reading

That is the intended failure mode. Upstream states plainly that "the
commandline does not guarantee a stable interface", so every parser here is
best-effort and every caller falls back to showing the raw text rather than
crashing or showing nothing.

If you see this, the drawer contains exactly what the app could not parse —
that is the useful thing to put in a bug report.

## Reporting something not listed here

Include the output drawer contents and your board string (the sub-line under
the device name on the Overview). The app has never been validated against
real hardware beyond one round of user feedback, so a real machine's actual
output is the single most useful thing you can provide.
