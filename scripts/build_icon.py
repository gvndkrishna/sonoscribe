"""Rasterize the Sonoscribe mark into AppIcon.icns and menu-bar templates."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
RESOURCES = ROOT / "src" / "sonoscribe" / "resources"
STATIC = ROOT / "src" / "sonoscribe" / "dashboard" / "static"

CANVAS = 512.0
INK = (246 / 255, 248 / 255, 247 / 255, 1.0)
AMBER = (183 / 255, 165 / 255, 106 / 255, 1.0)
PLATE = (15 / 255, 14 / 255, 18 / 255, 1.0)
LEFT = ((134, 352), (92, 336), (90, 288), (134, 268), (178, 248), (176, 198), (134, 182))
RIGHT = ((338, 182), (380, 198), (382, 248), (338, 268), (294, 288), (296, 336), (338, 352))
DASH = ((214, 268), (298, 268))
BAR = (72, 456, 368, 6)

ICONSET_SIZES = (
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
)


def _color(ns, rgba: tuple[float, float, float, float]):
    return ns.NSColor.colorWithCalibratedRed_green_blue_alpha_(*rgba)


def _context(ns, size: int):
    rep = ns.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None,
        size,
        size,
        8,
        4,
        True,
        False,
        ns.NSCalibratedRGBColorSpace,
        0,
        0,
    )
    ns.NSGraphicsContext.saveGraphicsState()
    ctx = ns.NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    ns.NSGraphicsContext.setCurrentContext_(ctx)
    flip = ns.NSAffineTransform.transform()
    flip.translateXBy_yBy_(0, size)
    flip.scaleXBy_yBy_(1, -1)
    flip.concat()
    return rep


def _curve(ns, scale: float, points: tuple, width: float, color) -> None:
    start, c1, c2, mid, c3, c4, end = points
    path = ns.NSBezierPath.bezierPath()
    path.moveToPoint_((start[0] * scale, start[1] * scale))
    path.curveToPoint_controlPoint1_controlPoint2_(
        (mid[0] * scale, mid[1] * scale),
        (c1[0] * scale, c1[1] * scale),
        (c2[0] * scale, c2[1] * scale),
    )
    path.curveToPoint_controlPoint1_controlPoint2_(
        (end[0] * scale, end[1] * scale),
        (c3[0] * scale, c3[1] * scale),
        (c4[0] * scale, c4[1] * scale),
    )
    path.setLineWidth_(width)
    path.setLineCapStyle_(ns.NSRoundLineCapStyle)
    path.setLineJoinStyle_(ns.NSRoundLineJoinStyle)
    color.setStroke()
    path.stroke()


def _dash(ns, scale: float, width: float, color) -> None:
    path = ns.NSBezierPath.bezierPath()
    path.moveToPoint_((DASH[0][0] * scale, DASH[0][1] * scale))
    path.lineToPoint_((DASH[1][0] * scale, DASH[1][1] * scale))
    path.setLineWidth_(width)
    path.setLineCapStyle_(ns.NSButtLineCapStyle)
    color.setStroke()
    path.stroke()


def _finish(ns, rep, path: Path) -> None:
    ns.NSGraphicsContext.restoreGraphicsState()
    data = rep.representationUsingType_properties_(ns.NSBitmapImageFileTypePNG, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    data.writeToFile_atomically_(str(path), True)


def draw_app_icon(ns, size: int, dest: Path) -> None:
    scale = size / CANVAS
    stroke = max(1.25, 6.0 * scale)
    dash = max(1.1, 5.0 * scale)
    rep = _context(ns, size)
    _color(ns, PLATE).setFill()
    ns.NSBezierPath.fillRect_(((0, 0), (size, size)))
    ink = _color(ns, INK)
    amber = _color(ns, AMBER)
    _curve(ns, scale, LEFT, stroke, ink)
    _curve(ns, scale, RIGHT, stroke, ink)
    _dash(ns, scale, dash, amber)
    bar = ns.NSBezierPath.bezierPathWithRect_(
        ((BAR[0] * scale, BAR[1] * scale), (BAR[2] * scale, max(1.0, BAR[3] * scale)))
    )
    amber.setFill()
    bar.fill()
    _finish(ns, rep, dest)


def draw_status(ns, size: int, dest: Path) -> None:
    box = (80.0, 160.0, 352.0, 200.0)
    inner = size * 0.72
    fit = inner / max(box[2], box[3])
    ox = (size - box[2] * fit) / 2 - box[0] * fit
    oy = (size - box[3] * fit) / 2 - box[1] * fit
    rep = _context(ns, size)
    ns.NSColor.clearColor().setFill()
    ns.NSBezierPath.fillRect_(((0, 0), (size, size)))
    shift = ns.NSAffineTransform.transform()
    shift.translateXBy_yBy_(ox, oy)
    shift.scaleBy_(fit)
    shift.concat()
    ink = ns.NSColor.blackColor()
    _curve(ns, 1.0, LEFT, 7.5, ink)
    _curve(ns, 1.0, RIGHT, 7.5, ink)
    _dash(ns, 1.0, 6.0, ink)
    _finish(ns, rep, dest)


def main() -> int:
    try:
        import AppKit as ns
    except ImportError:
        print("AppKit is required to build icons.", file=sys.stderr)
        return 1

    iconset = ASSETS / "AppIcon.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)
    for name, size in ICONSET_SIZES:
        draw_app_icon(ns, size, iconset / name)

    icns = ASSETS / "AppIcon.icns"
    subprocess.run(["iconutil", "-c", "icns", "-o", str(icns), str(iconset)], check=True)
    draw_app_icon(ns, 1024, ASSETS / "AppIcon.png")
    shutil.rmtree(iconset)

    RESOURCES.mkdir(parents=True, exist_ok=True)
    draw_status(ns, 18, RESOURCES / "StatusItem.png")
    draw_status(ns, 36, RESOURCES / "StatusItem@2x.png")
    draw_app_icon(ns, 256, STATIC / "favicon.png")
    shutil.copyfile(ASSETS / "AppIcon.svg", STATIC / "favicon.svg")
    print(f"Wrote {icns.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
