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
                               system backdrop, blur and all.
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


def supports_translucency(platform=None, environ=None, windows_build=None,
                          x11_probe=None):
    """Can this session composite a translucent window?

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
        return windows_supports_backdrop(build)
    if plat.startswith("linux"):
        session = (env.get("XDG_SESSION_TYPE") or "").lower()
        if session == "wayland" or env.get("WAYLAND_DISPLAY"):
            return True
        if session == "x11" or env.get("DISPLAY"):
            probe = x11_probe or _x11_has_compositor
            return bool(probe())
        return False
    # macOS and the BSDs are not distribution targets for this app; rather
    # than claim a capability nobody has tested, they get the opaque path.
    return False


def unavailable_message():
    """The strip shown when the platform cannot composite."""
    return ("This system cannot composite acrylic — using opaque surfaces "
            "instead.")


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


def apply_windows_backdrop(hwnd, acrylic):
    """Turn the Windows 11 system backdrop on or off for a window.

    Also asks for the dark titlebar: the app is a dark-only design, and a
    light native titlebar above it looks like a bug rather than a theme.
    """
    if not hwnd:
        return False
    _dwm_set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1)
    return _dwm_set(hwnd, DWMWA_SYSTEMBACKDROP_TYPE,
                    DWMSBT_ACRYLIC if acrylic else DWMSBT_NONE)
