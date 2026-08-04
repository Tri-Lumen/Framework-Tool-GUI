#!/usr/bin/env python3
"""
Framework System GUI — a Tkinter front-end for framework_tool
(https://github.com/FrameworkComputer/framework-system)

Requirements: Python 3.8+, framework_tool installed (host-side when in Flatpak).
No third-party packages.

Linux: most commands need root — run as root or use the pkexec checkbox.
Windows: run elevated (the packaged exe self-elevates).
Flatpak: commands run on the host via flatpak-spawn.

Multi-step tools (fan test, sweeps, monitors) run many commands in a row.
If you rely on pkexec you will get a prompt per command unless a polkit
policy with auth_admin_keep is installed — for those tools, run elevated.

On launch (and via "Rescan device") the GUI runs `--versions`, parses the
mainboard type, and shows only the controls that apply to that model
(e.g. stylus/touchscreen on Laptop 12, expansion bay on Laptop 16, RGB LEDs
on Desktop, battery/keyboard-light/fingerprint controls only on laptops).
If detection fails or the model string isn't recognized, every control is
shown rather than guessing what to hide.

Deliberately excluded: --flash-* / --force. Use the CLI for those.
"""

import datetime
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from parsers import (
    RE_CHG_V, RE_CHG_A, RE_IN_A, RE_SOC, RE_LFCC, RE_DESIGN, RE_CYCLES,
    RE_AC, RE_RPM, RE_TEMP, parse_ports, detect_model,
)

IS_WINDOWS = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")
IN_FLATPAK = os.path.exists("/.flatpak-info")


def find_binary():
    if IN_FLATPAK:
        return "framework_tool"  # resolved on the host by flatpak-spawn
    for name in ("framework_tool", "framework-tool"):
        p = shutil.which(name)
        if p:
            return p
    return "framework_tool"


def is_root():
    if IS_WINDOWS:
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


# ---------- output parsers now live in parsers.py ----------


class App(tk.Tk):
    BLOCKED = {"--flash-ec", "--flash-ro-ec", "--flash-rw-ec",
               "--flash-gpu-descriptor", "--flash-gpu-descriptor-file",
               "-f", "--force"}

    def __init__(self):
        super().__init__()
        self.title("Framework System GUI")
        self.geometry("980x700")
        self.minsize(800, 560)

        self.binary = tk.StringVar(value=find_binary())
        self.use_pkexec = tk.BooleanVar(
            value=IS_LINUX and not is_root()
            and (IN_FLATPAK or shutil.which("pkexec") is not None)
        )
        self._busy = False
        self._cancel = False

        # Fail-open defaults: show every control until (or unless) detection
        # narrows things down.
        self.caps = {
            "model": "Detecting…", "detected": False,
            "is_laptop": True, "is_desktop": False, "is_laptop12": True,
            "has_touchscreen": True, "has_stylus": True,
            "has_expansion_bay": True, "has_rgbkbd": True,
        }
        self.detected_var = tk.StringVar(value="Detecting device…")

        self._build_topbar()
        self._build_tabs()
        self._build_output()
        self._build_statusbar()

        if IS_LINUX and not is_root() and not self.use_pkexec.get():
            self.set_status("Not running as root — most commands will fail.")

        # Defer to after mainloop starts — spawning the scan thread directly
        # here can race Tk's startup and touch a Tk variable before the
        # interpreter is in its main loop.
        self.after(150, self._rescan)

    # ================= UI =================

    def _build_topbar(self):
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill="x")
        ttk.Label(bar, text="Binary:").pack(side="left")
        ttk.Entry(bar, textvariable=self.binary, width=28).pack(side="left", padx=(4, 12))
        if IS_LINUX:
            ttk.Checkbutton(bar, text="Elevate with pkexec",
                            variable=self.use_pkexec).pack(side="left")
        self.cancel_btn = ttk.Button(bar, text="Cancel tool", state="disabled",
                                     command=self._request_cancel)
        self.cancel_btn.pack(side="right", padx=(4, 0))
        ttk.Button(bar, text="Self-test (-t)",
                   command=lambda: self.run(["-t"])).pack(side="right")

        bar2 = ttk.Frame(self, padding=(8, 0))
        bar2.pack(fill="x")
        ttk.Label(bar2, textvariable=self.detected_var,
                  foreground="#555").pack(side="left")
        ttk.Button(bar2, text="Rescan device",
                   command=self._rescan).pack(side="right")

    def _build_tabs(self):
        if hasattr(self, "nb"):
            self.nb.destroy()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="x", padx=8)
        self._tab_tools()
        self._tab_info()
        self._tab_fans()
        self._tab_settings()
        self._tab_ports()
        self._tab_console()

    # ---- device detection ----

    def _rescan(self):
        if self._busy:
            self.set_status("Busy — wait or cancel the running tool.")
            return
        self._busy = True
        self.detected_var.set("Scanning device…")
        self.set_status("Scanning device…")
        threading.Thread(target=self._detect_worker, daemon=True).start()

    def _detect_worker(self):
        rc, out = self._exec(["--versions"], timeout=15)
        if rc != 0 or not out.strip():
            caps = dict(self.caps)
            caps.update(model="Unknown (detection failed)", detected=False)
        else:
            caps = detect_model(out)
        self.after(0, self._apply_detection, caps)

    def _apply_detection(self, caps):
        self.caps = caps
        self._busy = False
        if caps["detected"]:
            self.detected_var.set(f"Detected: {caps['model']}")
            self.set_status("Device scan complete.")
        else:
            self.detected_var.set(f"{caps['model']} — showing all controls.")
            self.set_status("Could not identify the device model — showing all controls.")
        # Keep the same tab selected across rebuild, where possible.
        try:
            current = self.nb.tab(self.nb.select(), "text")
        except Exception:  # noqa: BLE001
            current = None
        self._build_tabs()
        if current:
            for tab_id in self.nb.tabs():
                if self.nb.tab(tab_id, "text") == current:
                    self.nb.select(tab_id)
                    break

    def _tab_tools(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Tools")
        # requires: None (always shown) or a self.caps key that must be truthy
        tools = [
            ("Power input wattage", self.tool_input_power,
             "AC contract + measured input/charge power", "is_laptop"),
            ("Fan speed test", self.tool_fan_test,
             "Ramp 0→100% duty, log RPM per step, restore auto", None),
            ("Fan max burst (30 s)", self.tool_fan_burst,
             "100% duty for 30 s (dust blow-out), then auto", None),
            ("Battery health report", self.tool_battery_health,
             "Full-charge vs design capacity, cycle count", "is_laptop"),
            ("Charging speed check", self.tool_charge_speed,
             "Current charge rate in C and est. 0→100% time", "is_laptop"),
            ("Thermal monitor (30 s)", self.tool_thermal_monitor,
             "6 samples; min/max per sensor + fan RPM", None),
            ("Port power map", self.tool_port_map,
             "Per-port role and negotiated wattage summary", None),
            ("Keyboard backlight sweep", self.tool_kblight_sweep,
             "0→100→0 in steps (visual check), restores 0", "is_laptop"),
            ("Fingerprint LED test", self.tool_fpled_cycle,
             "Cycle high/medium/low/ultra-low, restore auto", "is_laptop"),
            ("EC health check", self.tool_ec_health,
             "Self-test + EC firmware image/version", None),
            ("Security check", self.tool_security,
             "Privacy switches + chassis intrusion in one view", None),
            ("Full system report → file", self.tool_full_report,
             "Versions, power, thermal, ports… saved as .txt", None),
            ("Preset: Longevity (limit 80%)", lambda: self.tool_preset(80, "0.8"),
             "Charge limit 80%, rate 0.8C", "is_laptop"),
            ("Preset: Full charge (100%)", lambda: self.tool_preset(100, "1"),
             "Charge limit 100%, rate 1C", "is_laptop"),
        ]
        tools = [t for t in tools if t[3] is None or self.caps.get(t[3])]
        for i, (label, fn, tip, _req) in enumerate(tools):
            b = ttk.Button(f, text=label, command=lambda fn=fn: self.run_tool(fn))
            b.grid(row=i // 2, column=(i % 2) * 2, sticky="ew", padx=4, pady=3)
            ttk.Label(f, text=tip, foreground="#666").grid(
                row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=(0, 10))
        for c in (0, 2):
            f.columnconfigure(c, weight=1)
        ttk.Label(
            f, foreground="#a60",
            text="Multi-step tools issue many commands — run elevated "
                 "(or install the polkit keep-auth policy) to avoid repeated prompts.",
        ).grid(row=99, column=0, columnspan=4, sticky="w", pady=(8, 0))

    def _tab_info(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Info")
        buttons = [
            ("Firmware versions", ["--versions"], None),
            ("Power / battery", ["--power", "-vv"], "is_laptop"),
            ("Thermal", ["--thermal"], None),
            ("Sensors", ["--sensors"], None),
            ("Firmware features", ["--features"], None),
            ("ESRT table", ["--esrt"], None),
        ]
        buttons = [b for b in buttons if b[2] is None or self.caps.get(b[2])]
        for i, (label, args, _req) in enumerate(buttons):
            ttk.Button(f, text=label, command=lambda a=args: self.run(a)).grid(
                row=i // 3, column=i % 3, sticky="ew", padx=4, pady=4)
        for c in range(3):
            f.columnconfigure(c, weight=1)

    def _tab_fans(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Fans")
        ttk.Label(f, text="Duty cycle (%)").grid(row=0, column=0, sticky="w")
        self.fan_duty = tk.IntVar(value=50)
        ttk.Scale(f, from_=0, to=100, variable=self.fan_duty,
                  command=lambda v: self.fan_duty.set(int(float(v)))
                  ).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Label(f, textvariable=self.fan_duty, width=4).grid(row=0, column=2)
        ttk.Button(f, text="Set duty",
                   command=lambda: self.run(["--fansetduty", str(self.fan_duty.get())])
                   ).grid(row=0, column=3, padx=4)
        ttk.Label(f, text="Target RPM").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.fan_rpm = tk.StringVar(value="3000")
        ttk.Entry(f, textvariable=self.fan_rpm, width=8).grid(
            row=1, column=1, sticky="w", padx=6, pady=(8, 0))
        ttk.Button(f, text="Set RPM",
                   command=lambda: self.run(["--fansetrpm", self.fan_rpm.get().strip()])
                   ).grid(row=1, column=3, padx=4, pady=(8, 0))
        ttk.Button(f, text="Restore automatic fan control",
                   command=lambda: self.run(["--autofanctrl"])
                   ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Button(f, text="Read thermal",
                   command=lambda: self.run(["--thermal"])
                   ).grid(row=2, column=3, padx=4, pady=(12, 0))
        f.columnconfigure(1, weight=1)

    def _tab_settings(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Settings")
        caps = self.caps
        r = 0  # running row counter so hidden sections don't leave gaps

        if caps.get("is_laptop"):
            ttk.Label(f, text="Max charge limit (%)").grid(row=r, column=0, sticky="w")
            self.charge_limit = tk.StringVar(value="80")
            ttk.Entry(f, textvariable=self.charge_limit, width=6).grid(row=r, column=1, sticky="w")
            ttk.Button(f, text="Get", command=lambda: self.run(["--charge-limit"])
                       ).grid(row=r, column=2, padx=2)
            ttk.Button(f, text="Set",
                       command=lambda: self.run(["--charge-limit", self.charge_limit.get().strip()])
                       ).grid(row=r, column=3, padx=2)
            r += 1

            ttk.Label(f, text="Charge rate limit (C)").grid(row=r, column=0, sticky="w", pady=4)
            self.charge_rate = tk.StringVar(value="1")
            ttk.Entry(f, textvariable=self.charge_rate, width=6).grid(row=r, column=1, sticky="w")
            ttk.Button(f, text="Set",
                       command=lambda: self.run(["--charge-rate-limit", self.charge_rate.get().strip()])
                       ).grid(row=r, column=3, padx=2)
            r += 1

            ttk.Separator(f, orient="horizontal").grid(row=r, column=0, columnspan=6,
                                                       sticky="ew", pady=8)
            r += 1

            ttk.Label(f, text="Keyboard backlight (%)").grid(row=r, column=0, sticky="w")
            self.kblight = tk.IntVar(value=20)
            ttk.Scale(f, from_=0, to=100, variable=self.kblight,
                      command=lambda v: self.kblight.set(int(float(v)))
                      ).grid(row=r, column=1, columnspan=2, sticky="ew", padx=6)
            ttk.Label(f, textvariable=self.kblight, width=4).grid(row=r, column=3)
            ttk.Button(f, text="Get", command=lambda: self.run(["--kblight"])
                       ).grid(row=r, column=4, padx=2)
            ttk.Button(f, text="Set",
                       command=lambda: self.run(["--kblight", str(self.kblight.get())])
                       ).grid(row=r, column=5, padx=2)
            r += 1

            ttk.Label(f, text="Fingerprint LED level").grid(row=r, column=0, sticky="w", pady=4)
            self.fp_level = tk.StringVar(value="auto")
            ttk.Combobox(f, textvariable=self.fp_level, width=10, state="readonly",
                         values=["auto", "high", "medium", "low", "ultra-low"]
                         ).grid(row=r, column=1, sticky="w")
            ttk.Button(f, text="Get", command=lambda: self.run(["--fp-brightness"])
                       ).grid(row=r, column=4, padx=2)
            ttk.Button(f, text="Set",
                       command=lambda: self.run(["--fp-led-level", self.fp_level.get()])
                       ).grid(row=r, column=5, padx=2)
            r += 1

            ttk.Label(f, text="Fingerprint LED brightness (%)").grid(row=r, column=0, sticky="w")
            self.fp_pct = tk.StringVar(value="55")
            ttk.Entry(f, textvariable=self.fp_pct, width=6).grid(row=r, column=1, sticky="w")
            ttk.Button(f, text="Set",
                       command=lambda: self.run(["--fp-brightness", self.fp_pct.get().strip()])
                       ).grid(row=r, column=5, padx=2)
            r += 1

            ttk.Separator(f, orient="horizontal").grid(row=r, column=0, columnspan=6,
                                                       sticky="ew", pady=8)
            r += 1

        if caps.get("is_laptop12"):
            ttk.Label(f, text="Tablet mode override").grid(row=r, column=0, sticky="w")
            self.tablet_mode = tk.StringVar(value="auto")
            ttk.Combobox(f, textvariable=self.tablet_mode, width=10, state="readonly",
                         values=["auto", "tablet", "laptop"]).grid(row=r, column=1, sticky="w")
            ttk.Button(f, text="Set",
                       command=lambda: self.run(["--tablet-mode", self.tablet_mode.get()])
                       ).grid(row=r, column=5, padx=2)
            r += 1

        if caps.get("has_touchscreen"):
            ttk.Label(f, text="Touchscreen").grid(row=r, column=0, sticky="w", pady=4)
            ttk.Button(f, text="Enable",
                       command=lambda: self.run(["--touchscreen-enable", "true"])
                       ).grid(row=r, column=1, sticky="w")
            ttk.Button(f, text="Disable",
                       command=lambda: self.run(["--touchscreen-enable", "false"])
                       ).grid(row=r, column=2, sticky="w")
            r += 1

        if caps.get("is_laptop"):
            ttk.Label(f, text="Input deck mode").grid(row=r, column=0, sticky="w")
            self.deck_mode = tk.StringVar(value="auto")
            ttk.Combobox(f, textvariable=self.deck_mode, width=10, state="readonly",
                         values=["auto", "on", "off", "reset"]).grid(row=r, column=1, sticky="w")
            ttk.Button(f, text="Set",
                       command=lambda: self.run(["--inputdeck-mode", self.deck_mode.get()])
                       ).grid(row=r, column=5, padx=2)
            r += 1

        if caps.get("has_rgbkbd"):
            ttk.Separator(f, orient="horizontal").grid(row=r, column=0, columnspan=6,
                                                       sticky="ew", pady=8)
            r += 1
            ttk.Label(f, text="RGB LEDs (hex, e.g. FF0000)").grid(row=r, column=0, sticky="w")
            self.rgb_hex = tk.StringVar(value="FF0000")
            ttk.Entry(f, textvariable=self.rgb_hex, width=8).grid(row=r, column=1, sticky="w")
            ttk.Button(f, text="Set all",
                       command=self._set_rgb_all).grid(row=r, column=2, padx=2)
            ttk.Button(f, text="Clear all",
                       command=self._clear_rgb_all).grid(row=r, column=3, padx=2)
            r += 1

        if r == 0:
            ttk.Label(f, text="No model-specific settings detected for this device.",
                      foreground="#666").grid(row=0, column=0, sticky="w")

        for c in (1, 2):
            f.columnconfigure(c, weight=1)

    def _set_rgb_all(self):
        hexval = self.rgb_hex.get().strip().lstrip("#") or "FF0000"
        self.run(["--rgbkbd", "0"] + [f"0x{hexval}"] * 8)

    def _clear_rgb_all(self):
        self.run(["--rgbkbd", "0"] + ["0"] * 8)

    def _tab_ports(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Ports & Modules")
        caps = self.caps
        buttons = [
            ("USB-C PD ports", ["--pdports"], None),
            ("PD controllers", ["--pd-info"], None),
            ("DP / HDMI card", ["--dp-hdmi-info"], None),
            ("Audio card", ["--audio-card-info"], None),
            ("Input deck", ["--inputdeck"], "is_laptop"),
            ("Expansion bay (L16)", ["--expansion-bay"], "has_expansion_bay"),
            ("Intrusion switch", ["--intrusion"], None),
            ("Privacy switches", ["--privacy"], "is_laptop"),
            ("Stylus battery", ["--stylus-battery"], "has_stylus"),
        ]
        buttons = [b for b in buttons if b[2] is None or caps.get(b[2])]
        for i, (label, args, _req) in enumerate(buttons):
            ttk.Button(f, text=label, command=lambda a=args: self.run(a)).grid(
                row=i // 3, column=i % 3, sticky="ew", padx=4, pady=4)
        for c in range(3):
            f.columnconfigure(c, weight=1)

    def _tab_console(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Console / Custom")
        ttk.Button(f, text="EC console (recent)",
                   command=lambda: self.run(["--console", "recent"])
                   ).grid(row=0, column=0, sticky="w", padx=4, pady=4)
        ttk.Label(f, text="Custom args:").grid(row=1, column=0, sticky="w", padx=4)
        self.custom = tk.StringVar()
        e = ttk.Entry(f, textvariable=self.custom)
        e.grid(row=1, column=1, sticky="ew", padx=4)
        e.bind("<Return>", lambda _e: self._run_custom())
        ttk.Button(f, text="Run", command=self._run_custom).grid(row=1, column=2, padx=4)
        f.columnconfigure(1, weight=1)

    def _build_output(self):
        frame = ttk.Frame(self, padding=(8, 4))
        frame.pack(fill="both", expand=True)
        self.out = scrolledtext.ScrolledText(
            frame, wrap="none",
            font=("Consolas" if IS_WINDOWS else "monospace", 10),
            state="disabled")
        self.out.pack(fill="both", expand=True)

    def _build_statusbar(self):
        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status, anchor="w",
                  padding=(8, 2)).pack(fill="x")

    # ================= command plumbing =================

    def _build_cmd(self, args):
        cmd = [self.binary.get().strip() or "framework_tool"] + list(args)
        if IS_LINUX and self.use_pkexec.get() and not is_root():
            cmd = ["pkexec"] + cmd
        if IN_FLATPAK:
            cmd = ["flatpak-spawn", "--host"] + cmd
        return cmd

    def _exec(self, args, timeout=60):
        """Synchronous — only call from worker threads. Returns (rc, text)."""
        cmd = self._build_cmd(args)
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return p.returncode, (p.stdout or "") + \
                (("\n" + p.stderr) if p.stderr else "")
        except FileNotFoundError:
            return 127, f"Binary not found: {cmd[0]}"
        except subprocess.TimeoutExpired:
            return 124, "Command timed out."
        except Exception as e:  # noqa: BLE001
            return 1, f"Error: {e}"

    def _run_custom(self):
        args = self.custom.get().split()
        if not args:
            return
        blocked = self.BLOCKED.intersection(args)
        if blocked:
            messagebox.showerror(
                "Blocked",
                f"{', '.join(sorted(blocked))} can brick hardware and is "
                "disabled here. Use the CLI directly.")
            return
        if "--console" in args and "follow" in args:
            messagebox.showerror("Blocked", "--console follow never exits; use 'recent'.")
            return
        self.run(args)

    def run(self, args):
        """Single command → replaces the output pane."""
        if self._busy:
            self.set_status("Busy — wait or cancel the running tool.")
            return
        self._busy = True
        self.set_status("Running: " + " ".join(self._build_cmd(args)))
        threading.Thread(target=self._single_worker, args=(args,), daemon=True).start()

    def _single_worker(self, args):
        rc, text = self._exec(args)
        self.after(0, self._single_done, rc, text)

    def _single_done(self, rc, text):
        self._busy = False
        self._set_output(text.strip() + "\n")
        self.set_status(f"Done (exit {rc})")

    # ---- tool (multi-step) plumbing ----

    def run_tool(self, fn):
        if self._busy:
            self.set_status("Busy — wait or cancel the running tool.")
            return
        self._busy = True
        self._cancel = False
        self.cancel_btn.configure(state="normal")
        self._set_output("")
        threading.Thread(target=self._tool_worker, args=(fn,), daemon=True).start()

    def _tool_worker(self, fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            self._append(f"\nTool error: {e}\n")
        finally:
            self.after(0, self._tool_done)

    def _tool_done(self):
        self._busy = False
        self.cancel_btn.configure(state="disabled")
        self.set_status("Tool finished." if not self._cancel else "Tool cancelled.")

    def _request_cancel(self):
        self._cancel = True
        self.set_status("Cancelling after current step…")

    def _sleep(self, seconds):
        """Interruptible sleep; returns False if cancelled."""
        end = time.time() + seconds
        while time.time() < end:
            if self._cancel:
                return False
            time.sleep(0.2)
        return True

    def _append(self, text):
        self.after(0, self.__append_ui, text)

    def __append_ui(self, text):
        self.out.configure(state="normal")
        self.out.insert("end", text)
        self.out.see("end")
        self.out.configure(state="disabled")

    def _set_output(self, text):
        self.after(0, self.__set_ui, text)

    def __set_ui(self, text):
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.insert("1.0", text)
        self.out.configure(state="disabled")

    def set_status(self, msg):
        self.after(0, self.status.set, msg)

    # ================= tools =================

    def tool_input_power(self):
        self._append("=== Power input wattage ===\n")
        rc, power = self._exec(["--power", "-vv"])
        if rc != 0:
            self._append(power + "\n")
            return
        rc2, pdout = self._exec(["--pdports"])
        ac = RE_AC.search(power)
        v = RE_CHG_V.search(power)
        chg = RE_CHG_A.search(power)
        inp = RE_IN_A.search(power)
        soc = RE_SOC.search(power)
        if ac:
            self._append(f"AC: {ac.group(1).strip()}\n")
        if soc:
            self._append(f"Battery SoC: {soc.group(1)}%\n")
        if rc2 == 0:
            for p in parse_ports(pdout):
                if p.get("watts") and p["role"] == "Sink":
                    self._append(
                        f"Port {p['port']}: adapter contract "
                        f"{p['volts']:.1f} V × {p['ma']} mA = {p['watts']:.1f} W max\n")
        if v and inp:
            est = int(v.group(1)) * int(inp.group(1)) / 1e6
            self._append(f"Measured input draw (est.): {est:.1f} W "
                         f"({v.group(1)} mV × {inp.group(1)} mA)\n")
        if v and chg:
            bw = int(v.group(1)) * int(chg.group(1)) / 1e6
            self._append(f"Battery charge power: {bw:.1f} W\n")
        if not (v and (inp or chg)):
            self._append("Could not parse charger values — raw output:\n" + power + "\n")

    def tool_fan_test(self):
        self._append("=== Fan speed test (0→100% duty) ===\n"
                     "Each step: set duty, wait 8 s for spin-up, read RPM.\n\n")
        results = []
        try:
            for duty in (0, 25, 50, 75, 100):
                if self._cancel:
                    break
                rc, out = self._exec(["--fansetduty", str(duty)])
                if rc != 0:
                    self._append(f"Set duty {duty}% failed:\n{out}\n")
                    break
                self._append(f"Duty {duty:3d}% … ")
                if not self._sleep(8):
                    self._append("cancelled\n")
                    break
                rc, out = self._exec(["--thermal"])
                m = RE_RPM.search(out)
                rpm = int(m.group(1)) if m else None
                results.append((duty, rpm))
                self._append(f"{rpm if rpm is not None else '??'} RPM\n")
        finally:
            self._exec(["--autofanctrl"])
            self._append("\nAutomatic fan control restored.\n")
        if len(results) >= 2:
            rpms = [r for _, r in results if r is not None]
            if rpms:
                self._append(f"Range observed: {min(rpms)}–{max(rpms)} RPM\n")
            if results[-1][0] == 100 and results[-1][1] in (None, 0):
                self._append("WARNING: no RPM at 100% duty — fan may be faulty/absent.\n")

    def tool_fan_burst(self):
        self._append("=== Fan max burst ===\nFull duty for 30 s, then auto.\n")
        rc, out = self._exec(["--fansetduty", "100"])
        if rc != 0:
            self._append(out + "\n")
            return
        try:
            for remaining in range(30, 0, -5):
                self._append(f"{remaining} s…\n")
                if not self._sleep(5):
                    break
        finally:
            self._exec(["--autofanctrl"])
            self._append("Automatic fan control restored.\n")

    def tool_battery_health(self):
        self._append("=== Battery health report ===\n")
        rc, out = self._exec(["--power", "-vv"])
        if rc != 0:
            self._append(out + "\n")
            return
        lfcc = RE_LFCC.search(out)
        design = RE_DESIGN.search(out)
        cycles = RE_CYCLES.search(out)
        if lfcc and design:
            health = 100.0 * int(lfcc.group(1)) / int(design.group(1))
            self._append(f"Design capacity:      {design.group(1)} mAh\n")
            self._append(f"Full-charge capacity: {lfcc.group(1)} mAh\n")
            self._append(f"Health:               {health:.1f}% of design\n")
        else:
            self._append("Could not parse capacities — raw output below.\n")
        if cycles:
            self._append(f"Cycle count:          {cycles.group(1)}\n")
        if not (lfcc and design):
            self._append("\n" + out + "\n")

    def tool_charge_speed(self):
        self._append("=== Charging speed check ===\n")
        rc, out = self._exec(["--power", "-vv"])
        if rc != 0:
            self._append(out + "\n")
            return
        ac = RE_AC.search(out)
        chg = RE_CHG_A.search(out)
        design = RE_DESIGN.search(out)
        soc = RE_SOC.search(out)
        if ac and "not" in ac.group(1):
            self._append("AC not connected — plug in a charger and rerun.\n")
            return
        if chg and design and int(chg.group(1)) > 0:
            c_rate = int(chg.group(1)) / int(design.group(1))
            self._append(f"Charge current: {chg.group(1)} mA "
                         f"→ {c_rate:.2f} C\n")
            self._append(f"Est. full 0→100% time at this rate: "
                         f"{60 / c_rate:.0f} min\n")
            if soc:
                self._append(f"Current SoC: {soc.group(1)}%\n")
        elif chg and int(chg.group(1)) == 0:
            self._append("Charger current is 0 mA — battery full, "
                         "at charge limit, or not charging.\n")
        else:
            self._append("Could not parse — raw output:\n" + out + "\n")

    def tool_thermal_monitor(self):
        self._append("=== Thermal monitor (6 samples, 5 s apart) ===\n")
        stats = {}
        rpm_seen = []
        for i in range(6):
            if self._cancel:
                break
            rc, out = self._exec(["--thermal"])
            if rc != 0:
                self._append(out + "\n")
                return
            line = [f"[{i + 1}/6]"]
            for name, val in RE_TEMP.findall(out):
                v = int(val)
                lo, hi = stats.get(name, (v, v))
                stats[name] = (min(lo, v), max(hi, v))
                line.append(f"{name}={v}C")
            m = RE_RPM.search(out)
            if m:
                rpm_seen.append(int(m.group(1)))
                line.append(f"fan={m.group(1)}rpm")
            self._append(" ".join(line) + "\n")
            if i < 5 and not self._sleep(5):
                break
        self._append("\nSummary (min–max):\n")
        for name, (lo, hi) in stats.items():
            self._append(f"  {name}: {lo}–{hi} C\n")
        if rpm_seen:
            self._append(f"  Fan: {min(rpm_seen)}–{max(rpm_seen)} RPM\n")

    def tool_port_map(self):
        self._append("=== Port power map ===\n")
        rc, out = self._exec(["--pdports"])
        if rc != 0:
            self._append(out + "\n")
            return
        ports = parse_ports(out)
        if not ports:
            self._append("No ports parsed — raw output:\n" + out + "\n")
            return
        for p in ports:
            if p.get("watts"):
                direction = ("drawing" if p["role"] == "Sink" else "supplying")
                self._append(f"Port {p['port']}: {p['role']:6s} {direction} "
                             f"{p['watts']:.1f} W "
                             f"({p['volts']:.1f} V / {p['ma']} mA)\n")
            else:
                self._append(f"Port {p['port']}: {p['role']:6s} "
                             f"no PD contract / nothing negotiated\n")

    def tool_kblight_sweep(self):
        self._append("=== Keyboard backlight sweep ===\n")
        rc, out = self._exec(["--kblight"])
        m = re.search(r"(\d+)\s*%", out) if rc == 0 else None
        original = m.group(1) if m else "0"
        levels = list(range(0, 101, 20)) + list(range(80, -1, -20))
        try:
            for lv in levels:
                if self._cancel:
                    break
                self._exec(["--kblight", str(lv)])
                self._append(f"{lv}% ")
                if not self._sleep(0.5):
                    break
        finally:
            self._exec(["--kblight", original])
            self._append(f"\nRestored to {original}%.\n")

    def tool_fpled_cycle(self):
        self._append("=== Fingerprint LED test ===\n"
                     "Watch the power button while levels cycle.\n")
        try:
            for level in ("high", "medium", "low", "ultra-low"):
                if self._cancel:
                    break
                self._exec(["--fp-led-level", level])
                self._append(f"{level} ")
                if not self._sleep(1.5):
                    break
        finally:
            self._exec(["--fp-led-level", "auto"])
            self._append("\nRestored to auto.\n")

    def tool_ec_health(self):
        self._append("=== EC health check ===\n")
        rc, out = self._exec(["-t"])
        self._append(f"Self-test exit code: {rc}\n{out.strip()}\n\n")
        rc, out = self._exec(["--versions"])
        if rc == 0:
            grab = False
            for line in out.splitlines():
                if line.startswith("EC Firmware"):
                    grab = True
                elif grab and not line.startswith(" "):
                    break
                if grab:
                    self._append(line + "\n")
        else:
            self._append(out + "\n")

    def tool_security(self):
        self._append("=== Security check ===\n")
        if self.caps.get("is_laptop"):
            rc, out = self._exec(["--privacy"])
            self._append("Privacy switches:\n" + out.strip() + "\n\n")
        else:
            self._append("Privacy switches: not applicable on this device.\n\n")
        rc, out = self._exec(["--intrusion"])
        self._append("Chassis intrusion:\n" + out.strip() + "\n")

    def tool_full_report(self):
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(os.path.expanduser("~"), f"framework_report_{ts}.txt")
        sections = [("FIRMWARE VERSIONS", ["--versions"]),
                    ("THERMAL", ["--thermal"]),
                    ("SENSORS", ["--sensors"]),
                    ("USB-C PD PORTS", ["--pdports"]),
                    ("INTRUSION", ["--intrusion"])]
        if self.caps.get("is_laptop"):
            sections[1:1] = [("POWER / BATTERY", ["--power", "-vv"])]
            sections += [("INPUT DECK", ["--inputdeck"]),
                         ("PRIVACY SWITCHES", ["--privacy"]),
                         ("CHARGE LIMIT", ["--charge-limit"])]
        if self.caps.get("has_expansion_bay"):
            sections.append(("EXPANSION BAY", ["--expansion-bay"]))
        self._append(f"=== Full system report ===\nWriting {path}\n\n")
        lines = [f"Framework system report — {ts}\n"]
        for title, args in sections:
            if self._cancel:
                break
            rc, out = self._exec(args)
            lines.append(f"\n===== {title} =====\n{out.strip()}\n")
            self._append(f"{title}: {'ok' if rc == 0 else f'exit {rc}'}\n")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.writelines(lines)
            self._append(f"\nSaved: {path}\n")
        except OSError as e:
            self._append(f"\nCould not write file: {e}\n")

    def tool_preset(self, limit, rate):
        self._append(f"=== Preset: charge limit {limit}%, rate {rate}C ===\n")
        rc, out = self._exec(["--charge-limit", str(limit)])
        self._append(out.strip() + "\n" if out.strip() else f"Charge limit → {limit}% (exit {rc})\n")
        rc, out = self._exec(["--charge-rate-limit", rate])
        self._append(out.strip() + "\n" if out.strip() else f"Rate limit → {rate}C (exit {rc})\n")
        rc, out = self._exec(["--charge-limit"])
        if rc == 0 and out.strip():
            self._append("Verify: " + out.strip() + "\n")


if __name__ == "__main__":
    App().mainloop()
