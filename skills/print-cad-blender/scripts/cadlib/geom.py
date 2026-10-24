"""Closed-solid primitives and Manifold booleans for headless Blender (5.1+). Units: mm.

Lifted from the mm-launcher attempt-1 designer's helper layer (HW/blender/build_assembly.py:146-415),
which produced 35 manifold printed parts on the first try once the Manifold solver was used
(docs/FINDINGS.md "What worked"). Rewriting this layer cost that designer ~270 lines of generation.

Every function returns a new mesh object linked to a scratch collection. Build parts from
prisms/revolves/lofts, combine with csg(), then hand the result to cadlib.asm.part().
2D profiles are lists of (u, v) tuples; `axis` names the extrusion axis ('X', 'Y' or 'Z') and
(u, v, w) map to (y, z, x) for 'X', (x, z, y) for 'Y' and (x, y, z) for 'Z'.
"""
import bpy, bmesh, math
from mathutils import Vector, Matrix

_TMP = None


def scratch():
    """Scratch collection for intermediate solids (survives scene resets)."""
    global _TMP
    try:
        ok = _TMP is not None and _TMP.name in bpy.data.collections
    except ReferenceError:
        ok = False
    if not ok:
        _TMP = bpy.data.collections.get("TMP") or bpy.data.collections.new("TMP")
        if _TMP.name not in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.link(_TMP)
    return _TMP


def _map(u, v, w, axis):
    if axis == 'Z':
        return (u, v, w)
    if axis == 'X':
        return (w, u, v)
    if axis == 'Y':
        return (u, w, v)
    raise ValueError(axis)


def _obj(name, bm):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    scratch().objects.link(ob)
    return ob


# ------------------------------------------------------------------ 2D profiles

def nseg(r):
    """Segment count for a circle of radius r: ~0.4 mm chord error, 16..128."""
    return int(max(16, min(128, round(r * 2.4))))


def circle(c, r, n=None, a0=0.0):
    n = n or nseg(r)
    return [(c[0] + r * math.cos(a0 + 2 * math.pi * i / n), c[1] + r * math.sin(a0 + 2 * math.pi * i / n)) for i in range(n)]


def arc(c, r, a0, a1, n=None):
    n = n or max(4, int(abs(a1 - a0) / (2 * math.pi) * nseg(r)))
    return [(c[0] + r * math.cos(a0 + (a1 - a0) * i / n), c[1] + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def hexagon(c, af, a0=0.0):
    """Hexagon by across-flats width (nut traps: af = 5.5 + clearance for M3)."""
    r = af / 2 / math.cos(math.pi / 6)
    return circle(c, r, 6, a0)


def rrect(x0, x1, y0, y1, r, n=6):
    r = min(r, (x1 - x0) / 2 - 1e-3, (y1 - y0) / 2 - 1e-3)
    pts = []
    for (cx, cy, a) in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(n + 1):
            t = math.radians(a + 90 * i / n)
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


def hull2d(pts):
    pts = sorted(set((round(x, 6), round(y, 6)) for x, y in pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 1e-9:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 1e-9:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def hull_circles(circs, n=72):
    """Convex hull of circles [(c, r), ...]: rounded plates, bosses joined to walls."""
    pts = []
    for (c, r) in circs:
        pts += circle(c, r, max(12, int(n * r / 40) + 12)) if r > 0 else [c]
    return hull2d(pts)


def teardrop(c, r, up=(0, 1)):
    """Hole profile printable without support when its axis is horizontal: 45 deg point toward `up`
    (the print +Z direction expressed in the profile's (u, v) plane)."""
    ang = math.atan2(up[1], up[0])
    pts = [p for p in circle(c, r, 32, 0)
           if (p[0] - c[0]) * math.cos(ang) + (p[1] - c[1]) * math.sin(ang) <= r * math.sin(math.radians(45)) + 1e-6]
    pts.append((c[0] + r * math.sqrt(2) * math.cos(ang), c[1] + r * math.sqrt(2) * math.sin(ang)))
    return hull2d(pts)


def offset_convex(poly, d):
    """Offset a convex CCW polygon by d (negative shrinks); exact for convex shapes."""
    n = len(poly)
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(poly[i - 1]), Vector(poly[i]), Vector(poly[(i + 1) % n])
        e0, e1 = (p1 - p0).normalized(), (p2 - p1).normalized()
        n0, n1 = Vector((e0.y, -e0.x)), Vector((e1.y, -e1.x))
        b = (n0 + n1)
        if b.length < 1e-9:
            b = n0
        b.normalize()
        k = d / max(0.2, b.dot(n0))
        out.append(tuple(p1 + b * k))
    return out


def gear_poly(m, z, c=(0, 0), backlash=0.15, phase=0.0, n_inv=7, pressure_deg=20.0):
    """Involute spur gear outline: module m, z teeth, backlash in mm at the pitch circle."""
    rp = m * z / 2
    ra = rp + m
    rf = rp - 1.25 * m
    alpha = math.radians(pressure_deg)
    rb = rp * math.cos(alpha)
    inv = lambda a: math.tan(a) - a
    half_p = math.pi / (2 * z) - backlash / (2 * rp)
    pts = []
    r_start = max(rb, rf)
    for k in range(z):
        th = phase + 2 * math.pi * k / z
        flank = []
        for i in range(n_inv + 1):
            r = r_start + (ra - r_start) * i / n_inv
            a = math.acos(min(1.0, rb / r))
            flank.append((r, half_p + inv(alpha) - inv(a)))
        a_root = flank[0][1]
        pts.append((rf, th - a_root - 0.25 * (2 * math.pi / z - 2 * a_root)))
        if rf < r_start:
            pts.append((rf, th - a_root))
        for r, a in flank:
            pts.append((r, th - a))
        for r, a in reversed(flank):
            pts.append((r, th + a))
        if rf < r_start:
            pts.append((rf, th + a_root))
        pts.append((rf, th + a_root + 0.25 * (2 * math.pi / z - 2 * a_root)))
    return [(c[0] + r * math.cos(a), c[1] + r * math.sin(a)) for r, a in pts]


# ------------------------------------------------------------------ solids

def loft(name, poly0, poly1, w0, w1, axis='Z'):
    """Closed solid between two same-count rings at w0 and w1."""
    assert len(poly0) == len(poly1), "loft rings need the same point count"
    bm = bmesh.new()
    vb = [bm.verts.new(_map(p[0], p[1], w0, axis)) for p in poly0]
    vt = [bm.verts.new(_map(p[0], p[1], w1, axis)) for p in poly1]
    n = len(vb)
    bm.faces.new(vb[::-1])
    bm.faces.new(vt)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((vb[i], vb[j], vt[j], vt[i]))
    return _obj(name, bm)


def prism(name, poly, w0, w1, axis='Z'):
    return loft(name, poly, poly, w0, w1, axis)


def cyl(name, c, r, w0, w1, axis='Z', n=None, a0=0.0):
    return prism(name, circle(c, r, n, a0), w0, w1, axis)


def cone(name, c, r0, r1, w0, w1, axis='Z', n=None):
    n = n or nseg(max(r0, r1))
    return loft(name, circle(c, r0, n), circle(c, r1, n), w0, w1, axis)


def box(name, x0, x1, y0, y1, z0, z1):
    return prism(name, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1, 'Z')


def revolve(name, prof, center=(0, 0, 0), n=96, a0=0.0, a1=None):
    """Revolve a closed (r, z) profile about the Z axis through center. Partial when a1 is given."""
    bm = bmesh.new()
    full = a1 is None
    steps = n if full else max(2, int(n * abs(a1 - a0) / (2 * math.pi)))
    rings = []
    for i in range(steps if full else steps + 1):
        t = a0 + (2 * math.pi * i / n if full else (a1 - a0) * i / steps)
        rings.append([bm.verts.new((center[0] + r * math.cos(t), center[1] + r * math.sin(t), center[2] + z)) for r, z in prof])
    m = len(prof)
    nr = len(rings)
    for i in range(nr if full else nr - 1):
        A, B = rings[i], rings[(i + 1) % nr]
        for k in range(m):
            kk = (k + 1) % m
            bm.faces.new((A[k], A[kk], B[kk], B[k]))
    if not full:
        bm.faces.new(rings[0])
        bm.faces.new(rings[-1][::-1])
    return _obj(name, bm)


def apply_mods(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear()
    old = ob.data
    ob.data = me
    bpy.data.meshes.remove(old)
    return ob


def kill(ob):
    me = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)


class CSGError(RuntimeError):
    pass


def csg(base, add=(), sub=(), inter=(), check=True):
    """Union `add`, subtract `sub`, intersect `inter` with the Manifold solver; apply; delete the tools.
    Raises CSGError if the result is empty or not a closed solid (check=False to skip)."""
    tools = []
    for op, lst in (('UNION', add), ('DIFFERENCE', sub), ('INTERSECT', inter)):
        for t in lst:
            if t is None:
                continue
            m = base.modifiers.new("b", 'BOOLEAN')
            m.operation = op
            m.solver = 'MANIFOLD'
            m.object = t
            tools.append(t)
    apply_mods(base)
    for t in tools:
        kill(t)
    if check:
        nm, vol = solid_stats(base)
        if vol <= 0 or nm:
            raise CSGError("%s: csg result not a closed solid (non-manifold edges %d, volume %.2f)" % (base.name, nm, vol))
    return base


def solid_stats(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    vol = bm.calc_volume(signed=True)
    bm.free()
    return nm, vol


def bevel(ob, w, seg=1, angle=40.0):
    """Edge break on every edge sharper than `angle`. Do it before booleans that cut fine detail:
    bevelling after booleans is fragile (attempt-1 finding)."""
    m = ob.modifiers.new("bev", 'BEVEL')
    m.width = w
    m.segments = seg
    m.limit_method = 'ANGLE'
    m.angle_limit = math.radians(angle)
    m.use_clamp_overlap = True
    return apply_mods(ob)


def xform(ob, M):
    """Bake a 4x4 transform into the mesh data (objects stay at identity until parented)."""
    ob.data.transform(M)
    ob.data.update()
    return ob


def frame(origin, u, v, w):
    """4x4 matrix whose columns are the local axes u, v, w placed at origin."""
    M = Matrix.Identity(4)
    for i in range(3):
        M[i][0], M[i][1], M[i][2], M[i][3] = u[i], v[i], w[i], origin[i]
    return M


def join(name, obs):
    """Merge shells without booleans (purchased placeholders only; printed parts need csg)."""
    bm = bmesh.new()
    for o in obs:
        bm.from_mesh(o.data)
    for o in obs:
        kill(o)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    scratch().objects.link(ob)
    return ob


def import_stl(path, name):
    """Import an STL (mm) as a single object named `name`, linked to the scratch collection."""
    before = set(bpy.data.objects)
    bpy.ops.wm.stl_import(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    ob = new[0]
    for o in new[1:]:
        kill(o)
    ob.name = name
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    scratch().objects.link(ob)
    return ob
