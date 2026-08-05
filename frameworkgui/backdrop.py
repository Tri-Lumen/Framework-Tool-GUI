"""
Whether this platform can composite a translucent window, and how to ask it to.

The design has two appearances. `acrylic` only means anything when something
is actually composited behind the window: a translucent surface on a system
that cannot composite is not a softer look, it is a window with nothing
behind it. So the app probes first, and where the answer is no it forces the
opaque appearance, disables the toggle and says why.

What each platform can do:

  Windows 11 (build >= 22621)  DwmSetWindowAttribute with
                               DWMWA_SYSTEMBACKDROP_TYPE gives the real
                               system backdrop, blur and all — but only
                               while Settings › Personalisation › Colours ›
                               "Transparency effects" is on. With it off,
                               DWM accepts the call and draws a flat
                               surface, so the app would claim an acrylic
                               it is not getting; that setting is read
                               here and answered as "no".
  Windows 10 and earlier       No system backdrop attribute. Opaque.
  Linux/Wayland                Always composited — translucent surfaces work.
                               There is no portable blur, so the surfaces are
                               translucent without one.
  Linux/X11                    Only with a compositing manager running, which
                               is what owning the _NET_WM_CM_S0 selection
                               means. Probed through libX11; no compositor,
                               no answer, or no libX11 all read as "no".
  Anything else                Opaque.

Stdlib only (ctypes), no toolkit import: the decision logic takes its inputs
as arguments so it is testable on any machine, and only the two `apply_*`
functions touch a real window handle.
"""

import ctypes
import sys

# DwmSetWindowAttribute attributes. Values are from the Windows SDK; they
# are stable, and sending one to an OS that does not know it just returns a
# failure HRESULT, which is why every call here is best-effort.
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
# The same attribute before Windows 10 20H1 renamed it. Sent as a fallback
# so the titlebar still goes dark on an older build.
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
DWMWA_SYSTEMBACKDROP_TYPE = 38

# DWM_SYSTEMBACKDROP_TYPE values. 3 is DWMSBT_TRANSIENTWINDOW — the acrylic
# backdrop, which is the effect the design asks for. (2 is Mica, the
# wallpaper-tinted variant; the handoff's table numbers these one higher
# than the SDK does, so this follows the SDK.)
DWMSBT_NONE = 1
DWMSBT_ACRYLIC = 3

# The first Windows 11 build that honours DWMWA_SYSTEMBACKDROP_TYPE.
WIN11_BACKDROP_BUILD = 22621


def windows_supports_backdrop(build):
    """True when a Windows build number can do system backdrops."""
    try:
        return int(build) >= WIN11_BACKDROP_BUILD
    except (TypeError, ValueError):
        return False


def _windows_transparency_setting():
    """Is "Transparency effects" on? True when it cannot be read.

    HKCU\\...\\Themes\\Personalize\\EnableTransparency is where the
    Settings toggle lands. Unreadable is answered as on: the registry
    value is a courtesy, and refusing acrylic because a key was missing
    would be a worse guess than trying it.
    """
    try:
        import winreg  # Windows only
    except ImportError:
        return True
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes"
                r"\Personalize") as key:
            value, _kind = winreg.QueryValueEx(key, "EnableTransparency")
        return bool(value)
    except (OSError, ValueError):
        return True


def _x11_has_compositor():
    """True when some process owns the _NET_WM_CM_S0 compositing selection.

    That selection is the standard "a compositing manager is running here"
    signal. Anything that goes wrong — no libX11, no display, an X error —
    is answered as "no compositor", because the cost of guessing wrong in
    that direction is a translucent window over a black hole.
    """
    try:
        xlib = ctypes.CDLL("libX11.so.6")
    except OSError:
        return False
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    display = xlib.XOpenDisplay(None)
    if not display:
        return False
    try:
        xlib.XInternAtom.restype = ctypes.c_ulong
        xlib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                     ctypes.c_int]
        xlib.XGetSelectionOwner.restype = ctypes.c_ulong
        xlib.XGetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        atom = xlib.XInternAtom(display, b"_NET_WM_CM_S0", 0)
        return bool(atom) and bool(xlib.XGetSelectionOwner(display, atom))
    except (AttributeError, OSError):
        return False
    finally:
        try:
            xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
            xlib.XCloseDisplay(display)
        except (AttributeError, OSError):
            pass


# Why acrylic is off, when it is. The message shown in the fallback strip
# is chosen from this: "cannot composite" is true of a Windows 10 box but
# unhelpful on a Windows 11 one where the user has simply turned
# transparency off and can turn it back on.
OK = ""
OLD_WINDOWS = "old-windows"
TRANSPARENCY_OFF = "transparency-off"
NO_COMPOSITOR = "no-compositor"
UNSUPPORTED_PLATFORM = "unsupported-platform"

_MESSAGES = {
    OLD_WINDOWS: ("This Windows build has no system backdrop — using opaque "
                  "surfaces instead."),
    TRANSPARENCY_OFF: ("Transparency effects are off in Windows Settings › "
                       "Personalisation › Colours — using opaque surfaces "
                       "instead."),
    NO_COMPOSITOR: ("No compositor is running on this session — using opaque "
                    "surfaces instead."),
    UNSUPPORTED_PLATFORM: ("This system cannot composite acrylic — using "
                           "opaque surfaces instead."),
}


def translucency_state(platform=None, environ=None, windows_build=None,
                       x11_probe=None, transparency_probe=None):
    """(can composite, why not) for this session.

    Every input is injectable so the decision table can be tested without
    being on the platform in question.
    """
    plat = platform if platform is not None else sys.platform
    env = environ if environ is not None else {}
    if plat.startswith("win"):
        build = windows_build
        if build is None:
            build = getattr(sys, "getwindowsversion", lambda: None)()
            build = getattr(build, "build", None)
        if not windows_supports_backdrop(build):
            return False, OLD_WINDOWS
        probe = transparency_probe or _windows_transparency_setting
        # DWM accepts DWMSBT_TRANSIENTWINDOW with the Settings toggle off
        # and then draws a flat surface, so the call "succeeding" is not
        # evidence of anything. Ask the setting instead of claiming an
        # acrylic that is not on screen.
        return (True, OK) if probe() else (False, TRANSPARENCY_OFF)
    if plat.startswith("linux"):
        session = (env.get("XDG_SESSION_TYPE") or "").lower()
        if session == "wayland" or env.get("WAYLAND_DISPLAY"):
            return True, OK
        if session == "x11" or env.get("DISPLAY"):
            probe = x11_probe or _x11_has_compositor
            return (True, OK) if probe() else (False, NO_COMPOSITOR)
        return False, NO_COMPOSITOR
    # macOS and the BSDs are not distribution targets for this app; rather
    # than claim a capability nobody has tested, they get the opaque path.
    return False, UNSUPPORTED_PLATFORM


def supports_translucency(platform=None, environ=None, windows_build=None,
                          x11_probe=None, transparency_probe=None):
    """Can this session composite a translucent window?"""
    return translucency_state(platform, environ, windows_build, x11_probe,
                              transparency_probe)[0]


def unavailable_message(reason=None):
    """The strip shown when acrylic is off, worded for the reason."""
    return _MESSAGES.get(reason or UNSUPPORTED_PLATFORM,
                         _MESSAGES[UNSUPPORTED_PLATFORM])


def status_label(appearance, supported):
    """The appearance state as the status bar words it."""
    if not supported:
        return "Acrylic unavailable — opaque"
    return "Acrylic on" if appearance == "acrylic" else "Opaque"


# ---------- applying it to a real window ----------

def _dwm_set(hwnd, attribute, value):
    """Best-effort DwmSetWindowAttribute. Returns True when it succeeded."""
    try:
        dwm = ctypes.windll.dwmapi  # noqa: F821 — Windows-only attribute
    except (AttributeError, OSError):
        return False
    data = ctypes.c_int(value)
    try:
        result = dwm.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), ctypes.c_uint(attribute),
            ctypes.byref(data), ctypes.sizeof(data))
    except (OSError, ValueError):
        return False
    return result == 0


class _Margins(ctypes.Structure):
    """The MARGINS struct DwmExtendFrameIntoClientArea takes."""

    _fields_ = [("cxLeftWidth", ctypes.c_int),
                ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int),
                ("cyBottomHeight", ctypes.c_int)]


# -1 on every edge is the documented "sheet of glass" — extend the frame
# across the whole client area. Without it the system backdrop is drawn
# only behind the non-client frame, which on a normal framed window means
# behind the titlebar and nowhere else: the window looks exactly as opaque
# as before even though DwmSetWindowAttribute returned success. That is
# the shape the acrylic bug took on a real machine.
_SHEET_OF_GLASS = (-1, -1, -1, -1)
_NO_GLASS = (0, 0, 0, 0)


def _dwm_extend_frame(hwnd, margins):
    """Best-effort DwmExtendFrameIntoClientArea. True when it succeeded."""
    try:
        dwm = ctypes.windll.dwmapi  # noqa: F821 — Windows-only attribute
    except (AttributeError, OSError):
        return False
    data = _Margins(*margins)
    try:
        result = dwm.DwmExtendFrameIntoClientArea(ctypes.c_void_p(hwnd),
                                                  ctypes.byref(data))
    except (OSError, ValueError):
        return False
    return result == 0


def apply_windows_backdrop(hwnd, acrylic):
    """Turn the Windows 11 system backdrop on or off for a window.

    Three calls, in this order, and all three are needed:

      1. the dark titlebar, because the app is a dark-only design and a
         light native titlebar above it reads as a bug rather than a theme;
      2. the frame extended across the client area, so the backdrop is
         drawn behind the app's own surfaces and not just the titlebar;
      3. the backdrop type itself.

    Returns True only when the backdrop type was accepted. The caller uses
    that: a window that asked for acrylic and did not get it should say
    "opaque" rather than claim an effect that is not on screen.

    Call it on a window that is already shown. Qt recreates the native
    window when WA_TranslucentBackground changes, and a recreated window is
    a new HWND with none of this on it.
    """
    if not hwnd:
        return False
    if not _dwm_set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1):
        _dwm_set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1)
    _dwm_extend_frame(hwnd, _SHEET_OF_GLASS if acrylic else _NO_GLASS)
    return _dwm_set(hwnd, DWMWA_SYSTEMBACKDROP_TYPE,
                    DWMSBT_ACRYLIC if acrylic else DWMSBT_NONE)
