"""Cable router: occupancy grid from the solids, A* with wall, exposure and turn costs, then line-of-sight
shortcuts and bend-radius fillets. The points go straight into asm.cable(name, pts, r, ..., lead_len=), so
cadcheck's cable checks (overlap, exposure, lead length) apply to the result.

    from cadlib import route as RT
    obs, res = RT.cable("CAB_bus", a, b, 1.4, "cable_wht", via=[...])     # route + asm.cable, one object per body
    res = RT.route(a, b, 1.6, via=[(0, 20, 30)], clearance=1.0)            # one body (no "joint" via): one piece
    A.cable("CAB_12v_ctrl", res["pts"], 1.6, "cable_red", lead_len=200)  # res["pts"] only when len(res["pieces"]) == 1
    cad q model.blend route CAB_12v_ctrl --config checks.json --save out.blend   # re-route an existing cable

A route split by a "joint" via has one piece per body: build each piece on its joint (RT.cable does), not res["pts"].
Full reference: ../../reference/route.md.

Why: every v1 attempt had cable review issues (FINDINGS A1-F12 routes, A2-F8 bare run, A3-F7 visible in a notch),
and hand-typed waypoints put 165.6 mm3 of five A3 cables inside solids (CAB_uart 113.4, CAB_12v_ctrl 38.0 in
BUY_servo_controller; cadcheck's 1331.9 for the latter was an open-tube boolean artefact, docs/features/cable-router.md).

Model:
- Grid: cells of `cell` mm over the leg's endpoints plus `margin`. A cell is blocked when a solid surface is closer
  than r + clearance (BVH find_nearest) or the cell is inside a solid (per-object column ray parity). Solids on
  another body are swept over the joints between the two bodies (revolute in degrees, prismatic in mm, posed by
  cadlib.joints exactly as cadcheck poses them). Each joint is sampled finely enough that a point at the moving
  side's reach r_max moves at most r + clearance per step (sweep_tol = half that between samples), capped per joint,
  and the swept solids are inflated by the largest move between samples, so the route clears them at every pose,
  not only at the sampled ones (PR #3 review: scenes `wedge`, `pantilt`, `slide`).
- Search: A* over 26 neighbours. Cost per mm: 1 within `wall_band` of the blocked band or in a `prefer` box,
  1 + w_open in open space, plus w_exposed where the cell is visible from outside (cadcheck's viewer-direction
  rule on a 2-cell lattice), plus w_turn mm per radian of turn.
- Vias: points the cable must pass. {"at": p, "dir": d, "len": L} forces a straight run (a hub bore, a slot), and
  "joint" (a PIV name, or "static") puts the legs after it on another body; the result then has one piece per body,
  a slack row and a crossing row (the cable's turn at the via at each joint limit; warned above 30 deg).
- Guard: the result is sampled every 0.5 mm against exact clearance; every sample away from the two ends that is
  under the requested clearance is listed in `violations` (straight runs and via stubs included) and printed.
- Smoothing: shortcuts checked against exact clearance that never enter costlier cells than the A* path used,
  then a fillet of bend_r at each corner, shrunk (or the corner pushed outward) where the arc would lose
  clearance. The smallest radius used is reported as bend_r_min. No arc is tighter than cadcheck's kink limit
  (min_bend_od x OD), and an end within 3 mm of a purchased part (a plug) keeps one OD straight: a corner that
  can't have both is left sharp, so cadcheck's `cables` kink test (which skips turns under 20 deg, i.e. every
  vertex of an arc drawn in 10 deg steps) still sees it.
"""
import bpy, heapq, json, math, time
import numpy as np
from mathutils import Vector, Matrix, Euler
from mathutils.bvhtree import BVHTree
from . import joints as JT

DEFAULTS = {"cell": 2.0, "clearance": 1.0, "margin": 20.0, "bend_r": None, "wall_band": None, "lead_in": None,
            "w_open": 0.5, "w_exposed": 8.0, "w_turn": 3.0, "w_stub": 3.0,
            "sweep_tol": None,          # largest move of a swept solid between two sampled poses; None: (r + clearance) / 2
            "max_joint_poses": 96,      # samples per joint, at most (the inflation grows when this caps the step)
            "max_group_poses": 1024,    # runtime guard for 2+ joints in a chain: thins the joint whose inflation is least
            "fold_warn_deg": 30.0,      # warn when the cable turns more than this at a joint crossing at a limit
            "view_frac": 0.10, "view_z": -0.2, "min_escape": 8, "prefer": [], "avoid": [], "exposure": True,
            "min_bend_od": 0.75}   # cadcheck cable_min_bend_od
OBSTACLES = ("Printed", "Purchased", "Fasteners")
VIEWERS = ("Printed", "Purchased")      # what hides a cable (cadcheck exposure uses the same two)


# ------------------------------------------------------------------ scene

def mesh_objs(colls):
    out = []
    for c in colls:
        col = bpy.data.collections.get(c)
        if col:
            out += [o for o in col.all_objects if o.type == 'MESH']
    return out


is_joint = JT.is_joint


def chain(o):
    """Joint ancestors of o (an object, a PIV name or None for static), nearest first."""
    if isinstance(o, str):
        o = bpy.data.objects.get(o) if o != "static" else None
    out, p = [], (o if is_joint(o) else (o.parent if o is not None else None))
    while p is not None:
        if is_joint(p):
            out.append(p.name)
        p = p.parent
    return out


def body(o):
    ch = chain(o)
    return ch[0] if ch else "static"


def scene_joints(cfg=None):
    """(joints, couplings) the way cadcheck reads them (cadlib.joints): PIV props, then the config's joints/couplings."""
    return JT.read(None, cfg)


def set_pose(pose, J, CP):
    """cadcheck's set_pose (cadlib.joints.apply): revolute joints in degrees, prismatic ones in mm."""
    JT.apply(J, CP, pose)


def drivers(names, CP):
    out = set()
    for n in names:
        while n in CP:
            n = CP[n]["to"]
        out.add(n)
    return frozenset(out)


def _driver_of(n, CP):
    """(driver, ratio): the free joint behind n and how far n moves per unit of it."""
    k = 1.0
    while n in CP:
        k *= float(CP[n]["ratio"])
        n = CP[n]["to"]
    return n, k


def _motion(j, J):
    """(kind, pivot, unit direction) of joint j's motion at the current pose, measured by nudging the empty (so a
    base rotation or a parent's frame is accounted for exactly as set_pose moves it)."""
    s, e = J[j], bpy.data.objects[j]
    m0 = e.matrix_world.copy()
    vl = bpy.context.view_layer
    if s.get("kind") == "prismatic":
        old = e.location.copy()
        ax = Vector([1.0 if i == "XYZ".index(s["axis"]) else 0.0 for i in range(3)])
        e.location = old + Euler(s["base_rot"]).to_matrix() @ ax
        vl.update()
        d = e.matrix_world.translation - m0.translation
        e.location = old
        vl.update()
        return "prismatic", m0.translation.copy(), d.normalized() if d.length > 1e-9 else Vector((0, 0, 1))
    old = e.rotation_euler.copy()
    r = list(old)
    r["XYZ".index(s["axis"])] += math.radians(1.0)
    e.rotation_euler = r
    vl.update()
    R = e.matrix_world.to_3x3().normalized() @ m0.to_3x3().normalized().inverted()
    e.rotation_euler = old
    vl.update()
    return "revolute", m0.translation.copy(), R.to_quaternion().axis.normalized()


def _ranged(j, J, CP):
    """Joint j moves: it has an axis and its driver has a range (a coupled gear follows its driver's)."""
    d = J.get(_driver_of(j, CP)[0]) or {}
    return bool((J.get(j) or {}).get("axis") and d.get("axis") and (d.get("continuous") or d.get("lo") is not None))


def _travel(s):
    if s.get("lo") is None:
        return 0.0
    h = float(s.get("home", 0.0) or 0.0)
    return max(abs(float(s["lo"]) - h), abs(float(s["hi"]) - h))


def _axis_dist(P, piv, u):
    P = np.asarray(P, float).reshape(-1, 3) - np.asarray(piv, float)
    return np.linalg.norm(np.cross(P, np.asarray(u, float)), axis=1)


def _path_rho(j, path, info, J):
    """(P0, K) such that any point p hanging off path[0] stays within |p - P0| + K of joint j's axis, whatever the
    joints in `path` do: path runs from the point's side to j through moving joints (their pivots), and each pivot is
    fixed relative to the next, so only the last pivot's distance from j's axis and the links between pivots add.
    (None, 0): no joint in between, the point's own distance from the axis is exact."""
    if not path:
        return None, 0.0
    kind, piv, u = info[j]
    K = float(_axis_dist([info[path[-1]][1]], piv, u)[0])
    for a, b in zip(path, path[1:]):
        K += (info[a][1] - info[b][1]).length
    K += sum(_travel(J[x]) for x in path if info[x][0] == "prismatic")
    return np.array(info[path[0]][1], float), K


def _rho(P, P0, K, piv, u):
    P = np.asarray(P, float).reshape(-1, 3)
    return _axis_dist(P, piv, u) if P0 is None else np.linalg.norm(P - P0, axis=1) + K


def sweep_plan(obj_pts, obj_chain, leg_pts, leg_chain, J, CP, tol, cap, budget):
    """How to sweep one obstacle body against one leg: (poses, terms, stats).

    The relative motion comes from the moving joints in exactly one of the two chains. For each free (driver) joint
    the step is the largest that keeps the move of any point between two samples under `tol`: a point at distance rho
    from a revolute axis moves at most rho * step / 2 to the nearer sample, a slide point step / 2. rho is bounded on
    both sides (the leg's query point and the obstacle's box corners, through the pivots of the joints in between,
    see _path_rho), and the move is at most the smaller. Each joint gets at most `cap` samples. `terms` give that move
    per query point, so the swept solids are inflated by exactly what the sampling can miss. `budget` thins the
    product of long chains; the inflation grows to match, so thinning costs room, never a miss."""
    mo, ml = [j for j in obj_chain if j not in leg_chain], [j for j in leg_chain if j not in obj_chain]
    mo, ml = [j for j in mo if _ranged(j, J, CP)], [j for j in ml if _ranged(j, J, CP)]
    moving = mo + ml
    if not moving:
        return [{}], [], {"poses": 1, "drivers": {}}
    info = {j: _motion(j, J) for j in moving}
    terms_by = {}
    for j in moving:
        d, k = _driver_of(j, CP)
        kind, piv, u = info[j]
        if kind == "prismatic":
            terms_by.setdefault(d, []).append(("const", abs(k) * 0.5))
            continue
        if j in ml:     # the leg hangs below j: query side = leg joints below j; obstacle side = obstacle joints, then
            i = ml.index(j)     # the leg joints above j from the top down
            qpath, opath = ml[:i], mo + ml[i + 1:][::-1]
        else:
            i = mo.index(j)
            qpath, opath = ml + mo[i + 1:][::-1], mo[:i]
        P0, K = _path_rho(j, qpath, info, J)
        O0, OK = _path_rho(j, opath, info, J)
        ocap = float(_rho(obj_pts, O0, OK, piv, u).max())
        terms_by.setdefault(d, []).append(("rho", abs(k) * math.pi / 360.0, P0, K, piv, u, ocap))

    def coef(tl):       # move per unit of driver step at the worst grid point
        return sum(t[1] if t[0] == "const" else t[1] * min(t[6], float(_rho(leg_pts, t[2], t[3], t[4], t[5]).max())) for t in tl)
    drv = sorted(terms_by)
    rng, n = {}, {}
    for d in drv:
        s = J.get(d) or {}
        rng[d] = (0.0, 360.0, True) if s.get("continuous") else (float(s["lo"]), float(s["hi"]), False)
        c = coef(terms_by[d])
        span = rng[d][1] - rng[d][0]
        if span <= 1e-9:
            n[d] = 0
            continue
        st = tol / c if c > 1e-12 else span          # move per sample gap = c * step <= tol
        n[d] = min(cap - (0 if rng[d][2] else 1), max(1, int(math.ceil(span / st - 1e-9))))   # intervals

    def count(d):
        return 1 if n[d] == 0 else (n[d] if rng[d][2] else n[d] + 1)
    while math.prod(count(d) for d in drv) > budget:
        cand = [d for d in drv if n[d] > 1]
        if not cand:
            break
        d = min(cand, key=lambda x: coef(terms_by[x]) * (rng[x][1] - rng[x][0]) / n[x])
        n[d] = max(1, int(n[d] * 0.8))
    per, terms, stats = [], [], {}
    for d in drv:
        lo, hi, cyc = rng[d]
        st = (hi - lo) / n[d] if n[d] else 0.0
        vals = [lo + st * i for i in range(count(d))] if n[d] else [lo]
        per.append(vals)
        terms += [(t[0], t[1] * st) + tuple(t[2:]) for t in terms_by[d]]
        stats[d] = {"samples": len(vals), "step": round(st, 3), "max_move_mm": round(coef(terms_by[d]) * st, 2)}
    poses = [{}]
    for d, vals in zip(drv, per):
        poses = [dict(p, **{d: float(a)}) for p in poses for a in vals]
    return poses, terms, {"poses": len(poses), "drivers": stats}


def inflation(terms, P):
    """Largest move between sampled poses for query points P (n x 3, leg frame), per point."""
    P = np.asarray(P, float).reshape(-1, 3)
    out = np.zeros(len(P))
    for t in terms:
        out += t[1] if t[0] == "const" else t[1] * np.minimum(_rho(P, t[2], t[3], t[4], t[5]), t[6])
    return out


def _mw(name):
    o = bpy.data.objects.get(name) if name and name != "static" else None
    return o.matrix_world.copy() if o is not None else Matrix.Identity(4)


def _mw_at(name, J, vals, cache):
    if not name or name == "static" or bpy.data.objects.get(name) is None:
        return Matrix.Identity(4)
    return JT.world_at(name, J, vals, cache)


# ------------------------------------------------------------------ BVH

def _tris(o):
    me = o.data
    me.calc_loop_triangles()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    M = np.array(o.matrix_world)
    co = co @ M[:3, :3].T + M[:3, 3]
    t = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", t)
    return co, t.reshape(-1, 3)


def tree(objs, extra=()):
    """One BVH over all `objs` in world coordinates at the current pose, plus `extra` (vertices, triangles) arrays
    (None when empty)."""
    vs, ts, off = [], [], 0
    for co, t in [_tris(o) for o in objs] + list(extra):
        if not len(t):
            continue
        vs.append(co)
        ts.append(t + off)
        off += len(co)
    if not vs:
        return None
    return BVHTree.FromPolygons(np.concatenate(vs).tolist(), np.concatenate(ts).tolist(), all_triangles=True)


def _bbox(o):
    bb = np.array([list(o.matrix_world @ Vector(c)) for c in o.bound_box])
    return bb.min(0), bb.max(0)


def _fib(n):
    i = np.arange(n) + 0.5
    z = 1 - 2 * i / n
    r = np.sqrt(1 - z * z)
    a = 2.39996 * np.arange(n)
    return np.stack([np.cos(a) * r, np.sin(a) * r, z], 1)


_SPH26 = _fib(26).tolist()
_VIEW240 = None


def exposed(tr, p, opt):
    """cadcheck.exposed: min_escape of 26 rays leave, or view_frac of the directions toward a viewer above or level."""
    global _VIEW240
    if _VIEW240 is None:
        _VIEW240 = [d for d in _fib(400).tolist() if d[2] > opt["view_z"]]
    n = sum(1 for d in _SPH26 if tr.ray_cast(p, d, 3000.0)[0] is None)
    if n >= opt["min_escape"]:
        return True
    if n == 0 and all(tr.ray_cast(p, d, 3000.0)[0] is not None for d in _VIEW240[::8]):
        return False
    return sum(1 for d in _VIEW240 if tr.ray_cast(p, d, 3000.0)[0] is None) >= opt["view_frac"] * len(_VIEW240)


# ------------------------------------------------------------------ grid

class Grid:
    """Cell centres lo + ijk * h, padded by one blocked cell on every side. Flat index (i * ny + j) * nz + k."""

    def __init__(self, lo, hi, h):
        self.h = h
        self.lo = np.asarray(lo, float) - h
        self.n = np.ceil((np.asarray(hi, float) - np.asarray(lo, float)) / h).astype(int) + 3
        self.N = int(np.prod(self.n))
        self.ijk = np.indices(self.n).reshape(3, -1).T
        self.xyz = self.lo + self.ijk * h
        self.border = (self.ijk == 0).any(1) | (self.ijk == self.n - 1).any(1)

    def ijk_of(self, p):
        return np.clip(np.round((np.asarray(p, float) - self.lo) / self.h).astype(int), 0, self.n - 1)

    def flat(self, ijk):
        ijk = np.asarray(ijk)
        return (ijk[..., 0] * self.n[1] + ijk[..., 1]) * self.n[2] + ijk[..., 2]

    def at(self, p):
        return int(self.flat(self.ijk_of(p)))


def _nearest(G, tr, R, cells, d, ins, M=None, infl=None):
    """d[cells] = min(d, distance to tr - infl) for cells within R (+ infl); ins[c] |= the nearest face faces away
    (inside). The sign test catches solids that column parity can't (touching shells: A3's controller header block).
    M maps grid points into tr's frame; infl (per cell) inflates a swept solid by its move between sampled poses."""
    P = G.xyz[cells]
    if M is not None:
        A = np.array(M)
        P = P @ A[:3, :3].T + A[:3, 3]
    fn = tr.find_nearest
    inf = [0.0] * len(cells) if infl is None else infl.tolist()
    for c, p, e in zip(cells.tolist(), P.tolist(), inf):
        h = fn(p, R + e)
        if h[0] is not None:
            if h[3] - e < d[c]:
                d[c] = h[3] - e
            # relative tolerance: a point above a box edge whose nearest face comes back as the side face has a dot of
            # about -1e-4 * distance from float noise, which read as "inside" (-10.3 mm in the review's pan/tilt case)
            if (p[0] - h[0][0]) * h[1][0] + (p[1] - h[0][1]) * h[1][1] + (p[2] - h[0][2]) * h[1][2] < -1e-3 * h[3] - 1e-6:
                ins[c] = True


def _inside(G, objs, cand):
    """Cells inside a solid, by ray parity up each grid column, per object (overlapping parts don't cancel).
    Columns with an odd hit count (open mesh, grazing ray) are skipped."""
    ins = np.zeros(G.N, bool)
    nx, ny, nz = G.n
    h = G.h
    zs = G.lo[2] + np.arange(nz) * h
    for o in objs:
        blo, bhi = _bbox(o)
        i0, j0 = np.maximum(np.ceil((blo[:2] - G.lo[:2]) / h).astype(int), 1)
        i1, j1 = np.minimum(np.floor((bhi[:2] - G.lo[:2]) / h).astype(int), (nx - 2, ny - 2))
        k0, k1 = max(int(np.ceil((blo[2] - G.lo[2]) / h)), 1), min(int(np.floor((bhi[2] - G.lo[2]) / h)), nz - 2)
        if i1 < i0 or j1 < j0 or k1 < k0:
            continue
        t = None
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                base = (i * ny + j) * nz
                if not cand[base + k0:base + k1 + 1].any():
                    continue
                t = t or tree([o])
                x, y = G.lo[0] + i * h + 1.3e-3, G.lo[1] + j * h + 0.7e-3
                z, hits = blo[2] - 1.0, []
                while len(hits) < 200:
                    r = t.ray_cast((x, y, z), (0, 0, 1), bhi[2] + 1.0 - z)
                    if r[0] is None:
                        break
                    hits.append(r[0].z)
                    z = r[0].z + 1e-4
                if len(hits) % 2:
                    continue
                for a, b in zip(hits[0::2], hits[1::2]):
                    ka, kb = int(np.ceil((a - G.lo[2]) / h)), int(np.floor((b - G.lo[2]) / h))
                    if kb >= ka:
                        ins[base + max(ka, 0):base + min(kb, nz - 1) + 1] = True
    return ins


def _exposure(G, free, tv, opt):
    """Escaping fraction toward a viewer (cadcheck rule), one sample per 2x2x2 block, scaled so that
    view_frac (cadcheck's 'exposed' threshold) maps to 1."""
    dirs = [d for d in _fib(64).tolist() if d[2] > opt["view_z"]]
    need = max(1, int(math.ceil(opt["view_frac"] * len(dirs))))
    b = G.ijk // 2
    nb = G.n // 2 + 1
    key = (b[:, 0] * nb[1] + b[:, 1]) * nb[2] + b[:, 2]
    fi = np.nonzero(free)[0]
    ukey, first = np.unique(key[fi], return_index=True)
    val = np.zeros(int(nb.prod()))
    rc = tv.ray_cast
    for kk, p in zip(ukey.tolist(), G.xyz[fi[first]].tolist()):
        n = 0
        for d in dirs:
            if rc(p, d, 3000.0)[0] is None:
                n += 1
                if n >= need:
                    break
        val[kk] = n / need
    return val[key]


def _inbox(G, boxes):
    m = np.zeros(G.N, bool)
    for lo, hi in boxes:
        lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
        m |= ((G.xyz >= lo) & (G.xyz <= hi)).all(1)
    return m


# ------------------------------------------------------------------ search

_NB = [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1) if (a, b, c) != (0, 0, 0)]


def astar(G, blocked, W, src, dst, goal, w_turn):
    """Cheapest path from any source cell to any goal cell. src/dst: {cell: entry cost} (a stub from a buried
    endpoint costs its length * w_stub). Step cost = length * W[target] + w_turn * turn angle (from the parent's
    step: an approximation that keeps one state per cell). Heuristic: distance to the goal point less the
    longest goal stub (admissible, as W >= 1)."""
    nx, ny, nz = G.n
    h = G.h
    offs = [(a * ny + b) * nz + c for a, b, c in _NB]
    lens = [h * math.sqrt(a * a + b * b + c * c) for a, b, c in _NB]
    uv = [np.array(v, float) / np.linalg.norm(v) for v in _NB]
    turn = [[w_turn * math.acos(max(-1.0, min(1.0, float(uv[i] @ uv[j])))) for j in range(26)] for i in range(26)]
    Wl = W.tolist()
    bl = blocked.tolist()
    X, Y, Z = (G.xyz[:, k].tolist() for k in range(3))
    gx, gy, gz = (float(x) for x in goal)
    slack = max(0.0, max(math.sqrt((X[c] - gx) ** 2 + (Y[c] - gy) ** 2 + (Z[c] - gz) ** 2) for c in dst))
    sq = math.sqrt
    best = dict(src)
    par = {s: (-1, -1) for s in src}
    heap = [(c0 + max(0.0, sq((X[s] - gx) ** 2 + (Y[s] - gy) ** 2 + (Z[s] - gz) ** 2) - slack), c0, s, -1) for s, c0 in src.items()]
    heapq.heapify(heap)
    done = set()
    end, end_cost = None, 1e30
    while heap:
        f, gc, u, pd = heapq.heappop(heap)
        if f >= end_cost:
            break
        if u in done:
            continue
        done.add(u)
        if u in dst and gc + dst[u] < end_cost:
            end, end_cost = u, gc + dst[u]
        tr = turn[pd] if pd >= 0 else None
        for n in range(26):
            v = u + offs[n]
            if bl[v] or v in done:
                continue
            c = gc + lens[n] * Wl[v] + (tr[n] if tr else 0.0)
            if c < best.get(v, 1e30):
                best[v] = c
                par[v] = (u, n)
                heapq.heappush(heap, (c + max(0.0, sq((X[v] - gx) ** 2 + (Y[v] - gy) ** 2 + (Z[v] - gz) ** 2) - slack), c, v, n))
    if end is None:
        return None, len(done)
    path, u = [], end
    while u != -1:
        path.append(u)
        u = par[u][0]
    return path[::-1], len(done)


# ------------------------------------------------------------------ one leg

class Leg:
    """Grid, costs and exact clearance for one leg (between two waypoints, on one body)."""

    def __init__(self, a, b, r, legbody, obstacles, J, CP, opt, tv):
        t0 = time.time()
        h = opt["cell"]
        self.r, self.h, self.opt = r, h, opt
        self.R = r + opt["clearance"]
        band = opt["wall_band"] if opt["wall_band"] is not None else 1.5 * h
        self.dcap = self.R + band            # d is exact below this; above it only "farther than dcap" is known
        lo = np.minimum(a, b) - opt["margin"]
        hi = np.maximum(a, b) + opt["margin"]
        G = self.G = Grid(lo, hi, h)
        set_pose({}, J, CP)
        # obstacles on this leg's body (or with no moving joint between) are fixed; the rest sweep, one rigid group per
        # body: one BVH at home, posed by a matrix per sampled pose. A part behind a continuous joint (a wheel) is
        # replaced by its spin envelope, an annulus about that axis on the wheel's parent body: sampled instead, A3's
        # flywheel took 900 pan x tilt x wheel poses at 47 mm of inflation
        mine = chain(legbody)
        groups = {}
        for o in obstacles:
            ch = chain(o)
            spin = [j for j in ch if j not in mine and (J.get(j) or {}).get("axis") and (J.get(j) or {}).get("continuous")]
            if spin:
                c = spin[-1]
                up = chain(c)[1:]
                g = groups.setdefault(up[0] if up else "static", {"objs": [], "extra": []})
                g["extra"].append(_envelope(o, c, ch, J, CP))
            else:
                groups.setdefault(body(o), {"objs": [], "extra": []})["objs"].append(o)
        set_pose({}, J, CP)
        corners = np.array([[x, y, z] for x in (G.lo[0], G.lo[0] + G.n[0] * h) for y in (G.lo[1], G.lo[1] + G.n[1] * h)
                            for z in (G.lo[2], G.lo[2] + G.n[2] * h)])
        tol = opt["sweep_tol"] if opt["sweep_tol"] is not None else 0.5 * self.R
        fixed, fixed_extra, plans = [], [], []
        for bn, g in sorted(groups.items()):
            opts = np.array([c for o in g["objs"] for c in _corners(o)] + [c for co, _ in g["extra"] for c in co.tolist()])
            poses, terms, st = sweep_plan(opts, chain(bn), corners, mine, J, CP, tol, int(opt["max_joint_poses"]),
                                          int(opt["max_group_poses"]))
            if not terms and len(poses) == 1:
                fixed += g["objs"]
                fixed_extra += g["extra"]
            else:
                plans.append((bn, g, opts, poses, terms, st))
        set_pose({}, J, CP)
        self.fixed_tree = tree(fixed, fixed_extra)
        d = np.full(G.N, np.inf)
        sign_in = np.zeros(G.N, bool)
        live = np.nonzero(~G.border)[0]
        XL = G.xyz[live]
        if self.fixed_tree:
            _nearest(G, self.fixed_tree, self.dcap, live, d, sign_in)
        Mleg_home = _mw(legbody)
        glo, ghi = G.lo, G.lo + (G.n - 1) * h
        BLK = 8
        nb = tuple(int(x) for x in (G.n + BLK - 1) // BLK)
        nbm = np.array(nb) - 1
        bi = G.ijk[live] // BLK
        blk = (bi[:, 0] * nb[1] + bi[:, 1]) * nb[2] + bi[:, 2]
        self.groups, self.sweep_stats = [], []
        for bn, g, opts, poses, terms, st in plans:
            set_pose({}, J, CP)
            tr = tree(g["objs"], g["extra"])           # world at home = this body's home frame
            if tr is None:
                continue
            Mb_home = _mw(bn)
            infl_all = inflation(terms, XL)
            emax = float(infl_all.max()) if len(infl_all) else 0.0
            pad = self.dcap + emax
            # each part's home box (a static group's union box covers the whole grid): per pose, only the 8-cell
            # blocks that some part's box reaches get distance queries
            bx = [(np.array(_corners(o)).min(0), np.array(_corners(o)).max(0)) for o in g["objs"]] + \
                 [(co.min(0), co.max(0)) for co, _ in g["extra"]]
            boxes = np.array([[[x, y, z, 1] for x in (lo_[0], hi_[0]) for y in (lo_[1], hi_[1]) for z in (lo_[2], hi_[2])]
                              for lo_, hi_ in bx])
            Ts = []
            for pose in poses:
                # leg frame (world at home) -> world at this pose -> the obstacle body's home frame; matrices from the
                # parent chain (cadlib.joints.world_at), so a pose costs no depsgraph update
                vals, cache = JT.values(J, CP, pose), {}
                T = Mb_home @ _mw_at(bn, J, vals, cache).inverted() @ _mw_at(legbody, J, vals, cache) @ Mleg_home.inverted()
                cl = (boxes @ np.array(T.inverted()).T)[:, :, :3]      # every part's home box, in the leg frame
                clo, chi = cl.min(1) - pad, cl.max(1) + pad
                hit = ~((chi < glo).any(1) | (clo > ghi).any(1))
                if not hit.any():
                    continue
                bm = np.zeros(nb, bool)
                b0 = np.clip(np.floor((clo[hit] - G.lo) / (BLK * h)).astype(int), 0, nbm)
                b1 = np.clip(np.floor((chi[hit] - G.lo) / (BLK * h)).astype(int), 0, nbm)
                for (i0, j0, k0), (i1, j1, k1) in zip(b0.tolist(), b1.tolist()):
                    bm[i0:i1 + 1, j0:j1 + 1, k0:k1 + 1] = True
                sel = bm.ravel()[blk]
                if not sel.any():
                    continue
                Ts.append(T)
                cells = live[sel]
                keep = d[cells] >= self.R              # already blocked: another pose can't unblock it
                _nearest(G, tr, self.dcap, cells[keep], d, sign_in, T, infl_all[sel][keep])
            self.groups.append({"body": bn, "tree": tr, "Ts": Ts, "terms": terms})
            self.sweep_stats.append(dict(st, body=bn, near_poses=len(Ts), max_inflation_mm=round(emax, 2),
                                         spin_envelopes=len(g["extra"])))
        set_pose({}, J, CP)
        self.d = d
        cand = d >= self.R
        self.inside = (_inside(G, fixed, cand) if fixed else np.zeros(G.N, bool)) | sign_in
        self.blocked = G.border | (d < self.R) | self.inside | _inbox(G, opt["avoid"])
        W = 1.0 + opt["w_open"] * (d >= self.R + band)
        self.t_grid = time.time() - t0
        t0 = time.time()
        if opt["exposure"] and opt["w_exposed"] and tv is not None:
            W = W + opt["w_exposed"] * _exposure(G, ~self.blocked, tv, opt)
        pref = _inbox(G, opt["prefer"])
        W[pref] = 1.0
        self.W = W
        self.t_exposure = time.time() - t0

    @property
    def swept_poses(self):
        return sum(len(g["Ts"]) for g in self.groups)

    def holds(self, p):
        ijk = (np.asarray(p, float) - self.G.lo) / self.h
        return bool((ijk >= 0.5).all() and (ijk <= self.G.n - 1.5).all())

    def clear(self, p):
        """Exact clearance of a cable centred at p: surface distance minus r, negative (-(d + r)) when p is inside
        a solid (nearest face points away), worst over the swept poses, a swept solid inflated by its move between
        samples. None when no solid is within r + clearance + 5 mm."""
        best = None
        pv = Vector(p)
        if self.fixed_tree:
            hh = self.fixed_tree.find_nearest(pv, self.R + 5.0)
            if hh[0] is not None:
                best = hh[3] - self.r if _outside(pv, hh) else -hh[3] - self.r
        for g in self.groups:
            e = float(inflation(g["terms"], [p])[0]) if g["terms"] else 0.0
            fn = g["tree"].find_nearest
            for T in g["Ts"]:
                q = T @ pv
                hh = fn(q, self.R + 5.0 + e)
                if hh[0] is not None:
                    dd = (hh[3] if _outside(q, hh) else -hh[3]) - self.r - e
                    best = dd if best is None else min(best, dd)
        return best

    def swept_by(self, p):
        """{body: clearance} for the swept bodies that take p under the requested clearance at some pose."""
        out, pv = {}, Vector(p)
        for g in self.groups:
            e = float(inflation(g["terms"], [p])[0]) if g["terms"] else 0.0
            for T in g["Ts"]:
                q = T @ pv
                hh = g["tree"].find_nearest(q, self.R + 5.0 + e)
                if hh[0] is not None:
                    dd = (hh[3] if _outside(q, hh) else -hh[3]) - self.r - e
                    if dd < self.opt["clearance"]:
                        out[g["body"]] = round(min(out.get(g["body"], 1e9), dd), 2)
        return out

    def clear_lb(self, p, need):
        """clear(p), or a lower bound on it that is already >= need (from the grid's distance field: d is 1-Lipschitz,
        so a free cell whose centre is far from every solid proves p is too). Keeps the shortcut and fillet checks
        cheap when hundreds of poses are swept."""
        if self.holds(p):
            c = self.G.at(p)
            if not self.inside[c]:
                lb = min(float(self.d[c]), self.dcap) - (Vector(p) - Vector(self.G.xyz[c])).length - self.r
                if lb >= need:
                    return lb
        v = self.clear(p)
        return 1e9 if v is None else v

    def seg_ok(self, a, b, wmax, skip_a=0.0, skip_b=0.0, need=None):
        """Segment a-b keeps the clearance (exact) through free cells no costlier than wmax."""
        need = self.opt["clearance"] if need is None else need
        a, b = Vector(a), Vector(b)
        L = (b - a).length
        n = max(1, int(math.ceil(L / min(0.5, 0.5 * self.h))))
        for i in range(n + 1):
            s = L * i / n
            if s < skip_a or s > L - skip_b:
                continue
            p = a.lerp(b, i / n)
            c = self.G.at(p)
            if self.blocked[c] or (wmax is not None and self.W[c] > wmax + 1e-6):
                return False
            if self.clear_lb(p, need) < need:
                return False
        return True

    def entry(self, p, mode=0):
        """{cell: cost} where the search may start or end for waypoint p.
        mode 0: p's own cell when p keeps the clearance and its cell is free; otherwise the same as mode 1.
        mode 1: free cells within lead_in, at w_stub * W per mm of a straight stub that goes no deeper into a solid
                than p already is (from a clear p: never into a solid, though it may cross the clearance band). This
                is what lets a clear p in a pocket whose own cell is boxed in by the band reach the open grid.
        mode 2: any stub (reported in `stubs`).
        Stubs serve connectors inside a part's envelope (A3's CAB_12v_ctrl ends inside the controller's header block)
        and points sealed in a pocket (A3's CAB_uart ends under the controller board, where the hand route also cut
        the board). Only the 200 nearest cells are tried. Empty when nothing is free nearby."""
        G = self.G
        c = G.at(p)
        cp = self.clear(p)
        cp = 1e9 if cp is None else cp
        if mode == 0 and not self.blocked[c] and cp >= self.opt["clearance"]:
            return {c: 0.0}
        lead = self.opt["lead_in"] or (self.R + 4 * self.h)
        k = int(math.ceil(lead / self.h))
        ijk = G.ijk_of(p)
        rng = [np.arange(max(1, ijk[a] - k), min(G.n[a] - 1, ijk[a] + k + 1)) for a in range(3)]
        cells = G.flat(np.stack(np.meshgrid(*rng, indexing="ij"), -1).reshape(-1, 3))
        cells = cells[~self.blocked[cells]]
        dd = np.linalg.norm(G.xyz[cells] - np.asarray(p, float), axis=1)
        order = np.argsort(dd)[:200]
        floor = min(cp, 0.0) - 1e-3
        pv = Vector(p)
        out = {}
        for c, x in zip(cells[order].tolist(), dd[order].tolist()):
            if x > lead + 1e-6:
                break
            q = Vector(G.xyz[c])
            m = max(1, int(math.ceil(x / 0.5)))
            if mode == 2 or all(self.clear_lb(pv.lerp(q, s / m), floor) >= floor for s in range(1, m + 1)):
                out[c] = x * self.opt["w_stub"] * float(self.W[c])
        return out


def _envelope(o, c, ch, J, CP, n=48):
    """Closed annulus (vertices, triangles; world at home) that object o fills while continuous joint c spins: radii
    rho_min..rho_max about c's axis over o's axial extent. With moving joints between o and c, rho_min is 0 and rho_max
    the reach bound. Polygon edges sit inside rho_min and outside rho_max, so the envelope covers the part."""
    kind, piv, u = _motion(c, J)
    u = Vector(u).normalized()
    co, _ = _tris(o)
    below = [j for j in ch[:ch.index(c)] if _ranged(j, J, CP)]
    t = (co - np.array(piv)) @ np.array(u)
    if below:
        info = {j: _motion(j, J) for j in below + [c]}
        P0, K = _path_rho(c, below, info, J)
        rmax = float(_rho(co, P0, K, piv, u).max())
        rmin, t0, t1 = 0.0, float(t.min()) - rmax, float(t.max()) + rmax
    else:
        rmax = float(_axis_dist(co, piv, u).max())
        t0, t1 = float(t.min()), float(t.max())
        # closest approach of the surface to the axis: nearest hits from axis points every 0.5 mm (0.25 mm slack)
        tr = tree([o])
        m = max(2, int(math.ceil((t1 - t0) / 0.5)) + 1)
        rmin = 1e9
        for i in range(m):
            q = Vector(piv) + u * (t0 + (t1 - t0) * i / (m - 1))
            hh = tr.find_nearest(q, rmax + 1.0)
            if hh[0] is None:
                continue
            if not _outside(q, hh):          # the axis runs through the solid: a disc, no bore
                rmin = 0.0
                break
            rmin = min(rmin, hh[3])
        rmin = max(0.0, min(rmin, rmax) - 0.25)
    w = u.orthogonal().normalized()
    v = u.cross(w)
    ro, ri = rmax / math.cos(math.pi / n), max(rmin, 1e-3)      # a 1 um core keeps the inner wall's normals defined
    V = []
    for tt in (t0, t1):
        for rr in (ri, ro):
            for k in range(n):
                a = 2 * math.pi * k / n
                V.append(list(Vector(piv) + u * tt + (w * math.cos(a) + v * math.sin(a)) * rr))
    # rings: 0 = bottom inner, 1 = bottom outer, 2 = top inner, 3 = top outer
    F = []

    def quad(r0, r1, k, flip):
        a, b, c2, d2 = r0 * n + k, r0 * n + (k + 1) % n, r1 * n + (k + 1) % n, r1 * n + k
        F.extend([(a, c2, b), (a, d2, c2)] if flip else [(a, b, c2), (a, c2, d2)])
    for k in range(n):
        quad(1, 3, k, False)        # outer wall
        quad(0, 2, k, True)         # inner wall
        quad(0, 1, k, False)        # bottom cap
        quad(2, 3, k, True)         # top cap
    return np.array(V, float), np.array(F, dtype=np.int64)


def _outside(q, hh):
    """find_nearest hit hh is on the outside of q's solid (same relative tolerance as _nearest)."""
    return (q - hh[0]).dot(hh[1]) >= -1e-3 * hh[3] - 1e-6


def _corners(o):
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return [list(v) for v in bb]


def _shortcut(leg, P, Wp, skip_a, skip_b):
    """Line-of-sight shortcuts. skip_a / skip_b: mm at the first / last point left unchecked (an end's stub plus a
    cell; at a via only its stub, so a shortcut can't cut the corner of the slot the via sits in)."""
    out, i, n = [P[0]], 0, len(P)
    while i < n - 1:
        j, k = i + 1, i + 2
        while k < n and leg.seg_ok(P[i], P[k], max(Wp[i:k + 1]), skip_a=skip_a if i == 0 else 0.0,
                                   skip_b=skip_b if k == n - 1 else 0.0):
            j, k = k, k + 1
        out.append(P[j])
        i = j
    return out


def _merge_short(leg, P, skip_a, skip_b):
    """Drop a vertex between short segments (< 2.5 cells, the staircase A* leaves at a turn) when the joined
    segment keeps the clearance; longer segments leave room for the bend radius (A3 CAB_12v_mg: 2.5 -> 8 mm)."""
    P = list(P)
    i = 1
    while i < len(P) - 1:
        if min((P[i] - P[i - 1]).length, (P[i + 1] - P[i]).length) < 2.5 * leg.h and \
                leg.seg_ok(P[i - 1], P[i + 1], None, skip_a=skip_a if i == 1 else 0.0,
                           skip_b=skip_b if i == len(P) - 2 else 0.0):
            del P[i]
            i = max(1, i - 1)
        else:
            i += 1
    return P


# ------------------------------------------------------------------ fillets

def _arc(P, din, dout, R, step_deg=10.0):
    th = din.angle(dout)
    if th < 1e-3 or R <= 1e-6:
        return [P.copy()]
    t = R * math.tan(th / 2)
    T1, T2 = P - din * t, P + dout * t
    C = P + (dout - din).normalized() * (R / math.cos(th / 2))
    u, w = T1 - C, T2 - C
    k = max(2, int(math.ceil(math.degrees(th) / step_deg)))
    a = u.angle(w)       # = th; mathutils' slerp returns unit vectors, so interpolate by hand
    return [C + (u * math.sin((1 - i / k) * a) + w * math.sin(i / k * a)) / math.sin(a) for i in range(k + 1)]


def _dense(pts, step=0.5):
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        m = max(1, int(math.ceil((b - a).length / step)))
        out += [a.lerp(b, s / m) for s in range(1, m + 1)]
    return out


def fillet(P, bend_r, check, fixed=(), r_min=0.5, lead=(0.0, 0.0)):
    """Round each corner of polyline P with radius bend_r where it fits (tangent lengths share each segment; the
    first and last segments keep lead[0] / lead[1] mm straight), keeping check(points, corner) true: push the corner
    outward (up to 3 times), else shrink the radius by 0.7 down to r_min, then leave it sharp. A corner whose fitted
    radius is under r_min is left sharp too. Returns (points, radius per interior vertex)."""
    P = [Vector(p) for p in P]
    n = len(P)
    if n < 3:
        return P, []
    want = [0.0] + [float(bend_r)] * (n - 2) + [0.0]
    pushes = [0] * n

    def tn(i):
        if i <= 0 or i >= n - 1:
            return 0.0
        a, b = P[i] - P[i - 1], P[i + 1] - P[i]
        if a.length < 1e-9 or b.length < 1e-9:
            return 0.0
        return math.tan(min(a.angle(b), math.radians(178)) / 2)

    def fit():
        tt = [tn(i) for i in range(n)]
        t = [want[i] * tt[i] for i in range(n)]
        f = [1.0] * n
        for i in range(n - 1):
            L, s = (P[i + 1] - P[i]).length, t[i] + t[i + 1]
            L = max(0.0, L - (lead[0] if i == 0 else 0.0) - (lead[1] if i == n - 2 else 0.0))
            if s > L:
                f[i], f[i + 1] = min(f[i], L / s), min(f[i + 1], L / s)
        R = [t[i] * f[i] / tt[i] if tt[i] > 1e-6 else 0.0 for i in range(n)]
        return [x if x >= r_min - 1e-9 else 0.0 for x in R]

    def arc(i, R):
        return _arc(P[i], (P[i] - P[i - 1]).normalized(), (P[i + 1] - P[i]).normalized(), R[i])

    def shrink(i, R):
        want[i] = R[i] * 0.7 if R[i] * 0.7 >= r_min else 0.0

    for _ in range(6):
        R = fit()
        changed = False
        for i in range(1, n - 1):
            if R[i] <= 0 or check(_dense(arc(i, R)), i):
                continue
            changed = True
            out = (P[i] - P[i - 1]).normalized() - (P[i + 1] - P[i]).normalized()
            if pushes[i] < 3 and i not in fixed and out.length > 1e-6:
                pushes[i] += 1
                old = P[i].copy()
                P[i] = P[i] + out.normalized() * max(0.5, 0.2 * R[i])
                if check(_dense([P[i - 1], P[i], P[i + 1]]), i):
                    continue
                P[i] = old
                pushes[i] = 3
            shrink(i, R)
        if not changed:
            break
    R = fit()
    for i in range(1, n - 1):          # pushes move neighbours' arcs: re-check every corner once more
        while R[i] > 0 and not check(_dense(arc(i, R)), i):
            shrink(i, R)
            R[i] = want[i]
    out = [P[0]]
    for i in range(1, n - 1):
        out += arc(i, R)
    out.append(P[-1])
    clean = [out[0]]
    for p in out[1:]:
        if (p - clean[-1]).length > 1e-4:
            clean.append(p)
    return clean, R[1:-1]


# ------------------------------------------------------------------ route

def _via(v):
    return dict(v, at=Vector(v["at"])) if isinstance(v, dict) else {"at": Vector(v)}


def _plen(pts):
    return sum((Vector(pts[i + 1]) - Vector(pts[i])).length for i in range(len(pts) - 1))


def _waypoints(start, end, via, joint, cell):
    """start, vias, end as points. A via with "dir" becomes a straight run (at - dir*len/2, at, at + dir*len/2).
    Each waypoint carries the body of the leg that starts there; "joint" on a via changes it from the via on."""
    wps = [{"p": Vector(start), "body": joint or "static", "kind": "end"}]
    for v in map(_via, via):
        prev = wps[-1]["body"]
        nb = v.get("joint", prev)
        if v.get("dir"):
            d = Vector(v["dir"]).normalized()
            L = float(v.get("len", 4 * cell))
            a0, a1 = v["at"] - d * (L / 2), v["at"] + d * (L / 2)
            if (a0 - wps[-1]["p"]).length > (a1 - wps[-1]["p"]).length:
                a0, a1 = a1, a0
            wps += [{"p": a0, "body": prev, "kind": "run", "straight": True},
                    {"p": v["at"], "body": nb, "kind": "via", "straight": True, "from": prev, "dir": tuple(d)},
                    {"p": a1, "body": nb, "kind": "run"}]
        else:
            wps.append({"p": v["at"], "body": nb, "kind": "via", "from": prev})
    wps.append({"p": Vector(end), "body": None, "kind": "end"})
    return wps


def route(start, end, r, via=(), joint=None, obstacles=None, joints=None, couplings=None, cfg=None, quiet=False, **kw):
    """Route a cable of radius r from start to end through each via. Returns a JSON-safe dict: pts (all points, for
    asm.cable when there is one piece), pieces [{joint, pts}] (one per body when a via changes body), length_mm,
    min_clearance_mm (None when no solid is within r + clearance + 5 mm), violations (samples away from the ends under
    the requested clearance), crossings (the turn at each joint crossing at each limit), warnings, stubs, bend_r_min,
    exposed_mm, slack rows, time_s and grid stats. Violations and warnings are also printed unless quiet.

    joint: the body of the first leg (the joint you would give asm.cable). obstacles: default Printed +
    Purchased + Fasteners. joints/couplings: scene_joints(cfg) when None. kw overrides DEFAULTS
    (cell, clearance, margin, bend_r, w_open, w_exposed, w_turn, prefer=[(lo, hi)], avoid=[(lo, hi)], ...)."""
    T0 = time.time()
    opt = dict(DEFAULTS, **kw)
    opt["bend_r"] = float(opt["bend_r"]) if opt["bend_r"] is not None else 5.0 * r
    bend_floor = max(0.5, float(opt["min_bend_od"]) * 2 * r)
    if joints is None:
        joints, cp = scene_joints(cfg)
        couplings = cp if couplings is None else couplings
    couplings = couplings or {}
    obstacles = obstacles if obstacles is not None else mesh_objs(OBSTACLES)
    set_pose({}, joints, couplings)
    tv = tree(mesh_objs(VIEWERS)) if opt["exposure"] else None
    wps = _waypoints(start, end, via, joint, opt["cell"])
    # cadcheck's kink test: an end within 3 mm of a purchased part is a termination and keeps one OD straight
    tb = tree(mesh_objs(("Purchased",)))
    leads = tuple(2.0 * r if tb is not None and tb.find_nearest(Vector(p), 3.0)[0] is not None else 0.0 for p in (start, end))
    legrows, stubs, legs = [], [], []
    poly, seg_leg, wp_at = [wps[0]["p"].copy()], [], [0]
    end_skip = [0.0, 0.0]          # mm at the start / end that the guard leaves to the end stub
    for k in range(len(wps) - 1):
        a, b, lb = wps[k]["p"], wps[k + 1]["p"], wps[k]["body"]
        a_end, b_end = k == 0, k == len(wps) - 2
        if wps[k].get("straight"):
            # a forced straight run (via "dir"): not searched, but checked like the rest (a small grid of its own)
            leg = Leg(np.array(a), np.array(b), r, lb, obstacles, joints, couplings,
                      dict(opt, margin=opt["clearance"] + r + 4 * opt["cell"]), None)
            seg = [a, b]
            legrows.append({"body": lb, "straight": True, "dims": leg.G.n.tolist(), "swept_poses": leg.swept_poses,
                            "sweep": leg.sweep_stats, "grid_s": round(leg.t_grid, 2)})
        else:
            leg, prev = None, None
            for grow, mode in ((1, 0), (1, 1), (1, 2), (2, 2)):   # clear ends, safe stubs, any stub, a bigger box
                o2 = dict(opt, margin=opt["margin"] * grow)
                if leg is None or leg.opt["margin"] != o2["margin"]:
                    leg, prev = Leg(np.array(a), np.array(b), r, lb, obstacles, joints, couplings, o2, tv), None
                src, dst = leg.entry(a, mode), leg.entry(b, mode)
                if not src or not dst:
                    pb = a if not src else b
                    sw = leg.swept_by(pb)
                    raise RuntimeError("route: %s is buried: no free cell within lead_in (r + clearance = %.2f)%s" % (
                        [round(x, 1) for x in pb], leg.R, "; it is in the swept path of %s (clearance %s over the joint "
                        "range): move it out of the path, or put the cable on that body" % (", ".join(sw), sw) if sw else ""))
                if prev == (src, dst):         # mode 1 gave mode 0's entries (neither end was clear): same search
                    continue
                prev = (src, dst)
                t0 = time.time()
                cells, nexp = astar(leg.G, leg.blocked, leg.W, src, dst, b, opt["w_turn"])
                ts = time.time() - t0
                if cells is not None:
                    break
            if cells is None:
                raise RuntimeError("route: no path from %s to %s with r + clearance = %.2f mm on a %.1f mm grid; try a "
                                   "smaller cell or clearance, or a via (a slot or bore narrower than 2 (r + clearance) "
                                   "+ cell needs a via with \"dir\")" % ([round(x, 1) for x in a], [round(x, 1) for x in b], leg.R, leg.h))
            sa = (Vector(leg.G.xyz[cells[0]]) - a).length if src[cells[0]] else 0.0
            sb = (Vector(leg.G.xyz[cells[-1]]) - b).length if dst[cells[-1]] else 0.0
            # an end skips its stub plus a cell (the plug's own clearance is the end's business); a via only its stub
            ka, kb = sa + (leg.h if a_end else 0.0), sb + (leg.h if b_end else 0.0)
            if a_end:
                end_skip[0] = ka
            if b_end:
                end_skip[1] = kb
            P = [a] + [Vector(leg.G.xyz[c]) for c in cells] + [b]
            Wp = [leg.W[cells[0]]] + [float(leg.W[c]) for c in cells] + [leg.W[cells[-1]]]
            t0 = time.time()
            seg = _merge_short(leg, _shortcut(leg, P, Wp, ka, kb), ka, kb)
            legrows.append({"body": lb, "dims": leg.G.n.tolist(), "cells": int(leg.G.N), "margin": o2["margin"],
                            "blocked_frac": round(float(leg.blocked.mean()), 3), "swept_poses": leg.swept_poses,
                            "sweep": leg.sweep_stats, "expanded": nexp, "grid_s": round(leg.t_grid, 2),
                            "exposure_s": round(leg.t_exposure, 2), "search_s": round(ts, 2),
                            "shortcut_s": round(time.time() - t0, 2)})
            for p, s_, c, is_end in ((a, sa, cells[0], a_end), (b, sb, cells[-1], b_end)):
                if s_:
                    q = Vector(leg.G.xyz[c])
                    m = max(1, int(math.ceil(s_ / 0.5)))
                    cl = [leg.clear(p.lerp(q, k2 / m)) for k2 in range(m + 1)]
                    cl = [x for x in cl if x is not None]
                    c0 = leg.clear(p)
                    stubs.append({"at": [round(x, 2) for x in p], "end": is_end, "stub_mm": round(s_, 1),
                                  "clearance_mm": round(c0, 2) if c0 is not None else None,
                                  "stub_min_clearance_mm": round(min(cl), 2) if cl else None})
        legs.append(leg)
        for p in seg[1:]:
            poly.append(Vector(p))
            seg_leg.append(leg)
        wp_at.append(len(poly) - 1)
    # a via without a dir gets a 2 x 1.5 mm straight run through it, so the fillets keep it on the path
    for k in range(len(wps) - 2, 0, -1):
        i = wp_at[k]
        if wps[k]["kind"] != "via" or wps[k].get("straight") or wps[k - 1].get("straight"):
            continue
        din, dout = poly[i] - poly[i - 1], poly[i + 1] - poly[i]
        u = (din.normalized() + dout.normalized())
        u = u.normalized() if u.length > 1e-6 else din.normalized()
        s_ = min(1.5, 0.25 * din.length, 0.25 * dout.length)
        poly[i:i + 1] = [poly[i] - u * s_, poly[i].copy(), poly[i] + u * s_]
        seg_leg[i - 1:i] = [seg_leg[i - 1]] * 2
        seg_leg[i + 1:i + 1] = [seg_leg[i + 1]]
        for kk in range(k, len(wp_at)):
            wp_at[kk] += 1 if kk == k else 2
    ends = [Vector(start), Vector(end)]

    def near_end(p):
        return (p - ends[0]).length < end_skip[0] or (p - ends[1]).length < end_skip[1]

    def clear_by(p, cand, need=None):
        """Exact clearance of p for the legs in cand whose grid holds it (None if none does); -r inside a solid.
        With `need`, a lower bound that is already >= need may stand in for the exact value."""
        out = None
        for leg in cand:
            if leg is None or not leg.holds(p):
                continue
            if leg.inside[leg.G.at(p)]:
                c = -leg.r
            else:
                c = leg.clear(p) if need is None else leg.clear_lb(p, need)
            if c is not None:
                out = c if out is None else min(out, c)
        return out

    def check(pts, i):
        cand = {seg_leg[j] for j in (i - 1, i) if 0 <= j < len(seg_leg)}
        for p in pts:
            if near_end(p):
                continue
            c = clear_by(p, cand, opt["clearance"])
            if c is not None and c < opt["clearance"]:
                return False
        return True

    t0 = time.time()
    fixed = {wp_at[k] for k, w in enumerate(wps) if w["kind"] in ("run", "via")}
    pts, radii = fillet(poly, opt["bend_r"], check, fixed=fixed, r_min=bend_floor, lead=leads)
    corner_rows = [{"at": [round(x, 1) for x in poly[i + 1]], "turn_deg": round(_turn(poly, i + 1), 1), "r": round(x, 2)}
                   for i, x in enumerate(radii) if _turn(poly, i + 1) > 1.0]
    t_smooth = time.time() - t0
    # one piece per body: split at the vias that change body (they stay exact vertices of pts)
    cut_wps = [w for w in wps if w["kind"] == "via" and w["body"] != w["from"]]
    cuts = [w["p"] for w in cut_wps]
    bodies = [wps[0]["body"]] + [w["body"] for w in cut_wps]
    pieces, cur = [{"joint": bodies[0], "pts": []}], 0
    for p in pts:
        pieces[-1]["pts"].append(p)
        if cur < len(cuts) and (p - cuts[cur]).length < 1e-6:
            cur += 1
            pieces.append({"joint": bodies[cur], "pts": [p]})
    body_legs = {}
    for leg, w in zip(legs, wps):
        body_legs.setdefault(w["body"], []).append(leg)
    # guard and stats: exact clearance every 0.5 mm (one sample index along the whole route), inside cells, and
    # exposure every 2 mm on the centre line (cadcheck's rule)
    clr_all, clr_mid, inside, exp_mm, viol, si = [], [], 0, 0.0, [], 0
    for pc in pieces:
        q = pc["pts"]
        for i in range(len(q) - 1):
            L = (q[i + 1] - q[i]).length
            m = max(1, int(math.ceil(L / 0.5)))
            for s_ in range(m + 1):
                p = q[i].lerp(q[i + 1], s_ / m)
                si += 1
                c = clear_by(p, body_legs.get(pc["joint"], []))
                if c is None:
                    continue
                clr_all.append(c)
                if not near_end(p):
                    clr_mid.append((c, [round(x, 2) for x in p]))
                    inside += int(any(lg is not None and lg.holds(p) and lg.inside[lg.G.at(p)] for lg in body_legs.get(pc["joint"], [])))
                    if c < opt["clearance"] - 1e-3 and not (viol and viol[-1]["i"] == si - 1 and viol[-1]["at"] == [round(x, 2) for x in p]):
                        viol.append({"i": si - 1, "at": [round(x, 2) for x in p], "clearance_mm": round(c, 2)})
            if tv is not None:
                m2 = max(1, int(math.ceil(L / 2.0)))
                exp_mm += sum(L / m2 for s_ in range(m2) if exposed(tv, q[i].lerp(q[i + 1], (s_ + 0.5) / m2), opt))
    bent = [x for i, x in enumerate(radii) if _turn(poly, i + 1) > 1.0]
    cross = crossings(pieces, cut_wps, joints, couplings)
    warnings = []
    if viol:
        w = min(viol, key=lambda v: v["clearance_mm"])
        warnings.append("%d samples away from the ends are under the requested %.2f mm clearance (worst %.2f at %s%s)" % (
            len(viol), opt["clearance"], w["clearance_mm"], w["at"], ", into a solid or its swept path" if w["clearance_mm"] < 0 else ""))
    for cr in cross:
        worst = max(cr["turn_deg"].items(), key=lambda kv: kv[1])
        if worst[1] > opt["fold_warn_deg"] and not cr["on_axis"]:
            cr["warn"] = True
            warnings.append("the cable folds %.0f deg crossing %s at %s (%s=%s): cross along the joint axis (via \"dir\" = "
                            "the axis) or model a service loop" % (worst[1], cr["joint"], cr["at"], cr["joint"], worst[0]))
    mn = min(clr_mid) if clr_mid else None
    mna = min(clr_all) if clr_all else None
    res = {"pts": [[round(x, 3) for x in p] for p in pts],
           "pieces": [{"joint": pc["joint"], "pts": [[round(x, 3) for x in p] for p in pc["pts"]]} for pc in pieces],
           "r": r, "length_mm": round(_plen(pts), 1), "straight_mm": round((ends[1] - ends[0]).length, 1),
           "min_clearance_mm": round(mn[0], 2) if mn else None, "min_clearance_at": mn[1] if mn else None,
           "min_clearance_incl_ends_mm": round(mna, 2) if mna is not None else None,
           "clearance_asked_mm": opt["clearance"], "violations": viol, "warnings": warnings, "crossings": cross,
           "inside_samples": inside, "stubs": stubs, "vias": [list(map(float, w["p"])) for w in wps if w["kind"] == "via"],
           "bend_r_target": round(opt["bend_r"], 2), "bend_r_min": round(min(bent), 2) if bent else None, "bend_r_floor": round(bend_floor, 2),
           "sharp_corners": sum(1 for x in bent if x <= 0), "corners": corner_rows,
           "exposed_mm": round(exp_mm, 1), "legs": legrows, "slack": slack(pieces, joints, couplings),
           "time_s": {"total": round(time.time() - T0, 2), "smooth": round(t_smooth, 2)},
           "settings": {k: v for k, v in opt.items() if k not in ("prefer", "avoid")}}
    set_pose({}, joints, couplings)
    if not quiet:
        for w in warnings:
            print("route: WARN " + w)
    return res


def _turn(P, i):
    if i <= 0 or i >= len(P) - 1:
        return 0.0
    a, b = (P[i] - P[i - 1]), (P[i + 1] - P[i])
    return math.degrees(a.angle(b)) if a.length and b.length else 0.0


def _limits(s):
    if s.get("continuous"):
        return [0.0, 90.0, 180.0, 270.0]
    if s.get("lo") is not None:
        h = float(s.get("home", 0.0) or 0.0)
        return sorted({float(s["lo"]), h, float(s["hi"])})
    return []


def _rel(b0, b1, J, CP):
    """Driver joints between two bodies, each with (pose -> matrix taking b1's home frame into b0's home frame)."""
    set_pose({}, J, CP)
    H0, H1 = _mw(b0), _mw(b1)

    def M(pose):
        set_pose(pose, J, CP)
        return H0 @ _mw(b0).inverted() @ _mw(b1) @ H1.inverted()
    return sorted(drivers(set(chain(b1)) ^ set(chain(b0)), CP)), M


def crossings(pieces, cut_wps, J, CP):
    """At each via where the route changes body: the cable's turn there (incoming direction against the outgoing one
    carried by the joint) at each limit of every joint between the two bodies. A via whose "dir" runs along the joint
    axis turns 0 at every pose; a cable crossing a hinge across its axis folds by the hinge angle (PR #3 review, scene
    `hinge`: 0 / 55 / 109 deg at 0 / 55 / 110), which a straight bridge hides from `slack`."""
    rows = []
    for k in range(1, len(pieces)):
        a, b = pieces[k - 1], pieces[k]
        if len(a["pts"]) < 2 or len(b["pts"]) < 2:
            continue
        din = (a["pts"][-1] - a["pts"][-2]).normalized()
        dout = (b["pts"][1] - b["pts"][0]).normalized()
        w = cut_wps[k - 1] if k - 1 < len(cut_wps) else {}
        vdir = Vector(w["dir"]).normalized() if w.get("dir") else None
        rel, M = _rel(a["joint"], b["joint"], J, CP)
        for j in rel:
            s = J.get(j) or {}
            if not s.get("axis"):
                continue
            turns = {}
            for v in _limits(s):
                d2 = (M({j: v}).to_3x3() @ dout).normalized()
                turns["%g" % v] = round(math.degrees(din.angle(d2)) if d2.length > 0 else 0.0, 1)
            set_pose({}, J, CP)
            kind, piv, u = _motion(j, J)
            on_axis = bool(vdir is not None and (kind == "prismatic" or abs(vdir.dot(u)) > math.cos(math.radians(10))))
            rows.append({"joint": j, "at": [round(x, 2) for x in a["pts"][-1]], "from": a["joint"], "to": b["joint"],
                         "turn_deg": turns, "on_axis": on_axis})
    set_pose({}, J, CP)
    return rows


def slack(pieces, J, CP):
    """Path length at each limit of every joint between consecutive pieces' bodies, with the later pieces
    moving with their body (seen from the first piece's body). slack_mm = longest minus home: how much the path
    stretches between the joint limits. It treats the via as a straight bridge, so it is 0 at an on-axis via by
    design and says nothing about the fold there (see crossings)."""
    rows = []
    if len(pieces) < 2:
        return rows
    b0 = pieces[0]["joint"]
    rel = set()
    for pc in pieces[1:]:
        rel |= drivers(set(chain(pc["joint"])) ^ set(chain(b0)), CP)
    set_pose({}, J, CP)
    home = {pc["joint"]: _mw(pc["joint"]) for pc in pieces}

    def length(pose):
        set_pose(pose, J, CP)
        M0 = _mw(b0).inverted()
        pts = []
        for pc in pieces:
            M = home[b0] @ M0 @ _mw(pc["joint"]) @ home[pc["joint"]].inverted()
            pts += [M @ Vector(p) for p in pc["pts"]]
        return _plen(pts)

    L0 = length({})
    for j in sorted(rel):
        s = J.get(j) or {}
        vals = [0.0, 90.0, 180.0, 270.0] if s.get("continuous") else ([float(s["lo"]), float(s["hi"])] if s.get("lo") is not None else [])
        if not vals:
            continue
        Ls = {a: length({j: a}) for a in vals}
        rows.append({"joint": j, "home_mm": round(L0, 1), "at": {("%g" % a): round(L, 1) for a, L in Ls.items()},
                     "unit": "mm" if s.get("kind") == "prismatic" else "deg",
                     "slack_mm": round(max(Ls.values()) - L0, 1), "range_mm": round(max(Ls.values()) - min(min(Ls.values()), L0), 1)})
    set_pose({}, J, CP)
    return rows


def cable(name, start, end, r, color="cable_blk", via=(), joint=None, lead_len=None, step=None, **kw):
    """route() then asm.cable(): one object per body (name, name_1, ...), each on its piece's joint.
    Returns (objects, result).

    lead_len goes on the cable when the route is one piece. A split route is one conductor in several objects, and
    cadcheck compares each object's own path_len with its lead_len, so the lead belongs on a cable_chains row (the
    whole run against one lead), not on each piece: res["cable_chain"] is that row, ready for checks.json."""
    from . import asm
    res = route(start, end, r, via=via, joint=joint, **kw)
    obs = []
    split = len(res["pieces"]) > 1
    for k, pc in enumerate(res["pieces"]):
        j = None if pc["joint"] == "static" else pc["joint"]
        obs.append(asm.cable(name if k == 0 else "%s_%d" % (name, k), pc["pts"], r, color, joint=j,
                             lead_len=None if split else lead_len, step=step))
    if split:
        res["cable_chain"] = {"name": name, "cables": [o.name for o in obs], "lead": lead_len}
        if not kw.get("quiet"):
            print("route: %s is split at a joint: add a cable_chains row to checks.json: %s" % (name, json.dumps(res["cable_chain"])))
    return obs, res


# ------------------------------------------------------------------ existing cables

def path_of(ob):
    """Centre line of a cable object (world, home pose) and its radius: asm.cable's cab_path / cab_r (world at
    home, the polyline cadcheck's kink and shared-run tests read), else a "path" prop in local coordinates (blends
    from this branch before it used cab_path), else the ring centroids of a curve-bevel tube (rings of k verts: two
    cap rings, then one per path point)."""
    mw = ob.matrix_world
    if ob.get("cab_path") is not None:
        f = list(ob["cab_path"])
        return [f[i:i + 3] for i in range(0, len(f), 3)], ob.get("cab_r")
    if "path" in ob.keys():
        f = list(ob["path"])
        return [list(mw @ Vector(f[i:i + 3])) for i in range(0, len(f), 3)], ob.get("r")
    V = np.array([list(mw @ v.co) for v in ob.data.vertices])
    for k in range(3, 65):
        if len(V) % k == 0 and len(V) >= 3 * k and np.allclose(V[k:2 * k], V[2 * k:3 * k], atol=1e-4):
            rings = V.reshape(-1, k, 3)[2:]
            c = rings.mean(1)
            rad = float(np.linalg.norm(rings - c[:, None, :], axis=2).mean())
            return c.tolist(), rad
    return None, None
