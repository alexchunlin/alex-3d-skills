"""Load a drawing, normalise faint ink, mask the fixed CADGenBench sheet template, parse crop boxes."""
from __future__ import annotations
import numpy as np
from PIL import Image

# The CADGenBench A2 sheet (3072 x 2118 px) is pixel-identical across all 39 dev drawings
# (checked 2026-10-27: every pixel inked in >= 38 of 39 lies on the frame or the title block).
BASE_W, BASE_H = 3072, 2118
FRAME = (166, 122, 2920, 2038)        # drawing area, inside the inner frame line
TITLE = (1554, 1460, 2922, 2040)      # title block + the fixed notes left of it


def load_gray(path) -> np.ndarray:
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im)
    return np.asarray(im.convert("L"))


def is_cgb(shape) -> bool:
    """The CADGenBench sheet template only applies to images with its aspect ratio."""
    return abs(shape[1] / shape[0] - BASE_W / BASE_H) < 0.01 and shape[1] >= 1000


def _scale_box(b, shape):
    sx, sy = shape[1] / BASE_W, shape[0] / BASE_H
    return (int(b[0] * sx), int(b[1] * sy), int(b[2] * sx), int(b[3] * sy))


def frame_box(shape):
    if not is_cgb(shape):
        return (0, 0, shape[1], shape[0])
    return _scale_box(FRAME, shape)


def template_mask(shape) -> np.ndarray:
    """True on the sheet template: outside the frame, and the title block."""
    m = np.ones(shape[:2], bool)
    x0, y0, x1, y1 = frame_box(shape)
    m[y0:y1, x0:x1] = False
    if is_cgb(shape):
        tx0, ty0, tx1, ty1 = _scale_box(TITLE, shape)
        m[ty0:ty1, tx0:tx1] = True
    return m


def in_template(box, shape) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    x0, y0, x1, y1 = frame_box(shape)
    if not (x0 <= cx <= x1 and y0 <= cy <= y1):
        return True
    if not is_cgb(shape):
        return False
    tx0, ty0, tx1, ty1 = _scale_box(TITLE, shape)
    return tx0 <= cx <= tx1 and ty0 <= cy <= ty1


def levels(gray: np.ndarray):
    """(paper, ink) grey levels of the drawing area. Faint drawings have ink at ~190 instead of ~0."""
    x0, y0, x1, y1 = frame_box(gray.shape)
    v = gray[y0:y1, x0:x1][~template_mask(gray.shape)[y0:y1, x0:x1]]
    paper = float(np.percentile(v, 50))
    dark = v[v < paper - 20]
    ink = float(np.percentile(dark, 20)) if dark.size > 100 else 0.0
    return paper, ink


def normalise(gray: np.ndarray) -> np.ndarray:
    """Stretch so paper -> 255 and typical ink -> 0 (no-op on the usual black-ink sheets)."""
    paper, ink = levels(gray)
    if paper - ink < 10:
        return gray.copy()
    out = (gray.astype(np.float32) - ink) * (255.0 / (paper - ink))
    return np.clip(out, 0, 255).astype(np.uint8)


def ink_mask(gray: np.ndarray, frac: float = 0.3) -> np.ndarray:
    """Binary ink: darker than paper - frac * (paper - ink)."""
    paper, ink = levels(gray)
    return gray < paper - max(frac * (paper - ink), 12)


def parse_box(s, shape=None):
    if s is None:
        return None
    v = [int(round(float(t))) for t in str(s).replace(" ", "").split(",")]
    if len(v) != 4:
        raise SystemExit(f"box must be x0,y0,x1,y1 (got {s!r})")
    x0, y0, x1, y1 = min(v[0], v[2]), min(v[1], v[3]), max(v[0], v[2]), max(v[1], v[3])
    if shape is not None:
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(shape[1], x1), min(shape[0], y1)
    return (x0, y0, x1, y1)


def parse_pt(s):
    v = [float(t) for t in str(s).replace(" ", "").split(",")]
    if len(v) != 2:
        raise SystemExit(f"point must be x,y (got {s!r})")
    return (v[0], v[1])
