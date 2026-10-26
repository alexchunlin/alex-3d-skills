"""Organic printed connectors: place the things to hold, then grow one smooth solid that grips them.

    from cadlib import blend as B
    holds = [B.Tube((0, 0, 0), (40, 0, 0), 20, wall=4, clearance=0.2, stop=14.2), ...]
    ob, rep = B.grow("node", holds, fillet=6, extra=[B.rod(a, b, 5)], keepout=[envelope_ob], holes=F.screw_hole(...))
    print(B.measure(ob, holds))      # fit clearance and wall per hold, measured on the mesh

How it works:
- Every hold, and every extra primitive, is a signed distance field on a numpy grid.
- A round union joins them with a circular concave fillet of radius `fillet` wherever two grips meet.
- Keep-outs (meshes such as geom.swept_envelope, or fields) are cut with a rounded intersection.
- OpenVDB, which ships inside Blender's Python, extracts the surface.
- Then the interfaces are made exact with Manifold booleans: each hold's cutter (the held object plus its fit
  clearance), the screw holes, the keep-out meshes and the clip box.

So the fit clearances are exact to the cutter's facets, and only the outer skin carries voxel error (about voxel / 10
on flat and round faces). This is motivated by aesthetics capped at 5-6 in all three v1 attempts by "kit of boxes, no
form language" (FINDINGS R2 #10, R3 #4). The measurements and the comparison with Blender's own remesh, volume and
metaball routes are in docs/features/blend-bracket.md.
"""
import math, time
import bpy, bmesh
import numpy as np
from mathutils import Vector, Matrix
from . import geom

try:
    import openvdb as vdb          # bundled with Blender 4+ (5.1.2: OpenVDB 13)
except ImportError:                # pragma: no cover
    vdb = None


# ------------------------------------------------------------------ grid and fields

MAX_CELLS = 40_000_000   # grid cells: grow peaks at 1.63 GB for 36.9M (measured, docs/features/blend-bracket.md)


class GridTooLarge(ValueError):
    pass


# geom.swept_envelope's advice: a coarser voxel is safe there (the pad grows with it), a tighter tol is not a fix
SWEEP_HINT = ("The envelope's pad grows with the voxel (pad = r_max * step / 2 + voxel), so a coarser voxel gives a fatter "
              "keep-out, never a leaky one; don't tighten tol to win the margin back. Or sweep fewer parts or a shorter range")


def check_cells(lo, hi, voxel, max_cells=None, what="grid", hint="Or split the part"):
    """Refuse a grid over max_cells before anything is allocated. The message names the extent, the voxel and the
    smallest voxel that fits, then `hint`. Returns the cell count."""
    max_cells = max_cells or MAX_CELLS
    ext = [float(hi[i] - lo[i]) for i in range(3)]
    n = 1
    for e in ext:
        n *= int(math.ceil(e / voxel)) + 1
    if n > max_cells:
        fit = (ext[0] * ext[1] * ext[2] / max_cells) ** (1 / 3)
        while True:   # the +1 per axis makes the closed form a little optimistic
            m = 1
            for e in ext:
                m *= int(math.ceil(e / fit)) + 1
            if m <= max_cells:
                break
            fit *= 1.02
        raise GridTooLarge("%s: %.0f x %.0f x %.0f mm at voxel %g mm is %.0fM cells (max_cells %.0fM); "
                           "the smallest voxel that fits is %.2f mm. %s, or raise max_cells"
                           % (what, ext[0], ext[1], ext[2], voxel, n / 1e6, max_cells / 1e6, math.ceil(fit * 100) / 100, hint))
    return n

class Grid:
    """Axis-aligned sample grid: origin `lo` (world mm), voxel `h`, `shape` (nx, ny, nz). X, Y, Z broadcast."""

    def __init__(self, lo, hi, h):
        self.h = float(h)
        self.lo = np.array(lo, dtype=np.float64)
        self.shape = tuple(int(math.ceil((hi[i] - lo[i]) / h)) + 1 for i in range(3))
        ax = [(self.lo[i] + self.h * np.arange(self.shape[i])).astype(np.float32) for i in range(3)]   # float32 halves memory
        self.X = ax[0][:, None, None]
        self.Y = ax[1][None, :, None]
        self.Z = ax[2][None, None, :]

    def transform(self):
        h, o = self.h, self.lo
        return vdb.createLinearTransform([[h, 0, 0, 0], [0, h, 0, 0], [0, 0, h, 0], [float(o[0]), float(o[1]), float(o[2]), 1]])

    def local(self, M):
        """Grid coordinates in the frame M (4x4 world-from-local): returns broadcast x, y, z."""
        Mi = Matrix(M).inverted()
        X, Y, Z = self.X, self.Y, self.Z
        return [Mi[i][0] * X + Mi[i][1] * Y + Mi[i][2] * Z + Mi[i][3] for i in range(3)]


class Field:
    """A signed distance field: fn(grid) -> array (negative inside), with world bounds (lo, hi)."""

    def __init__(self, fn, lo, hi, name="field"):
        self.fn, self.lo, self.hi, self.name = fn, Vector(lo), Vector(hi), name

    def __call__(self, g):
        return self.fn(g)


def _seg_frame(a, b):
    a, b = Vector(a), Vector(b)
    w = (b - a).normalized()
    t = Vector((1, 0, 0)) if abs(w.x) < 0.9 else Vector((0, 1, 0))
    u = w.cross(t).normalized()
    v = w.cross(u)
    return geom.frame(a, u, v, w), (b - a).length


def rod(a, b, r, edge=0.0, name="rod"):
    """Solid cylinder of radius r from a to b with flat ends; `edge` rounds the end rims."""
    M, L = _seg_frame(a, b)
    e = min(edge, r * 0.5, L * 0.5)

    def fn(g):
        x, y, z = g.local(M)
        dx = np.sqrt(x * x + y * y) - r + e
        dz = np.abs(z - L / 2) - L / 2 + e
        return np.minimum(np.maximum(dx, dz), 0) + np.sqrt(np.maximum(dx, 0) ** 2 + np.maximum(dz, 0) ** 2) - e
    lo = [min(a[i], b[i]) - r for i in range(3)]
    hi = [max(a[i], b[i]) + r for i in range(3)]
    return Field(fn, lo, hi, name)


def capsule(a, b, r, name="capsule"):
    """Cylinder with hemispherical ends (struts, webs, pegs)."""
    a, b = Vector(a), Vector(b)
    ab = b - a
    L2 = max(ab.length_squared, 1e-12)

    def fn(g):   # Python floats keep the grid's float32
        px, py, pz = g.X - a.x, g.Y - a.y, g.Z - a.z
        t = np.clip((px * ab.x + py * ab.y + pz * ab.z) / L2, 0, 1)
        return np.sqrt((px - t * ab.x) ** 2 + (py - t * ab.y) ** 2 + (pz - t * ab.z) ** 2) - r
    return Field(fn, [min(a[i], b[i]) - r for i in range(3)], [max(a[i], b[i]) + r for i in range(3)], name)


def sphere(c, r, name="sphere"):
    c = Vector(c)
    return Field(lambda g: np.sqrt((g.X - c.x) ** 2 + (g.Y - c.y) ** 2 + (g.Z - c.z) ** 2) - r, c - Vector((r, r, r)), c + Vector((r, r, r)), name)


def _box_sdf(x, y, z, half, r):
    qx, qy, qz = np.abs(x) - half[0] + r, np.abs(y) - half[1] + r, np.abs(z) - half[2] + r
    out = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2)
    return out + np.minimum(np.maximum(np.maximum(qx, qy), qz), 0) - r


def _frame_of(M):
    if M is None:
        return Matrix.Identity(4)
    if len(M) == 3 and not hasattr(M[0], "__len__"):
        return Matrix.Translation(Vector(M))
    return Matrix(M)


def rbox(M, size, r=0.0, name="box"):
    """Box of full `size` (local x, y, z) centred on frame M (a 4x4 from geom.frame, or a centre point); r rounds
    every edge (pads, feet, plates)."""
    M = _frame_of(M)
    half = [s / 2 for s in size]
    r = min(r, min(half))
    corners = [M @ Vector((sx * half[0], sy * half[1], sz * half[2])) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]

    def fn(g):
        x, y, z = g.local(M)
        return _box_sdf(x, y, z, half, r)
    return Field(fn, [min(c[i] for c in corners) for i in range(3)], [max(c[i] for c in corners) for i in range(3)], name)


def mesh_field(ob, band=None, name=None):
    """Signed distance to a closed mesh object (world space), from an OpenVDB level set on the same grid.
    Exact within `band` mm of the surface (default: enough for the caller's offsets), clamped beyond."""
    me = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    me.calc_loop_triangles()
    Mw = ob.matrix_world
    P = np.array([tuple(Mw @ v.co) for v in me.vertices], dtype=np.float32)
    T = np.array([tuple(t.vertices) for t in me.loop_triangles], dtype=np.uint32)
    ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()

    def fn(g, band=band):
        bw = max(3.0, (band or 12.0) / g.h + 2)
        ls = vdb.FloatGrid.createLevelSetFromPolygons(P, triangles=T, transform=g.transform(), halfWidth=bw)
        a = np.empty(g.shape, np.float32)
        ls.copyToArray(a, ijk=(0, 0, 0))
        return a
    return Field(fn, P.min(0), P.max(0), name or ob.name)


def round_union(ds, r):
    """Union with a circular fillet of radius r between any two members (n-ary form of hg_sdf fOpUnionRound)."""
    if r <= 0:
        return np.minimum.reduce(ds)
    m = np.minimum.reduce(ds)
    s = np.zeros_like(m)
    for d in ds:
        s += np.maximum(r - d, 0) ** 2
    return np.maximum(m, r) - np.sqrt(s)


def round_intersect(a, b, r):
    """Intersection with a convex round of radius r on the new edge (hg_sdf fOpIntersectionRound)."""
    if r <= 0:
        return np.maximum(a, b)
    return np.minimum(np.maximum(a, b), -r) + np.sqrt(np.maximum(r + a, 0) ** 2 + np.maximum(r + b, 0) ** 2)


# ------------------------------------------------------------------ holds

def _nseg_exact(r, sag=0.01):
    """Facets for a cutter whose flats stay within `sag` mm of the round: fits stay exact to 0.01 mm."""
    return int(max(48, math.ceil(math.pi / math.acos(max(-1.0, 1 - sag / r)))))


class Tube:
    """Grip a round tube or rod of diameter d whose axis runs from a to b (b is the open mouth).

    The grip is a sleeve of wall `wall` from a to b. `clearance` is radial: the bore is d + 2 * clearance, so the
    default 0.2 is a 0.4 mm diametral fit (features.RULES["fit_loose"]). `stop`: the tube end sits this far from a (a
    blind socket, the rest of the sleeve toward a stays solid). None means the bore runs through both ends. `edge`
    rounds the sleeve rims, `lead_in` chamfers the mouth for insertion. `print_up`: world direction of print +Z; a bore
    within 60 deg of horizontal in print becomes a teardrop pointing up (as features.screw_hole does), its point cut flat
    to keep RULES["min_wall"] above it, and measure() skips the rays into the point. The socket holds the tube by fit only: retain it with a screw through the sleeve
    (`holes=features.screw_hole(...)`) or glue. name: default tube0, tube1, ... in grow() order."""

    def __init__(self, a, b, d, wall=4.0, clearance=0.2, stop=None, edge=1.0, lead_in=0.5, print_up=None, name=None):
        self.a, self.b, self.d = Vector(a), Vector(b), float(d)
        self.wall, self.clearance, self.stop, self.edge, self.lead_in = wall, clearance, stop, edge, lead_in
        self.name, self._auto = name or "tube", name is None
        self.M, self.L = _seg_frame(a, b)
        self.r_bore = d / 2 + clearance
        self.r_out = self.r_bore + wall
        self.up = None   # print +Z in the tube's local (u, v) plane, when the bore is a teardrop
        if print_up is not None and abs((self.b - self.a).normalized().dot(Vector(print_up).normalized())) < 0.5:
            up = self.M.to_3x3().inverted() @ Vector(print_up)
            self.up = Vector((up.x, up.y)).normalized()

    def field(self):
        return rod(self.a, self.b, self.r_out, self.edge, self.name)

    def cutters(self):
        n = _nseg_exact(self.r_bore)
        z0 = -1.0 if self.stop is None else self.stop
        if self.up is not None:
            cut = [geom.prism(self.name + "_bore", self.teardrop(n), z0, self.L + 1.0, 'Z')]
        else:
            cut = [geom.cyl(self.name + "_bore", (0, 0), self.r_bore, z0, self.L + 1.0, 'Z', n=n)]
        if self.lead_in > 0:
            li = self.lead_in
            cut.append(geom.cone(self.name + "_lead", (0, 0), self.r_bore, self.r_bore + li + 1.0, self.L - li, self.L + 1.0, 'Z', n=n))
            if self.stop is None:
                cut.append(geom.cone(self.name + "_lead0", (0, 0), self.r_bore + li + 1.0, self.r_bore, -1.0, li, 'Z', n=n))
        return [geom.xform(c, self.M) for c in cut]

    def teardrop(self, n):
        """geom.teardrop's bore profile, with the point cut flat where it would leave less than RULES["min_wall"] of
        sleeve above it (r * sqrt(2) = 14.4 > 14.2 for a 20 mm tube in a 4 mm wall: a slot along the top)."""
        from .features import RULES
        prof = geom.teardrop((0, 0), self.r_bore, tuple(self.up), n)
        top = min(self.r_bore * math.sqrt(2), self.r_out - RULES["min_wall"])
        ux, uy = self.up
        out = []
        for i, a in enumerate(prof):                  # clip the convex profile to (p . up) <= top
            b = prof[(i + 1) % len(prof)]
            da, db = a[0] * ux + a[1] * uy - top, b[0] * ux + b[1] * uy - top
            if da <= 1e-9:
                out.append(a)
            if (da < -1e-9 < db) or (db < -1e-9 < da):
                t = da / (da - db)
                out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
        return out

    def stations(self):
        """Axial positions (from a) where the grip is a plain sleeve: away from the stop, the rims and the lead-in."""
        z0 = (0.0 if self.stop is None else self.stop) + 1.0 + (self.lead_in + self.edge if self.stop is None else 0)
        z1 = self.L - self.edge - self.lead_in - 1.0
        n = max(2, int((z1 - z0) / 2.0) + 1)
        return [z0 + (z1 - z0) * i / (n - 1) for i in range(n)]

    def probe(self, tree, n_ang=24):
        """Radial rays from the tube axis: clearance = first hit - d/2; wall = material from there to the next face."""
        u, v, w = (Vector(self.M.col[i][:3]) for i in range(3))
        clr, wall = [], []
        for z in self.stations():
            p = self.a + w * z
            for k in range(n_ang):
                t = 2 * math.pi * (k + 0.5) / n_ang
                if self.up is not None and math.cos(t) * self.up.x + math.sin(t) * self.up.y > 0.70:
                    continue   # into the teardrop's point: not a fit surface
                dr = u * math.cos(t) + v * math.sin(t)
                hit = tree.ray_cast(p, dr, 200.0)
                if hit[0] is None:
                    clr.append(None)
                    continue
                clr.append(hit[3] - self.d / 2)
                h2 = tree.ray_cast(hit[0] + dr * 1e-3, dr, 200.0)
                wall.append(h2[3] + 1e-3 if h2[0] is not None else None)
        return clr, wall


class Block:
    """Grip a box-shaped part (servo body, PCB edge, battery) of full `size` centred on frame M (4x4 or centre).

    The grip is the box grown by clearance + wall (rounded with radius wall), limited to the local region
    `grip` = ((x0, y0, z0), (x1, y1, z1)) when given. The cutter is the box plus clearance, run out through every face
    named in `open` ('+z', '-x', ...) so the part can drop in and its connectors stay free. clearance is per side.
    name: default block0, block1, ... in grow() order."""

    def __init__(self, M, size, wall=2.4, clearance=0.2, grip=None, open=("+z",), edge=1.0, name=None):
        self.M = _frame_of(M)
        self.size, self.wall, self.clearance, self.grip, self.open, self.edge = size, wall, clearance, grip, open, edge
        self.name, self._auto = name or "block", name is None
        self.half = [s / 2 for s in size]

    def field(self):
        M, half, c, w = self.M, self.half, self.clearance, self.wall
        H = [x + c for x in half]
        grip = self.grip

        def fn(g):
            x, y, z = g.local(M)
            d = _box_sdf(x, y, z, H, 0.0) - w
            if grip is not None:
                lo, hi = Vector(grip[0]), Vector(grip[1])
                cen, gh = (lo + hi) / 2, (hi - lo) / 2
                d = round_intersect(d, _box_sdf(x - cen.x, y - cen.y, z - cen.z, gh, 0.0), self.edge)
            return d
        corners = [M @ Vector((sx * (H[0] + w), sy * (H[1] + w), sz * (H[2] + w))) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        return Field(fn, [min(p[i] for p in corners) for i in range(3)], [max(p[i] for p in corners) for i in range(3)], self.name)

    def cutters(self):
        c, run = self.clearance, 200.0
        lo = [-h - c for h in self.half]
        hi = [h + c for h in self.half]
        for o in self.open:
            i = "xyz".index(o[1])
            if o[0] == "+":
                hi[i] += run
            else:
                lo[i] -= run
        return [geom.xform(geom.box(self.name + "_cut", lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]), self.M)]

    def probe(self, tree):
        """Rays along each closed local axis from the body centre (moved into the grip region): clearance = hit - half
        size; wall = material beyond it."""
        clr, wall = [], []
        Mr = self.M.to_3x3()
        c = Vector((0, 0, 0))
        if self.grip is not None:
            c = Vector([max(-h, min(h, (self.grip[0][i] + self.grip[1][i]) / 2)) for i, h in enumerate(self.half)])
        for i in range(3):
            for sgn in (-1, 1):
                if ("+" if sgn > 0 else "-") + "xyz"[i] in self.open:
                    continue
                dr = Mr @ Vector([sgn if j == i else 0 for j in range(3)])
                o = c.copy()
                o[i] = 0.0
                hit = tree.ray_cast(self.M @ o, dr.normalized(), 500.0)
                if hit[0] is None:
                    clr.append(None)
                    continue
                clr.append(hit[3] - self.half[i])
                h2 = tree.ray_cast(hit[0] + dr.normalized() * 1e-3, dr.normalized(), 500.0)
                wall.append(h2[3] + 1e-3 if h2[0] is not None else None)
        return clr, wall


# ------------------------------------------------------------------ meshing

def vdb_to_object(grid_or_arr, name, iso=0.0, adaptivity=0.0, g=None):
    """Isosurface of an OpenVDB FloatGrid (or a dense array on Grid g) as a closed Blender mesh object."""
    if isinstance(grid_or_arr, np.ndarray):
        vg = vdb.FloatGrid(float(np.max(np.abs(grid_or_arr))))
        vg.copyFromArray(np.ascontiguousarray(grid_or_arr, dtype=np.float32), ijk=(0, 0, 0), tolerance=0)
        vg.transform = g.transform()
    else:
        vg = grid_or_arr
    pts, tris, quads = vg.convertToPolygons(float(iso), float(adaptivity))
    faces = [tuple(t) for t in tris.tolist()] + [tuple(q) for q in quads.tolist()]
    me = bpy.data.meshes.new(name)
    me.from_pydata(pts.tolist(), [], faces)
    me.validate(clean_customdata=False)
    ob = bpy.data.objects.new(name, me)
    geom.scratch().objects.link(ob)
    nm, vol = geom.solid_stats(ob)
    if vol < 0:
        me.flip_normals()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    return ob


def tri_count(ob):
    ob.data.calc_loop_triangles()
    return len(ob.data.loop_triangles)


def skin(name, fields, fillet=5.0, keepout=(), keepout_clear=0.5, keepout_edge=1.0, clip=None, voxel=0.5,
         adaptivity=0.0, bias=0.0, max_tris=None, max_cells=None):
    """The blended outer solid only (no exact cuts): round union of `fields`, keep-outs cut, meshed by OpenVDB.
    bias moves the surface outward (mm), e.g. to pay back the inward chord error of adaptivity or decimation.
    Raises GridTooLarge, before allocating, when the grid would exceed max_cells (default MAX_CELLS).
    Returns (object, report dict)."""
    assert vdb is not None, "openvdb is not available in this Blender"
    t0 = time.time()
    lo = Vector([min(f.lo[i] for f in fields) for i in range(3)])
    hi = Vector([max(f.hi[i] for f in fields) for i in range(3)])
    pad = fillet + 3 * voxel
    lo, hi = lo - Vector((pad, pad, pad)), hi + Vector((pad, pad, pad))
    if clip is not None:
        m = 3 * voxel
        lo = Vector([max(lo[i], clip[0][i] - m) for i in range(3)])
        hi = Vector([min(hi[i], clip[1][i] + m) for i in range(3)])
    cells = check_cells(lo, hi, voxel, max_cells, "blend.skin(%s)" % name)
    g = Grid(lo, hi, voxel)
    # streamed round union: two arrays live at a time, however many members there are
    m = s = None
    for f in fields:
        d = f(g)
        m = d if m is None else np.minimum(m, d, out=m)
        t = np.maximum(fillet - d, 0) if fillet > 0 else None
        if t is not None:
            t *= t
            s = t if s is None else np.add(s, t, out=s)
        del d, t
    d = m if fillet <= 0 else np.subtract(np.maximum(m, fillet, out=m), np.sqrt(s, out=s), out=m)
    del m, s
    for k in keepout:
        f = k if isinstance(k, Field) else mesh_field(k, band=keepout_clear + keepout_edge + 3 * voxel)
        d = round_intersect(d, keepout_clear - f(g), keepout_edge)
    # close the grid boundary so the isosurface is a closed solid even where the field runs past the box
    d[0, :, :] = d[-1, :, :] = voxel
    d[:, 0, :] = d[:, -1, :] = voxel
    d[:, :, 0] = d[:, :, -1] = voxel
    t_field = time.time() - t0
    ob = vdb_to_object(d, name, bias, adaptivity, g)
    del d
    tris = tri_count(ob)
    if max_tris and tris > max_tris:
        m = ob.modifiers.new("dec", 'DECIMATE')
        m.ratio = max_tris / tris
        m.use_collapse_triangulate = True
        geom.apply_mods(ob)
    nm, vol = geom.solid_stats(ob)
    return ob, {"voxel": voxel, "grid": list(g.shape), "cells_M": round(cells / 1e6, 1), "fillet": fillet, "adaptivity": adaptivity, "bias": bias,
                "skin_tris_raw": tris, "skin_tris": tri_count(ob), "skin_non_manifold": nm,
                "t_field_s": round(t_field, 2), "t_mesh_s": round(time.time() - t0 - t_field, 2)}


def _name_holds(holds):
    """Number unnamed holds (tube0, tube1, block0, ...) and refuse duplicate names: measure() reports by name, and two
    holds called "tube" used to come back as one row."""
    count, seen = {}, set()
    for h in holds:
        if getattr(h, "_auto", False):
            base = type(h).__name__.lower()
            h.name, h._auto = "%s%d" % (base, count.get(base, 0)), False   # named once: measure() sees grow()'s names
            count[base] = count.get(base, 0) + 1
    for h in holds:
        if h.name in seen:
            raise ValueError("blend: two holds are named %r; give each hold its own name (measure() reports by name)" % h.name)
        seen.add(h.name)
    return holds


def grow(name, holds=(), fillet=5.0, extra=(), keepout=(), keepout_clear=0.5, keepout_edge=1.0, clip=None, holes=(),
         voxel=0.5, adaptivity=0.0, bias=0.02, max_tris=40000, max_cells=None):
    """Grow one smooth printed solid around `holds` (Tube, Block) and `extra` fields (rod, capsule, rbox, sphere).

    fillet:      concave fillet radius between every pair of members
    keepout:     mesh objects (e.g. geom.swept_envelope) or fields; material stays keepout_clear mm away, with a
                 keepout_edge round on the cut. The meshes are also subtracted exactly at the end (they are copied,
                 so the caller keeps them).
    clip:        ((x0, y0, z0), (x1, y1, z1)) world box, intersected exactly at the end: flat bed faces, exact
                 lengths. The field runs past it, so the clip cuts solid material.
    holes:       extra exact cutters, e.g. features.screw_hole(...) lists
    voxel:       grid step (mm); time and memory grow as 1 / voxel^3
    max_tris:    collapse-decimate the skin past this many triangles. On the node, 168k -> 33k triangles kept the
                 arm radius within 0.02 mm (docs/features/blend-bracket.md).
    bias:        moves the skin out (mm) so walls stay at or above spec after meshing and decimation (+0.016 mm on
                 the node with 0.02). adaptivity (OpenVDB, 0..1) is cheaper but flattens round arms: 0.05 cost 0.21 mm.
    max_cells:   dense grid limit (default MAX_CELLS = 40M; 36.9M peaked at 1.63 GB). Over it, GridTooLarge is raised before
                 anything is allocated, naming the smallest voxel that fits. It does not coarsen silently.
    Returns (object, report dict). The report is also stored on the object as ob["blend"], and the tube rims and clip
    faces as ob["blend_orient"], the default candidates of best_orientation()."""
    t0 = time.time()
    _name_holds(holds)
    ob, rep = skin(name, [h.field() for h in holds] + list(extra), fillet, keepout, keepout_clear, keepout_edge, clip,
                   voxel, adaptivity, bias, max_tris, max_cells)
    sub = []
    for h in holds:
        sub += h.cutters()
    sub += list(holes)
    for k in keepout:
        if not isinstance(k, Field):
            c = k.copy()
            c.data = k.data.copy()
            c.data.transform(k.matrix_world)
            c.matrix_world = Matrix.Identity(4)
            c.parent = None
            geom.scratch().objects.link(c)
            sub.append(c)
    inter = []
    if clip is not None:
        (x0, y0, z0), (x1, y1, z1) = clip
        inter.append(geom.box(name + "_clip", x0, x1, y0, y1, z0, z1))
    t1 = time.time()
    geom.csg(ob, sub=sub, inter=inter)
    nm, vol = geom.solid_stats(ob)
    rep.update(tris=tri_count(ob), non_manifold_edges=nm, volume_mm3=round(vol, 1), t_csg_s=round(time.time() - t1, 2),
               t_total_s=round(time.time() - t0, 2))
    ob["blend"] = str(rep)
    return ob, rep


class Points(Grid):
    """Evaluate fields at arbitrary points: Points(list of (x, y, z)) quacks like a Grid."""

    def __init__(self, pts):
        P = np.asarray(pts, dtype=np.float64).reshape(-1, 3)
        self.X, self.Y, self.Z = P[:, 0], P[:, 1], P[:, 2]
        self.h, self.lo, self.shape = 0.0, P.min(0) if len(P) else np.zeros(3), (len(P),)


def field_at(fields, pts, fillet=0.0):
    """Round-union value of `fields` at points (signed mm: negative inside)."""
    P = Points(pts)
    return round_union([f(P) for f in fields], fillet)


def overhang(ob, R, deg=45.0):
    """(sloped overhang mm2 steeper than `deg`, flat bed contact mm2) with print rotation R: cadcheck's parts formula,
    for choosing the print orientation of an organic part before registering it."""
    R = Matrix(R).to_3x3()
    vs = [R @ (ob.matrix_world @ v.co) for v in ob.data.vertices]
    zmin = min(v.z for v in vs)
    ob.data.calc_loop_triangles()
    cos_o = math.cos(math.radians(deg))
    over = bed = 0.0
    for t in ob.data.loop_triangles:
        a, b, c = (vs[i] for i in t.vertices)
        n = (b - a).cross(c - a)
        A = n.length / 2
        if A < 1e-9:
            continue
        n.normalize()
        zc = (a.z + b.z + c.z) / 3 - zmin
        if n.z < -0.999 and zc < 0.05:
            bed += A
        elif n.z < -cos_o - 1e-3 and zc > 0.25:
            over += A
    return round(over, 1), round(bed, 1)


def measure(ob, holds):
    """Fit clearance and wall around each hold, by rays on the finished mesh. Returns {hold name: {...}}."""
    from mathutils.bvhtree import BVHTree
    me = ob.data
    Mw = ob.matrix_world
    tree = BVHTree.FromPolygons([Mw @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    out = {}
    for h in _name_holds(holds):
        clr, wall = h.probe(tree)
        cl = [c for c in clr if c is not None]
        wl = [w for w in wall if w is not None]
        spec = h.clearance
        out[h.name] = {"spec_clearance": spec, "clearance_min": round(min(cl), 3) if cl else None,
                       "clearance_max": round(max(cl), 3) if cl else None, "rays": len(clr), "missed": len(clr) - len(cl),
                       "wall_spec": h.wall, "wall_min": round(min(wl), 3) if wl else None,
                       "fit_ok": bool(cl) and len(cl) == len(clr) and max(abs(c - spec) for c in cl) <= 0.05}
    return out
