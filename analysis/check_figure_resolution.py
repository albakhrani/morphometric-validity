#!/usr/bin/env python3
"""
Report the effective resolution of every raster image EMBEDDED in each figure.

check_figure_type.py measures type size and will happily pass a figure that is
too coarse to print. This is the companion check. A matplotlib PDF is vector,
but any imshow / pcolormesh / rasterized artist inside it is a raster XObject,
and that XObject is what the printer sees.

The number that matters is not the dpi the PNG was saved at, nor the dpi tag in
the file. It is

    effective dpi = image pixel width / (placed width on the page in inches)

so it depends on the artwork size, on the raster's extent WITHIN the artwork,
and on the scale LaTeX applies when placing the artwork at \\textwidth. Widening
the text measure lowers it.

Content streams are walked with a real q/Q/cm graphics-state stack, so the
placed size is the true CTM at the `Do` operator rather than the page box.

    python check_figure_resolution.py                 # all figures here
    python check_figure_resolution.py --width 526.38  # at a different measure
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import zlib
from pathlib import Path

# Both measured from the compiled documents, not read off the class sources.
VENUE = {"cas": (494.51, 234.88),
         "oup": (526.376, 254.652)}

SINGLE_COLUMN: set[str] = {"Fig4_envelope"}
UNUSED: set[str] = {"Fig4_envelope"}

FLOOR = 300.0             # dpi; both Elsevier and OUP specify this for halftone
FLOOR_LINEART = 600.0     # for pure line art; not applied, recorded for context


def objects(data: bytes) -> dict[str, tuple[bytes, bytes]]:
    """Object number -> (dictionary bytes, raw stream bytes or b'').

    Built by slicing on real `N 0 obj` headers rather than searching outward
    from each `stream` keyword. The outward search misattributes object
    numbers whenever a dictionary contains a digit before the header, which
    silently decouples the name->object map from the image table.
    """
    out: dict[str, tuple[bytes, bytes]] = {}
    hdr = re.compile(rb"(?<![0-9])(\d+)\s+(\d+)\s+obj\b")
    pos = 0
    while True:
        m = hdr.search(data, pos)
        if not m:
            return out
        num = m.group(1).decode()
        e = data.find(b"endobj", m.end())
        s = re.compile(rb"stream\r?\n").search(data, m.end(),
                       e if e > 0 else len(data))
        if not s:
            out[num] = (data[m.end():e if e > 0 else None], b"")
            pos = (e + 6) if e > 0 else m.end()
            continue
        d = data[m.end():s.start()]
        # Use /Length rather than scanning for `endstream`: a megabyte of image
        # data can contain bytes that look like `N 0 obj` or `endstream`, and
        # scanning through it splits objects at the wrong offsets.
        #
        # /Length is very often an INDIRECT reference (`/Length 12 0 R`). It
        # must be resolved, not skipped -- matching `(\d+)` with a negative
        # lookahead lets the regex backtrack onto the first digit of `12` and
        # return a length of 1, which truncates the stream to nothing.
        ln = re.search(rb"/Length\s+(\d+)\s+(\d+)\s+R", d)
        n = None
        if ln:
            tgt = data[:0]
            mm = re.search(rb"(?<![0-9])" + ln.group(1) + rb"\s+0\s+obj\s*"
                           rb"(\d+)", data)
            if mm:
                n = int(mm.group(1))
        else:
            direct = re.search(rb"/Length\s+(\d+)\s*(?:/|>>)", d)
            if direct:
                n = int(direct.group(1))
        if n is not None and s.end() + n <= len(data):
            stop = s.end() + n
        else:
            stop = data.find(b"endstream", s.end())
            stop = stop if stop > 0 else len(data)
        out[num] = (d, data[s.end():stop])
        pos = stop
    return out


def inflate(raw: bytes) -> str:
    for attempt in (lambda: zlib.decompress(raw),
                    lambda: zlib.decompressobj().decompress(raw),
                    lambda: raw):
        try:
            return attempt().decode("latin-1")
        except Exception:
            continue
    return ""


def image_xobjects(objs: dict[str, tuple[bytes, bytes]]
                   ) -> dict[str, tuple[int, int, str]]:
    """Map PDF object number -> (pixel width, pixel height, filter)."""
    imgs = {}
    for num, (d, _) in objs.items():
        if b"/Subtype" not in d or b"/Image" not in d:
            continue
        w = re.search(rb"/Width\s+(\d+)", d)
        h = re.search(rb"/Height\s+(\d+)", d)
        f = re.search(rb"/Filter\s*/?(\w+)", d)
        if w and h:
            imgs[num] = (int(w.group(1)), int(h.group(1)),
                         f.group(1).decode() if f else "none")
    return imgs


def name_to_object(objs: dict[str, tuple[bytes, bytes]]) -> dict[str, str]:
    """Resource-name (/I1) -> object number, from every /XObject dict.

    matplotlib writes /XObject as an INDIRECT reference (`/XObject 7 0 R`),
    not an inline dictionary. Handling only the inline form finds no images
    and reports a rasterised figure as fully vector -- a false pass, which is
    the one outcome this check exists to prevent. Both forms are resolved.
    """
    out = {}
    for num, (d, _) in objs.items():
        for m in re.finditer(rb"/XObject\s*<<(.*?)>>", d, re.S):
            for n, o in re.findall(rb"/(\w+)\s+(\d+)\s+0\s+R", m.group(1)):
                out[n.decode()] = o.decode()
        for m in re.finditer(rb"/XObject\s+(\d+)\s+0\s+R", d):
            tgt = objs.get(m.group(1).decode())
            if tgt:
                for n, o in re.findall(rb"/(\w+)\s+(\d+)\s+0\s+R", tgt[0]):
                    out[n.decode()] = o.decode()
    return out


NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)"
# Case-SENSITIVE. PDF `q` (push) and `Q` (pop) are different operators; a
# case-insensitive match makes the first alternative swallow both, the stack
# never pops, and the CTM compounds until it overflows.
OPS = re.compile(
    rf"(?P<a>{NUM})\s+(?P<b>{NUM})\s+(?P<c>{NUM})\s+(?P<d>{NUM})\s+"
    rf"{NUM}\s+{NUM}\s+(?P<cm>cm)\b"
    rf"|(?P<q>\bq\b)|(?P<Q>\bQ\b)|/(?P<name>\w+)\s+(?P<do>Do)\b")


def content_streams(objs: dict[str, tuple[bytes, bytes]]) -> list[str]:
    """Decompressed payload of every object named by a page /Contents.

    Restricted deliberately: a font or ICC stream decoded as latin-1 can
    contain byte sequences that look like operators, which produces nonsense
    matrices rather than an error.
    """
    wanted: set[str] = set()
    for _, (d, _) in objs.items():
        for m in re.finditer(rb"/Contents\s+(\d+)\s+0\s+R", d):
            wanted.add(m.group(1).decode())
        for m in re.finditer(rb"/Contents\s*\[(.*?)\]", d, re.S):
            wanted |= {n.decode()
                       for n in re.findall(rb"(\d+)\s+0\s+R", m.group(1))}
    return [inflate(objs[n][1]) for n in wanted if n in objs and objs[n][1]]


def placed_images(objs: dict[str, tuple[bytes, bytes]]
                  ) -> list[tuple[str, float, float]]:
    """(resource name, placed width in pt, placed height in pt) per `Do`."""
    hits = []
    for s in content_streams(objs):
        ctm = [1.0, 0.0, 0.0, 1.0]
        stack: list[list[float]] = []
        for m in OPS.finditer(s):
            if m.group("q"):
                stack.append(list(ctm))
            elif m.group("Q"):
                if stack:
                    ctm = stack.pop()
            elif m.group("cm"):
                a, b, c, d = (float(m.group(k)) for k in "abcd")
                # 2x2 part only; translation does not affect extent
                ctm = [ctm[0] * a + ctm[2] * b, ctm[1] * a + ctm[3] * b,
                       ctm[0] * c + ctm[2] * d, ctm[1] * c + ctm[3] * d]
            elif m.group("do"):
                w = (ctm[0] ** 2 + ctm[1] ** 2) ** 0.5
                h = (ctm[2] ** 2 + ctm[3] ** 2) ** 0.5
                hits.append((m.group("name"), w, h))
    return hits


def tiff_width(path: Path) -> int:
    """Pixel width of a TIFF or PNG, without requiring Pillow.

    TIFF: read the IFD and pull tag 256 (ImageWidth). PNG: bytes 16-20 of
    the IHDR. Parsed directly for the same reason /MediaBox is -- a check
    that cannot run in a clean environment is a check that silently passes.
    """
    d = path.read_bytes()
    if d[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(d[16:20], "big")
    if d[:2] not in (b"II", b"MM"):
        raise SystemExit(f"{path}: not a TIFF or PNG")
    end = "little" if d[:2] == b"II" else "big"
    off = int.from_bytes(d[4:8], end)
    n = int.from_bytes(d[off:off + 2], end)
    for i in range(n):
        e = off + 2 + i * 12
        if int.from_bytes(d[e:e + 2], end) == 256:          # ImageWidth
            typ = int.from_bytes(d[e + 2:e + 4], end)
            raw = d[e + 8:e + 12]
            return int.from_bytes(raw[:2] if typ == 3 else raw, end)
    raise SystemExit(f"{path}: no ImageWidth tag")


def page_width(path: Path) -> float:
    """Artwork width in pt, from /MediaBox. Parsed directly so the check does
    not depend on pdfinfo being on PATH."""
    data = path.read_bytes()
    m = re.search(rb"/MediaBox\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+"
                  rb"([-\d.]+)\s+([-\d.]+)", data)
    if not m:
        raise SystemExit(f"cannot read /MediaBox of {path}")
    return float(m.group(3)) - float(m.group(1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("figures", nargs="*")
    ap.add_argument("--venue", choices=sorted(VENUE), default="oup")
    ap.add_argument("--width", type=float, default=None,
                    help="override the text measure in pt")
    a = ap.parse_args()
    tw, cw = VENUE[a.venue]
    if a.width:
        cw, tw = cw * a.width / tw, a.width
    a.width = tw

    here = Path(__file__).parent
    targets = ([Path(p) for p in a.figures] or
               sorted(p for p in here.glob("*.pdf")
                      if p.name not in {"COMPILED_PREVIEW.pdf", "main.pdf"}))

    print(f"text measure: {a.width:.2f} pt   floor: {FLOOR:.0f} dpi at placed size")
    print(f"{'figure':24s} {'artwork':>8s} {'scale':>6s} {'raster':>13s} "
          f"{'placed in':>10s} {'eff dpi':>8s}  verdict")
    print("-" * 92)
    bad = 0

    # A flat raster has no artwork box and no vector content: the whole file
    # IS the image, so effective dpi is pixel width over placed width. This
    # branch exists because the checker's numbers only describe the format
    # actually submitted -- measuring the PDF master says nothing about a
    # TIFF exported from it.
    flat = [p for p in targets if p.suffix.lower() in {".tif", ".tiff",
                                                       ".png"}]
    for p in flat:
        targets.remove(p)
        px = tiff_width(p)
        placed = cw if p.stem in SINGLE_COLUMN else a.width
        inches = placed / 72.0
        dpi = px / inches
        verdict = "ok" if dpi >= FLOOR else "FAIL  below 300 dpi"
        if dpi < FLOOR:
            bad += 1
        print(f"{p.stem:24s} {'raster':>8s} {'--':>6s} {f'{px}px':>13s} "
              f"{inches:9.2f}\" {dpi:8.0f}  {verdict}"
              f"  [{p.suffix.lstrip('.')}]")

    for p in targets:
        try:
            aw = page_width(p)
        except SystemExit:
            continue
        placed = cw if p.stem in SINGLE_COLUMN else a.width
        scale = placed / aw
        objs = objects(p.read_bytes())
        imgs = image_xobjects(objs)
        names = name_to_object(objs)
        rows = []
        for nm, wpt, hpt in placed_images(objs):
            obj = names.get(nm)
            if obj is None or obj not in imgs:
                continue           # a form XObject, not an image
            px, py, filt = imgs[obj]
            inches = wpt * scale / 72.0
            rows.append((px, py, inches, px / inches if inches else 0, filt))
        if not rows:
            # The guard. "No raster placed" and "the parser failed to find the
            # raster" look identical in the output, and only one of them is
            # good news. If the file carries image XObjects, silence is a bug.
            if imgs:
                print(f"{p.stem:24s} {aw:8.1f} {scale:6.3f} {'?':>13s} "
                      f"{'-':>10s} {'-':>8s}  ERROR  {len(imgs)} image "
                      f"XObject(s) present but none located in a content "
                      f"stream -- parser bug, do not trust this line")
                bad += 1
                continue
            print(f"{p.stem:24s} {aw:8.1f} {scale:6.3f} {'none':>13s} "
                  f"{'-':>10s} {'-':>8s}  ok  fully vector")
            continue
        worst = min(rows, key=lambda r: r[3])
        px, py, inches, dpi, filt = worst
        verdict = "ok" if dpi >= FLOOR else "FAIL  below 300 dpi"
        if dpi < FLOOR:
            bad += 1
        if p.stem in UNUSED:
            verdict += "   (not used by body.tex)"
        extra = f"  [{len(rows)} rasters]" if len(rows) > 1 else ""
        print(f"{p.stem:24s} {aw:8.1f} {scale:6.3f} {f'{px}x{py}':>13s} "
              f"{inches:9.2f}\" {dpi:8.0f}  {verdict}{extra}")
    print("-" * 92)
    print("FAIL count:", bad)
    if flat:
        print("NOTE: type size cannot be measured on a flattened raster --")
        print("      there are no text objects left to read. Run")
        print("      check_figure_type.py on the PDF master instead. The")
        print("      raster inherits that type only if it was exported at a")
        print("      dpi high enough to resolve it, which is what the dpi")
        print("      column above is for.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
