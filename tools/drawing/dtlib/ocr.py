"""Text on a drawing with pixel boxes: RapidOCR (PaddleOCR PP-OCRv4 det + rec, ONNX) run on upscaled tiles.

Configuration matters more than the engine here (measured on 5 hand-labelled dev drawings, see
docs/features/drawing-tools.md): RapidOCR's defaults shrink any image over 2000 px to 2000 px, so a whole
3072 px sheet is read at 0.65x and small dimension text is lost. Tiles of <= 1600 px upscaled 2x keep it.
"""
from __future__ import annotations
import os
import re
import numpy as np
import cv2

from . import sheet
from .textparse import parse, clean, ARROW_ONLY

_ENGINE = None
VERSION = 2  # bump when read() changes; part of the OCR cache key
_CJK = re.compile(r"[\u3000-\u9fff\uac00-\ud7af]")  # the PP-OCR model is Chinese+English; these sheets are English


def engine():
    global _ENGINE
    if _ENGINE is None:
        os.environ.setdefault("OMP_NUM_THREADS", "4")
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR(max_side_len=4000, min_height=30, width_height_ratio=-1)
    return _ENGINE


def _quad_box(q):
    q = np.asarray(q, float)
    return (q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max())


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0:
        return 0.0, 0.0
    aa = (a[2] - a[0]) * (a[3] - a[1]); bb = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (aa + bb - inter), inter / max(1e-9, min(aa, bb))


def _merge(items):
    """Drop duplicates from tile overlaps: overlapping boxes keep the higher-scoring, longer read."""
    items = sorted(items, key=lambda d: (-(d["score"] * (1 + 0.05 * len(d["raw"])))))
    kept = []
    for d in items:
        dup = False
        for k in kept:
            iou, cont = _iou(d["box"], k["box"])
            if iou > 0.3 or cont > 0.7:
                dup = True
                break
        if not dup:
            kept.append(d)
    return kept


def _same_line(a, b):
    ha, hb = a[3] - a[1], b[3] - b[1]
    h = max(ha, hb)
    return abs((a[1] + a[3]) / 2 - (b[1] + b[3]) / 2) < 0.4 * h and min(ha, hb) > 0.6 * h, h


def _join_text(a, b):
    for k in range(min(len(a), len(b)), 1, -1):
        if a[-k:] == b[:k]:
            return a + b[k:]
    return a.rstrip() + " " + b.lstrip()


def _stitch(items):
    """Join reads of one long line that a tile edge cut: a read cut at a tile edge plus the next read on the
    same line from another tile (which may itself have lost a few characters at its own edge)."""
    items = sorted(items, key=lambda d: d["box"][0])
    used = set()
    out = []
    for i, a in enumerate(items):
        if i in used:
            continue
        cur = dict(a)
        while cur["cut"]:
            best = None
            for j, b in enumerate(items):
                if j in used or j == i or b["tile"] == cur["tile"]:
                    continue
                same, h = _same_line(cur["box"], b["box"])
                if same and b["box"][0] <= cur["box"][2] + h and b["box"][2] > cur["box"][2] + h:
                    best = j; break
            if best is None:
                break
            b = items[best]; used.add(best)
            cur = {"box": (min(cur["box"][0], b["box"][0]), min(cur["box"][1], b["box"][1]),
                           max(cur["box"][2], b["box"][2]), max(cur["box"][3], b["box"][3])),
                   "raw": _join_text(cur["raw"], b["raw"]), "score": min(cur["score"], b["score"]),
                   "cut": b["cut"] and b["box"][2] > cur["box"][2], "tile": b["tile"]}
            cur["quad"] = [[cur["box"][0], cur["box"][1]], [cur["box"][2], cur["box"][1]],
                           [cur["box"][2], cur["box"][3]], [cur["box"][0], cur["box"][3]]]
        out.append(cur)
    return out


_SUFFIX = re.compile(r"^\(?\d+\s*[xX]\)?$|^THRU$|^TYP\.?$|^(\d+\s*)?DEEP$|^ALL\s*AROUND$|^EQ(\.|UALLY)?\s*SP", re.I)
_PREFIX = re.compile(r"^\d+\s*[xX]$")


def _join_callouts(items):
    """'Ø10.00' + '(6X)' and '4X' + 'Ø30' + 'THRU' on one line are one callout; OCR often splits them."""
    items = sorted(items, key=lambda d: d["box"][0])
    changed = True
    while changed:
        changed = False
        for a in items:
            for b in items:
                if a is b or b["box"][0] < a["box"][0]:
                    continue
                same, h = _same_line(a["box"], b["box"])
                gap = b["box"][0] - a["box"][2]
                if same and -h < gap < 3.0 * h and (_SUFFIX.match(b["raw"].strip()) or _PREFIX.match(a["raw"].strip())):
                    a["box"] = (a["box"][0], min(a["box"][1], b["box"][1]), b["box"][2], max(a["box"][3], b["box"][3]))
                    a["raw"] = a["raw"].rstrip() + " " + b["raw"].lstrip()
                    a["score"] = min(a["score"], b["score"])
                    items.remove(b); changed = True
                    break
            if changed:
                break
    return items


_TWO_NUMS = re.compile(r"^(\d+(?:\.\d+)?)(\s+|\s*—+\s*)(\d+(?:\.\d+)?)$")


def _split(items):
    """'31 30' and '135 —100.1' are two adjacent dimensions read as one box: split at the gap."""
    out = []
    for d in items:
        m = _TWO_NUMS.match(clean(d["raw"]))
        b = d["box"]
        if m and b[2] - b[0] > b[3] - b[1]:
            t = clean(d["raw"]); n = len(t)
            xa = b[0] + (b[2] - b[0]) * len(m.group(1)) / n
            xb = b[0] + (b[2] - b[0]) * (len(m.group(1)) + len(m.group(2))) / n
            out.append(dict(d, raw=m.group(1), box=(b[0], b[1], round(xa), b[3])))
            out.append(dict(d, raw=m.group(3), box=(round(xb), b[1], b[2], b[3])))
        else:
            out.append(d)
    return out


def reparse(items):
    """Re-run the parser on cached reads, so a parser change needs no new OCR."""
    out = []
    for d in items:
        p = parse(d["raw"])
        p.update(box=d["box"], score=d["score"], raw=d["raw"], rot=d.get("rot", 0))
        out.append(p)
    return out


def _pass(g, box, upscale, tile, overlap, min_score, box_thresh, unclip_ratio, tid0=0):
    """One OCR pass over `box` of image g in tiles. Boxes in g's coordinates."""
    x0, y0, x1, y1 = box
    eng = engine()
    out = []
    step = max(64, tile - overlap)
    xs = list(range(x0, max(x0 + 1, x1 - overlap), step)) or [x0]
    ys = list(range(y0, max(y0 + 1, y1 - overlap), step)) or [y0]
    tid = tid0
    for ty in ys:
        for tx in xs:
            tid += 1
            bx1, by1 = min(x1, tx + tile), min(y1, ty + tile)
            t = g[ty:by1, tx:bx1]
            if t.size == 0 or t.min() > 200:
                continue
            if upscale != 1:
                t = cv2.resize(t, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
            t3 = cv2.cvtColor(np.ascontiguousarray(t), cv2.COLOR_GRAY2BGR)
            res, _ = eng(t3, box_thresh=box_thresh, unclip_ratio=unclip_ratio, text_score=min_score)
            for q, txt, sc in res or []:
                q = np.asarray(q, float) / upscale + [tx, ty]
                b = _quad_box(q)
                edge = 3  # a read touching an inner tile edge is cut; _stitch joins it with its neighbour
                cut = ((b[0] - tx < edge and tx > x0) or (b[1] - ty < edge and ty > y0)
                       or (bx1 - b[2] < edge and bx1 < x1) or (by1 - b[3] < edge and by1 < y1))
                out.append({"box": tuple(round(v) for v in b), "quad": q.round(1).tolist(), "raw": txt,
                            "score": float(sc), "cut": cut, "tile": tid})
    return _merge(_stitch(out)), tid


def read(gray, box=None, upscale=2.0, tile=1600, overlap=240, min_score=0.5, keep_template=False,
         box_thresh=0.5, unclip_ratio=1.6, vertical=True):
    """OCR a sheet (or the crop `box`). Returns dicts: box (x0,y0,x1,y1 sheet px), raw, score, rot, parsed fields.

    vertical=True adds a pass on the image turned 90 deg clockwise, which reads upward-running dimension text
    as horizontal lines; RapidOCR alone breaks small vertical numbers into single digits.
    """
    g = sheet.normalise(gray)
    if not keep_template:
        g = g.copy(); g[sheet.template_mask(g.shape)] = 255
    if box is None:
        box = sheet.frame_box(g.shape) if not keep_template else (0, 0, g.shape[1], g.shape[0])
    x0, y0, x1, y1 = box
    kw = dict(upscale=upscale, tile=tile, overlap=overlap, min_score=min_score, box_thresh=box_thresh,
              unclip_ratio=unclip_ratio)
    items, tid = _pass(g, box, **kw)
    for d in items:
        d["pass"] = 0
    if vertical:
        sub = g[y0:y1, x0:x1]
        H = sub.shape[0]
        rot = np.rot90(sub, k=-1)  # clockwise: (x, y) -> (H-1-y, x)
        vi, _ = _pass(rot, (0, 0, rot.shape[1], rot.shape[0]), tid0=tid, **kw)
        for d in vi:
            b = d["box"]  # rotated coords -> original: x = y', y = H-1-x'
            d["box"] = (x0 + b[1], y0 + H - 1 - b[2], x0 + b[3], y0 + H - 1 - b[0])
            d["quad"] = [[x0 + q[1], y0 + H - 1 - q[0]] for q in d["quad"]]
            d["pass"] = 90
        # where both passes read the same spot keep one: a multi-character read must run along its pass
        # (wide in pass 0, tall in pass 90); then the longer read wins, then the higher score
        def wide(d):
            b = d["box"]; return (b[2] - b[0]) > 1.3 * (b[3] - b[1])

        def tall(d):
            b = d["box"]; return (b[3] - b[1]) > 1.3 * (b[2] - b[0])

        def plausible(d):
            n = len(clean(d["raw"]).replace(" ", ""))
            return n <= 1 or (not tall(d) if d["pass"] == 0 else not wide(d))

        allr = [d for d in items + vi if plausible(d)]
        allr.sort(key=lambda d: (-len(clean(d["raw"]).replace(" ", "")), -d["score"]))
        kept = []
        for d in allr:
            if any(k["pass"] != d["pass"] and _iou(d["box"], k["box"])[1] > 0.4 for k in kept):
                continue
            kept.append(d)
        keep_h = [d for d in kept if d["pass"] == 0]; keep_v = [d for d in kept if d["pass"] == 90]
        items = keep_h + keep_v
    items = [d for d in items if keep_template or not sheet.in_template(d["box"], g.shape)]
    items = [d for d in items if not ARROW_ONLY.match(d["raw"].strip()) and d["raw"].strip() not in ("O", "o", "0", "()")
             and not _CJK.search(d["raw"])]
    for d in items:
        d["raw"] = clean(d["raw"])
    items = _join_callouts(_split(items))
    res = []
    for d in items:
        q = np.asarray(d["quad"])
        e = q[1] - q[0]
        ang = float(np.degrees(np.arctan2(e[1], e[0])))
        if d.get("pass") == 90:
            ang = -90.0  # reads bottom to top
        p = parse(d["raw"])
        p.update(box=list(d["box"]), score=round(d["score"], 2), raw=d["raw"], rot=round(ang))
        res.append(p)
    res.sort(key=lambda d: (d["box"][1] // 40, d["box"][0]))
    return res
