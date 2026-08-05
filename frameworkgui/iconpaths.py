"""
The icon path language, parsed here rather than by Qt.

Every icon in this app is a stroked path in an 18x18 box — the five rail
groups, the appearance toggle, the expansion-card marks. They used to be
handed to `QSvgRenderer` as a one-line SVG document, and on the Qt bundled
with the packaged Windows build that renderer dropped most of every path:
four of the five rail icons came out as a bare diagonal stroke on a real
machine while the same strings rendered perfectly under the Qt used in CI.
There is no way to test around that from here — the failure only exists in
the shipped build.

So the parsing is ours now. This module turns a path string into a flat
list of drawing operations:

    ("move", x, y)                            start a subpath
    ("line", x, y)                            straight segment
    ("cubic", c1x, c1y, c2x, c2y, x, y)       cubic bezier segment
    ("close",)                                close the current subpath

Arcs are converted to cubics here, so the toolkit side has four cases to
draw and no geometry to do. `widgets.stroke_pixmap` is the only caller.

Stdlib only (`math`, `re`), no toolkit import: the geometry is testable
without a display, which is the whole point of moving it here.
"""

import math
import re

# A letter, or a number. Any letter matches, not just the commands this
# module knows: an unrecognised one has to reach `parse` so it can be
# refused, and a letter that quietly failed to tokenize would be dropped
# silently — which is the exact failure mode this module was written to
# get rid of. SVG numbers may run together with no separator ("1-1",
# "0 0 1-1 1") and may be written in exponent form, so the number pattern
# carries its own sign and exponent rather than relying on whitespace.
_TOKEN = re.compile(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")

# How many numbers each command consumes per repetition.
ARGUMENTS = {
    "M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2,
    "A": 7, "Z": 0,
}

# The most a single cubic should span, in radians. Anything larger bulges
# away from the true ellipse, so arcs are split into 90-degree pieces.
_MAX_ARC_SEGMENT = math.pi / 2


class PathError(ValueError):
    """A path string that could not be read as one.

    Raised rather than swallowed: an icon path is a literal in this repo,
    not user input, so a malformed one is a bug that should fail a test
    rather than silently draw nothing.
    """


def tokenize(path_d):
    """Split a path string into command letters and floats, in order."""
    out = []
    for token in _TOKEN.findall(path_d or ""):
        out.append(token if token.isalpha() else float(token))
    return out


def parse(path_d):
    """Parse a path string into drawing operations.

    Supports the subset the icons use — M/L/H/V/C/S/Q/T/A/Z in both cases,
    including SVG's implicit repeat (extra coordinate pairs after a command
    repeat it; extra pairs after a moveto are linetos). Those shorthands are
    what Qt's parser mishandled; they are handled correctly here, which is
    why the icons no longer have to avoid them.
    """
    tokens = tokenize(path_d)
    ops = []
    index = 0
    # Current point, the subpath's start (for Z), and the previous control
    # point, which is what S and T reflect.
    x = y = start_x = start_y = 0.0
    control = None
    command = None
    previous = None
    while index < len(tokens):
        token = tokens[index]
        if isinstance(token, str):
            command = token
            index += 1
            if command in "Zz":
                ops.append(("close",))
                x, y = start_x, start_y
                previous, control = command, None
                continue
        elif command is None:
            raise PathError("path starts with a number: {!r}".format(path_d))
        elif command in "Mm":
            # An implicit repeat after a moveto is a lineto, per the spec.
            command = "L" if command == "M" else "l"
        upper = (command or "").upper()
        count = ARGUMENTS.get(upper)
        if count is None:
            raise PathError("unknown path command {!r} in {!r}".format(
                command, path_d))
        args = tokens[index:index + count]
        if len(args) < count or any(isinstance(a, str) for a in args):
            raise PathError("{!r} wants {} numbers in {!r}".format(
                command, count, path_d))
        index += count
        relative = command.islower()
        if upper == "M":
            x, y = _point(args[0], args[1], x, y, relative)
            start_x, start_y = x, y
            ops.append(("move", x, y))
            control = None
        elif upper == "L":
            x, y = _point(args[0], args[1], x, y, relative)
            ops.append(("line", x, y))
            control = None
        elif upper == "H":
            x = x + args[0] if relative else args[0]
            ops.append(("line", x, y))
            control = None
        elif upper == "V":
            y = y + args[0] if relative else args[0]
            ops.append(("line", x, y))
            control = None
        elif upper in ("C", "S"):
            if upper == "C":
                c1 = _point(args[0], args[1], x, y, relative)
                c2 = _point(args[2], args[3], x, y, relative)
                end = _point(args[4], args[5], x, y, relative)
            else:
                c1 = _reflect(control, x, y, previous, "CS")
                c2 = _point(args[0], args[1], x, y, relative)
                end = _point(args[2], args[3], x, y, relative)
            ops.append(("cubic", c1[0], c1[1], c2[0], c2[1], end[0], end[1]))
            control, (x, y) = c2, end
        elif upper in ("Q", "T"):
            if upper == "Q":
                q = _point(args[0], args[1], x, y, relative)
                end = _point(args[2], args[3], x, y, relative)
            else:
                q = _reflect(control, x, y, previous, "QT")
                end = _point(args[0], args[1], x, y, relative)
            # A quadratic is an exact cubic: the control points sit two
            # thirds of the way from each end towards the quadratic's own.
            c1 = (x + 2.0 * (q[0] - x) / 3.0, y + 2.0 * (q[1] - y) / 3.0)
            c2 = (end[0] + 2.0 * (q[0] - end[0]) / 3.0,
                  end[1] + 2.0 * (q[1] - end[1]) / 3.0)
            ops.append(("cubic", c1[0], c1[1], c2[0], c2[1], end[0], end[1]))
            control, (x, y) = q, end
        else:                                              # A
            end = _point(args[5], args[6], x, y, relative)
            ops.extend(arc_to_cubics(x, y, args[0], args[1], args[2],
                                     args[3], args[4], end[0], end[1]))
            control, (x, y) = None, end
        previous = command
    return tuple(ops)


def _point(dx, dy, x, y, relative):
    return (x + dx, y + dy) if relative else (dx, dy)


def _reflect(control, x, y, previous, allowed):
    """The control point S/T inherit: the last one mirrored, or the point.

    The spec is specific about this — the reflection only applies when the
    previous command was of the matching kind, otherwise the control point
    is the current point.
    """
    if control is None or (previous or " ")[0].upper() not in allowed:
        return (x, y)
    return (2.0 * x - control[0], 2.0 * y - control[1])


def arc_to_cubics(x1, y1, rx, ry, rotation, large_arc, sweep, x2, y2):
    """An elliptical arc as a run of cubic segments (SVG spec, F.6.5).

    Degenerate arcs — either radius zero, or the two endpoints in the same
    place — are a straight line and a no-op respectively, which is what the
    spec says to do and what keeps a typo'd icon from raising.
    """
    if _close(x1, x2) and _close(y1, y2):
        return []
    rx, ry = abs(float(rx)), abs(float(ry))
    if not rx or not ry:
        return [("line", x2, y2)]
    phi = math.radians(float(rotation))
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    # Step 1: the endpoints in the ellipse's own frame, origin at their
    # midpoint.
    dx, dy = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy
    # Step 2: grow radii that are too small to join the endpoints at all.
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1.0:
        scale = math.sqrt(lam)
        rx, ry = rx * scale, ry * scale
    numerator = (rx * rx * ry * ry - rx * rx * y1p * y1p
                 - ry * ry * x1p * x1p)
    denominator = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    factor = math.sqrt(max(numerator / denominator, 0.0)) if denominator else 0.0
    if bool(large_arc) == bool(sweep):
        factor = -factor
    cxp, cyp = factor * rx * y1p / ry, -factor * ry * x1p / rx
    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2.0
    # Step 3: the angles the arc runs between.
    start = _angle(1.0, 0.0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    extent = _angle((x1p - cxp) / rx, (y1p - cyp) / ry,
                    (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and extent > 0:
        extent -= 2.0 * math.pi
    elif sweep and extent < 0:
        extent += 2.0 * math.pi
    steps = max(int(math.ceil(abs(extent) / _MAX_ARC_SEGMENT)), 1)
    step = extent / steps
    # The magic constant that makes a cubic follow a circular arc: the
    # control points sit 4/3 * tan(step/4) of a radius along the tangents.
    alpha = 4.0 / 3.0 * math.tan(step / 4.0)
    out = []
    theta = start
    for _ in range(steps):
        ax, ay = _on_ellipse(cx, cy, rx, ry, cos_phi, sin_phi, theta)
        adx, ady = _tangent(rx, ry, cos_phi, sin_phi, theta)
        theta += step
        bx, by = _on_ellipse(cx, cy, rx, ry, cos_phi, sin_phi, theta)
        bdx, bdy = _tangent(rx, ry, cos_phi, sin_phi, theta)
        out.append(("cubic", ax + alpha * adx, ay + alpha * ady,
                    bx - alpha * bdx, by - alpha * bdy, bx, by))
    if out:
        # End exactly on the commanded point; the trigonometry gets there
        # to within a rounding error and an icon is stroked, not filled, so
        # a gap of 1e-15 would still be a gap.
        last = list(out[-1])
        last[5], last[6] = x2, y2
        out[-1] = tuple(last)
    return out


def _on_ellipse(cx, cy, rx, ry, cos_phi, sin_phi, theta):
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return (cx + rx * cos_t * cos_phi - ry * sin_t * sin_phi,
            cy + rx * cos_t * sin_phi + ry * sin_t * cos_phi)


def _tangent(rx, ry, cos_phi, sin_phi, theta):
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return (-rx * sin_t * cos_phi - ry * cos_t * sin_phi,
            -rx * sin_t * sin_phi + ry * cos_t * cos_phi)


def _angle(ux, uy, vx, vy):
    dot = ux * vx + uy * vy
    length = math.hypot(ux, uy) * math.hypot(vx, vy)
    if not length:
        return 0.0
    angle = math.acos(max(-1.0, min(1.0, dot / length)))
    return -angle if ux * vy - uy * vx < 0 else angle


def _close(a, b, tolerance=1e-9):
    return abs(a - b) <= tolerance


def bounds(paths):
    """(min x, min y, max x, max y) over one path or a sequence of them.

    Control points count, because a stroked curve can bulge past its own
    endpoints. Used by the tests to keep every icon inside its 18x18 box.
    """
    xs, ys = [], []
    for path_d in ((paths,) if isinstance(paths, str) else paths):
        for op in parse(path_d):
            values = op[1:]
            xs.extend(values[0::2])
            ys.extend(values[1::2])
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))
