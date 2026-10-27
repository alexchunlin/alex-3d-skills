"""Render-and-diff: a candidate part's orthographic edges at the drawing's scale, matched against a view crop
under all 8 flips / quarter turns, so a mirrored or rotated reading of the view shows up as a better match.

Edges come from a painter's-algorithm raster of the tessellated part (face normal + depth per pixel): a pixel is
an edge where the normal turns by more than 30 deg, the depth jumps, or the part meets the background. That is
what a drawing's visible lines are (outline, creases, hole rims), with hidden lines left out.
"""
from __future__ import annotations
import math
import struct
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from scipy.signal import fftconvolve

# cadgenbench.common.camera_presets: direction from the part toward the camera, and the up vector (Z up)
PRESETS = {
    "front": ((0, -1, 0), (0, 0, 1)), "rear": ((0, 1, 0), (0, 0, 1)),
    "left": ((-1, 0, 0), (0, 0, 1)), "right": ((1, 0, 0), (0, 0, 1)),
    "top": ((0, 0, 1), (0, 1, 0)), "bottom": ((0, 0, -1), (0, -1, 0)),
}
# 8 symmetries of the square, as maps of image coords (u right, v down) about the centre
TRANSFORMS = [
    ("as modelled", lambda u, v: (u, v)),
    ("rotated 90 CW", lambda u, v: (-v, u)),
    ("rotated 180", lambda u, v: (-u, -v)),
    ("rotated 90 CCW", lambda u, v: (v, -u)),
    ("mirrored left-right", lambda u, v: (-u, v)),
    ("mirrored top-bottom", lambda u, v: (u, -v)),
    ("mirrored on the \\ diagonal", lambda u, v: (v, u)),
    ("mirrored on the / diagonal", lambda u, v: (-v, -u)),
]


def _ax(v):
    v = np.round(np.asarray(v, float), 3)
    names = {(1, 0, 0): "+X", (-1, 0, 0): "-X", (0, 1, 0): "+Y", (0, -1, 0): "-Y", (0, 0, 1): "+Z", (0, 0, -1): "-Z"}
    return names.get(tuple(int(x) if float(x).is_integer() else x for x in v), "(" + ",".join(f"{x:g}" for x in v) + ")")


def fix_hint(view, ti):
    """What to do to the model so it reads like the drawing, for transform index ti in this view."""
    d, up, right = _basis(view)
    D, U, R = _ax(d), _ax(up), _ax(right)
    diag1 = _ax((right + up) / math.sqrt(2)); diag2 = _ax((right - up) / math.sqrt(2))
    return {
        0: "",
        1: f"rotate the part -90 deg about {D} (clockwise as seen in this view)",
        2: f"rotate the part 180 deg about {D}",
        3: f"rotate the part +90 deg about {D} (counter-clockwise as seen in this view)",
        4: f"turn the part over: 180 deg about {U} (then its other side faces this view), or mirror it across the plane normal to {R} if the other views already match",
        5: f"turn the part over: 180 deg about {R} (then its other side faces this view), or mirror it across the plane normal to {U} if the other views already match",
        6: f"turn the part over: 180 deg about the in-view diagonal {diag2}, or mirror it",
        7: f"turn the part over: 180 deg about the in-view diagonal {diag1}, or mirror it",
    }[ti]


def load_mesh(path, tol=None):
    """(V, F) in mm from a STEP (build123d tessellation) or a binary/ASCII STL."""
    p = str(path)
    if p.lower().endswith((".stl",)):
        data = open(p, "rb").read()
        if data[:5].lower() == b"solid" and b"facet" in data[:400]:
            vs = [tuple(map(float, l.split()[1:4])) for l in data.decode(errors="ignore").splitlines()
                  if l.strip().startswith("vertex")]
            V = np.array(vs, float)
        else:
            n = struct.unpack("<I", data[80:84])[0]
            a = np.frombuffer(data[84:84 + n * 50], dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
            V = a["v"].reshape(-1, 3).astype(float)
        return V, np.arange(len(V)).reshape(-1, 3)
    from build123d import import_step
    shape = import_step(p)
    bb = shape.bounding_box()
    tol = tol or max(0.01, min(0.2, 0.001 * bb.diagonal))
    vs, tris = shape.tessellate(tol, 0.2)
    V = np.array([(v.X, v.Y, v.Z) for v in vs], float)
    return V, np.array(tris, int)


def _basis(view):
    if isinstance(view, str):
        d, up = PRESETS[view]
    else:
        d, up = view
    d = np.asarray(d, float); d /= np.linalg.norm(d)
    up = np.asarray(up, float); up = up - d * (up @ d); up /= np.linalg.norm(up)
    right = np.cross(-d, up)  # camera looks along -d
    return d, up, right


def render_edges(V, F, view, s, crease_deg=30.0, depth_mm=None):
    """Edge image (bool) of the part seen from `view` at s px/mm, plus its silhouette and the image of the
    part's bbox centre. 1 px = 1/s mm."""
    d, up, right = _basis(view)
    P = V @ np.c_[right, up, d]          # u = right, w = up, z = toward camera
    u = P[:, 0] * s; w = -P[:, 1] * s; z = P[:, 2]
    pad = 4
    u0, w0 = u.min() - pad, w.min() - pad
    W = int(math.ceil(u.max() - u0 + pad)); H = int(math.ceil(w.max() - w0 + pad))
    if W * H > 36e6:
        raise SystemExit(f"overlay: rendered view would be {W}x{H} px; check --scale (px/mm) and the model units (mm)")
    tri = F
    pu, pw, pz = u[tri] - u0, w[tri] - w0, z[tri]
    n = np.cross(V[tri[:, 1]] - V[tri[:, 0]], V[tri[:, 2]] - V[tri[:, 0]])
    nl = np.linalg.norm(n, axis=1); ok = nl > 1e-12
    n[ok] /= nl[ok, None]
    order = np.argsort(pz.mean(1))        # far to near
    nid = Image.new("I", (W, H), 0)       # face index + 1
    dimg = Image.new("F", (W, H), float(z.min() - 1))
    dn, dd = ImageDraw.Draw(nid), ImageDraw.Draw(dimg)
    for k in order:
        if not ok[k]:
            continue
        poly = [(pu[k, 0], pw[k, 0]), (pu[k, 1], pw[k, 1]), (pu[k, 2], pw[k, 2])]
        dn.polygon(poly, fill=int(k) + 1)
        dd.polygon(poly, fill=float(pz[k].mean()))
    ids = np.asarray(nid, np.int64); dep = np.asarray(dimg, np.float32)
    sil = ids > 0
    N = np.zeros((len(F) + 1, 3)); N[1:] = n
    nm = N[ids]
    cosmax = math.cos(math.radians(crease_deg))
    edge = np.zeros_like(sil)
    dz = depth_mm if depth_mm is not None else max(0.5, 3.0 / s)
    for sh in ((0, 1), (1, 0)):
        a = (slice(None, -sh[0] or None), slice(None, -sh[1] or None))
        b = (slice(sh[0], None), slice(sh[1], None))
        both = sil[a] & sil[b]
        turn = (nm[a] * nm[b]).sum(-1) < cosmax
        jump = np.abs(dep[a] - dep[b]) > dz
        e = (sil[a] != sil[b]) | (both & (turn | jump))
        edge[a] |= e
    centre = ((-u0 + 0.0), (-w0 + 0.0))  # image position of the model origin
    return edge, sil, centre


def _transform_points(pts, T, shape):
    """Apply transform T to edge pixel coords about the image centre; return integer coords in a new frame."""
    H, W = shape
    u = pts[:, 1] - (W - 1) / 2; v = pts[:, 0] - (H - 1) / 2
    a, b = T(u, v)
    return np.c_[b, a]  # (row, col) relative to centre


def match(edge, ink, scales=(0.97, 0.985, 1.0, 1.015, 1.03), tol_px=2):
    """Best translation for each transform x scale by FFT correlation of model edges with dilated drawing ink.
    Returns list of dicts sorted by score: transform, scale, shift (row, col of model centre in the crop),
    precision (model edge px near ink), recall (ink px near model edges, inside the model's footprint), f."""
    near_ink = ndimage.binary_dilation(ink, iterations=tol_px)
    ink_d = ndimage.distance_transform_edt(~ink)
    pts = np.argwhere(edge).astype(float)
    res = []
    for ti, (name, T) in enumerate(TRANSFORMS):
        rel0 = _transform_points(pts, T, edge.shape)
        for sc in scales:
            rel = np.round(rel0 * sc).astype(int)
            rmin = rel.min(0); size = rel.max(0) - rmin + 1
            k = np.zeros(size, np.float32)
            k[rel[:, 0] - rmin[0], rel[:, 1] - rmin[1]] = 1
            npx = k.sum()
            corr = fftconvolve(near_ink.astype(np.float32), k[::-1, ::-1], mode="full")
            idx = np.unravel_index(int(np.argmax(corr)), corr.shape)
            prec = float(corr[idx] / npx)
            # top-left of kernel in crop coords
            top = idx[0] - (size[0] - 1); left = idx[1] - (size[1] - 1)
            rr = rel[:, 0] - rmin[0] + top; cc = rel[:, 1] - rmin[1] + left
            inside = (rr >= 0) & (cc >= 0) & (rr < ink.shape[0]) & (cc < ink.shape[1])
            # recall: drawing ink inside the model's bbox that lies within tol of a model edge
            r0, r1 = max(0, top), min(ink.shape[0], top + size[0]); c0, c1 = max(0, left), min(ink.shape[1], left + size[1])
            mimg = np.zeros(ink.shape, bool); mimg[rr[inside], cc[inside]] = True
            near_model = ndimage.binary_dilation(mimg[r0:r1, c0:c1], iterations=tol_px)
            win = ink[r0:r1, c0:c1]
            rec = float((win & near_model).sum() / max(1, win.sum()))
            mean_d = float(ink_d[rr[inside], cc[inside]].clip(0, 10).mean()) if inside.any() else 99.0
            f = 2 * prec * rec / max(1e-9, prec + rec)
            res.append({"transform": name, "ti": ti, "scale": sc, "top_left": (int(top), int(left)),
                        "precision": prec, "recall": rec, "f": f, "mean_px": mean_d,
                        "pts": (rr[inside], cc[inside])})
    res.sort(key=lambda r: -r["f"])
    return res


def best_per_transform(res):
    seen = {}
    for r in res:
        if r["ti"] not in seen:
            seen[r["ti"]] = r
    return [seen[k] for k in sorted(seen, key=lambda k: -seen[k]["f"])]


_FONT = "/Users/alxchunlin/code-stuff/alex-style-guide/fonts/RobotoMono-400.ttf"


def draw(crop_gray, ink, ident, best, path, title):
    """Light-mode overlay (alex-style series 1 blue = as modelled, series 2 red = best other reading)."""
    H, W = ink.shape
    img = np.full((H, W, 3), 255, np.uint8)
    img[ink] = (170, 170, 166)

    def paint(r, rgb):
        m = np.zeros((H, W), bool); m[r["pts"][0], r["pts"][1]] = True
        img[ndimage.binary_dilation(m)] = rgb
    if best is not None and best is not ident:
        paint(best, (0xE3, 0x24, 0x1B))
    paint(ident, (0x1F, 0x4F, 0xD8))
    im = Image.fromarray(img)
    band = 22 * (3 if best is not None and best is not ident else 2)
    out = Image.new("RGB", (W, H + band), (255, 255, 255)); out.paste(im, (0, band))
    d = ImageDraw.Draw(out)
    try:
        f = ImageFont.truetype(_FONT, 14)
    except OSError:
        f = ImageFont.load_default()
    d.text((6, 3), title, fill=(11, 11, 11), font=f)
    d.rectangle((6, 27, 16, 37), fill=(0x1F, 0x4F, 0xD8))
    d.text((22, 24), f"as modelled  f {ident['f']:.3f}  scale x{ident['scale']:.3f}", fill=(11, 11, 11), font=f)
    if best is not None and best is not ident:
        d.rectangle((6, 49, 16, 59), fill=(0xE3, 0x24, 0x1B))
        d.text((22, 46), f"{best['transform']}  f {best['f']:.3f}  scale x{best['scale']:.3f}", fill=(11, 11, 11), font=f)
    out.save(path)
