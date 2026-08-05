# Framework-Tool-GUI

A PySide6/Qt front-end for
[framework_tool](https://github.com/FrameworkComputer/framework-system), the
official CLI for controlling Framework laptop and desktop firmware.

The app has **no direct hardware access of any kind**. Every reading and
every change is a subprocess: it builds a command, runs it, and parses the
text that comes back. When a parse fails it shows the raw output rather than
guessing. The output drawer at the bottom of the window shows every command
it ran, verbatim, which means nothing here is a black box.

## Start here

| Page | What it covers |
| --- | --- |
| [[Installation]] | Windows installer, portable exe, Linux Flatpak, and installing `framework_tool` itself |
| [[Using the app]] | The nine sections, one at a time |
| [[Device support]] | Which controls each board gets, and why one may be missing |
| [[Troubleshooting]] | Blank readings, "not read" bays, permission prompts, missing icons |
| [[Architecture]] | How the app is put together, for anyone changing it |
| [[Development]] | Running the tests, building the packages, releasing |

## Two things worth knowing before you start

**Nothing runs in the background.** No service, timer, tray icon or autostart
entry, on either OS. A subprocess is spawned when you click a button and
exits when that command finishes. This is a hard requirement of the project,
not a default — it is why CPU power limits here do not survive a reboot, and
why the app tells you that instead of quietly installing something to
re-apply them.

**The firmware-flashing commands are refused.** `--flash-ec`,
`--flash-ro-ec`, `--flash-rw-ec`, `--flash-gpu-descriptor*` and `--force`
are excluded from every button *and* from the free-form arguments field.
They can brick the hardware. If you need them, use the CLI directly and
know what you are doing.

## Project status

This whole project was built without ever running against real Framework
hardware — testing uses a stub standing in for the CLI, with output samples
from upstream's `EXAMPLES.md`. One round of feedback from a real Laptop 13
has since corrected three real mismatches (see [[Troubleshooting]]), but
assume there are more. `CLAUDE.md` in the repository keeps the honest list
of what has and has not been verified.
