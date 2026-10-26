"""Cable router: occupancy grid from the solids, A* with wall, exposure and turn costs, then line-of-sight
shortcuts and bend-radius fillets. The points go straight into asm.cable(name, pts, r, ..., lead_len=), so
cadcheck's cable checks (overlap, exposure, lead length) apply to the result.

    from cadlib import route as RT
    res = RT.route(a, b, 1.6, via=[{"at": (0, 0, 60), "dir": (0, 0, 1), "len": 20}], clearance=1.0)
    A.cable("CAB_12v_ctrl", res["pts"], 1.6, "cable_red", lead_len=200)
    obs, res = RT.cable("CAB_bus", a, b, 1.4, "cable_wht", via=[...])     # route + asm.cable, one object per body
    cad q model.blend route CAB_12v_ctrl --config checks.json --save out.blend   # re-route an existing cable

Why: every v1 attempt had cable review issues (FINDINGS A1-F12 routes, A2-F8 bare run, A3-F7 visible in a notch),
and hand-typed waypoints put 165.6 mm3 of five A3 cables inside solids (CAB_uart 113.4, CAB_12v_ctrl 38.0 in
BUY_servo_controller; cadcheck's 1331.9 for the latter was an open-tube boolean artefact, docs/features/cable-router.md).

Model:
- Grid: cells of `cell` mm over the leg's endpoints plus `margin`. A cell is blocked when a solid surface is closer
  than r + clearance (BVH find_nearest) or the cell is inside a solid (per-object column ray parity). Solids on
  another body are swept over the joints between the two bodies, so the route clears them at every pose.
- Search: A* over 26 neighbours. Cost per mm: 1 within `wall_band` of the blocked band or in a `prefer` box,
  1 + w_open in open space, plus w_exposed where the cell is visible from outside (cadcheck's viewer-direction
  rule on a 2-cell lattice), plus w_turn mm per radian of turn.
- Vias: points the cable must pass. {"at": p, "dir": d, "len": L} forces a straight run (a hub bore), and
  "joint" puts the legs after it on another body; the result then has one piece per body and a slack row.
- Smoothing: shortcuts checked against exact clearance that never enter costlier cells than the A* path used,
  then a fillet of bend_r at each corner, shrunk (or the corner pushed outward) where the arc would lose
  clearance. The smallest radius used is reported as bend_r_min.
"""
import bpy, heapq, math, time
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

DEFAULTS = {"cell": 2.0, "clearance": 1.0, "margin": 20.0, "bend_r": None, "wall_band": None, "lead_in": None,
            "w_open": 0.5, "w_exposed": 8.0, "w_turn": 3.0, "w_stub": 3.0, "sweep_step": 15.0, "max_poses": 13,
            "view_frac": 0.10, "view_z": -0.2, "min_escape": 8, "prefer": [], "avoid": [], "exposure": True}
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


def is_joint(o):
    return o is not None and o.type == 'EMPTY' and o.name.startswith("PIV_")


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
    """(joints, couplings) the way cadcheck reads them: PIV props, then the config's "joints"/"couplings"."""
    cfg = cfg or {}
    J, CP = {}, dict(cfg.get("couplings", {}))
    for e in bpy.data.objects:
        if not is_joint(e):
            continue
        s = {"axis": None, "lo": None, "hi": None, "home": 0.0, "step": None, "continuous": False}
        for ks, k in (("joint_axis", "axis"), ("joint_lo", "lo"), ("joint_hi", "hi"), ("joint_home", "home"),
                      ("joint_step", "step"), ("joint_continuous", "continuous")):
            if ks in e.keys():
                s[k] = e[ks]
        if s["axis"] is None and "axis" in e.keys():
            s["axis"] = str(e["axis"]).strip()[:1].upper()
        s.update(cfg.get("joints", {}).get(e.name, {}))
        if s["axis"] not in ("X", "Y", "Z"):
            s["axis"] = None
        s["base_rot"] = tuple(e.rotation_euler)
        J[e.name] = s
        if "couple_to" in e.keys() and e.name not in CP:
            CP[e.name] = {"to": e["couple_to"], "ratio": float(e.get("couple_ratio", 1.0))}
    return J, CP


def set_pose(pose, J, CP):
    vals = {n: pose.get(n, s.get("home", 0.0) or 0.0) for n, s in J.items()}
    for n, c in CP.items():
        vals[n] = vals.get(c["to"], 0.0) * c["ratio"] + c.get("offset", 0.0)
    for n, s in J.items():
        if s["axis"] is None:
            continue
        r = list(s["base_rot"])
        r["XYZ".index(s["axis"])] = math.radians(vals[n])
        bpy.data.objects[n].rotation_euler = r
    bpy.context.view_layer.update()


def drivers(names, CP):
    out = set()
    for n in names:
        while n in CP:
            n = CP[n]["to"]
        out.add(n)
    return frozenset(out)


def _samples(s, step):
    if not s or s["axis"] is None:
        return [0.0]
    if s.get("continuous"):
        return list(np.arange(0.0, 360.0 - 1e-6, max(step, 30.0)))
    if s["lo"] is None or s["hi"] is None:
        return [s.get("home", 0.0) or 0.0]
    lo, hi = float(s["lo"]), float(s["hi"])
    st = max(s.get("step") or step, (hi - lo) / 12.0, 1e-3)
    v = list(np.arange(lo, hi + 1e-9, st))
    return v + ([hi] if abs(v[-1] - hi) > 1e-6 else [])


def pose_grid(drv, J, opt):
    per = [_samples(J.get(j), opt["sweep_step"]) for j in sorted(drv)]
    while math.prod(len(p) for p in per) > opt["max_poses"]:
        i = max(range(len(per)), key=lambda k: len(per[k]))
        if len(per[i]) <= 3:
            break
        per[i] = [per[i][int(round(t))] for t in np.linspace(0, len(per[i]) - 1, max(3, len(per[i]) - 2))]
    out = [{}]
    for j, vals in zip(sorted(drv), per):
        out = [dict(p, **{j: float(a)}) for p in out for a in vals]
    return out


def _mw(name):
    o = bpy.data.objects.get(name) if name and name != "static" else None
    return o.matrix_world.copy() if o is not None else Matrix.Identity(4)


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


def tree(objs):
    """One BVH over all `objs` in world coordinates at the current pose (None when empty)."""
    vs, ts, off = [], [], 0
    for o in objs:
        co, t = _tris(o)
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


def _nearest(G, tr, R, cells, d, ins, M=None):
    """d[cells] = min(d, distance to tr) for cells within R; ins[c] |= the nearest face faces away (inside).
    The sign test catches solids that column parity can't (touching shells: A3's controller header block).
    M maps grid points into tr's frame."""
    P = G.xyz[cells]
    if M is not None:
        A = np.array(M)
        P = P @ A[:3, :3].T + A[:3, 3]
    fn = tr.find_nearest
    for c, p in zip(cells.tolist(), P.tolist()):
        h = fn(p, R)
        if h[0] is not None:
            if h[3] < d[c]:
                d[c] = h[3]
            if (p[0] - h[0][0]) * h[1][0] + (p[1] - h[0][1]) * h[1][1] + (p[2] - h[0][2]) * h[1][2] < -1e-6:
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
        lo = np.minimum(a, b) - opt["margin"]
        hi = np.maximum(a, b) + opt["margin"]
        G = self.G = Grid(lo, hi, h)
        # obstacles on this leg's body (or with no joint between) are fixed; the rest sweep
        mine = drivers(set(chain(legbody)), CP)
        fixed, moving = [], {}
        for o in obstacles:
            rel = drivers(set(chain(o)), CP) ^ mine
            (moving.setdefault(rel, []) if rel and any(J.get(j, {}).get("axis") for j in rel) else fixed).append(o)
        set_pose({}, J, CP)
        self.fixed_tree = tree(fixed)
        d = np.full(G.N, np.inf)
        sign_in = np.zeros(G.N, bool)
        live = np.nonzero(~G.border)[0]
        if self.fixed_tree:
            _nearest(G, self.fixed_tree, self.R + band, live, d, sign_in)
        glo, ghi = G.lo - self.R - band, G.lo + G.n * h + self.R + band
        self.sweep = []
        Mb_home = _mw(legbody)
        for rel, objs in moving.items():
            for pose in pose_grid(rel, J, self.opt):
                set_pose(pose, J, CP)
                M = _mw(legbody) @ Mb_home.inverted()     # leg frame (world at home) -> world at this pose
                Minv = np.array(M.inverted())
                near = []
                for o in objs:                           # only solids that reach the grid at this pose
                    blo, bhi = _bbox(o)
                    cs = np.array([[x, y, z, 1] for x in (blo[0], bhi[0]) for y in (blo[1], bhi[1]) for z in (blo[2], bhi[2])])
                    cl = (cs @ Minv.T)[:, :3]
                    if (cl.max(0) >= glo).all() and (cl.min(0) <= ghi).all():
                        near.append(o)
                tr = tree(near)
                if tr is None:
                    continue
                bb = np.array([c for o in near for c in _bbox(o)])
                corners = np.array([[x, y, z, 1] for x in (bb[:, 0].min(), bb[:, 0].max())
                                    for y in (bb[:, 1].min(), bb[:, 1].max()) for z in (bb[:, 2].min(), bb[:, 2].max())])
                cl = (corners @ Minv.T)[:, :3]
                sel = live[((G.xyz[live] >= cl.min(0) - self.R - band) & (G.xyz[live] <= cl.max(0) + self.R + band)).all(1)]
                _nearest(G, tr, self.R + band, sel, d, sign_in, M)
                self.sweep.append((pose, tr, M))
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

    def clear(self, p):
        """Exact clearance of a cable centred at p: surface distance minus r, negative (-(d + r)) when p is inside
        a solid (nearest face points away), worst over the swept poses."""
        best = 1e9
        for tr, M in ([(self.fixed_tree, None)] if self.fixed_tree else []) + [(t, M) for _, t, M in self.sweep]:
            q = Vector(p) if M is None else M @ Vector(p)
            hh = tr.find_nearest(q, self.R + 5.0)
            if hh[0] is not None:
                dd = hh[3] - self.r if (q - hh[0]).dot(hh[1]) >= -1e-6 else -hh[3] - self.r
                best = min(best, dd)
        return best

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
            if self.clear(p) < need:
                return False
        return True

    def entry(self, p, mode=0):
        """{cell: cost} where the search may start or end for waypoint p. mode 0: its own cell when p is clear.
        Otherwise free cells within lead_in, at w_stub * W per mm of the straight stub: mode 1 only stubs that go no
        deeper into a solid than p already is, mode 2 any stub (reported). Stubs serve connectors inside a part's
        envelope (A3's CAB_12v_ctrl ends inside the controller's header block) and points sealed in a pocket
        (A3's CAB_uart ends under the controller board, where the hand route also cut the board). Only the 200
        nearest cells are tried. Empty when nothing is free nearby."""
        G = self.G
        c = G.at(p)
        if mode == 0 and not self.blocked[c] and self.clear(p) >= self.opt["clearance"]:
            return {c: 0.0}
        lead = self.opt["lead_in"] or (self.R + 4 * self.h)
        k = int(math.ceil(lead / self.h))
        ijk = G.ijk_of(p)
        rng = [np.arange(max(1, ijk[a] - k), min(G.n[a] - 1, ijk[a] + k + 1)) for a in range(3)]
        cells = G.flat(np.stack(np.meshgrid(*rng, indexing="ij"), -1).reshape(-1, 3))
        cells = cells[~self.blocked[cells]]
        dd = np.linalg.norm(G.xyz[cells] - np.asarray(p, float), axis=1)
        order = np.argsort(dd)[:200]
        floor = min(self.clear(p), 0.0) - 1e-3
        pv = Vector(p)
        out = {}
        for c, x in zip(cells[order].tolist(), dd[order].tolist()):
            if x > lead + 1e-6:
                break
            q = Vector(G.xyz[c])
            m = max(1, int(math.ceil(x / 0.5)))
            if mode == 2 or all(self.clear(pv.lerp(q, s / m)) >= floor for s in range(1, m + 1)):
                out[c] = x * self.opt["w_stub"] * float(self.W[c])
        return out


def _shortcut(leg, P, Wp, stub_a, stub_b):
    out, i, n = [P[0]], 0, len(P)
    while i < n - 1:
        j, k = i + 1, i + 2
        while k < n and leg.seg_ok(P[i], P[k], max(Wp[i:k + 1]), skip_a=(stub_a + leg.h) if i == 0 else 0.0,
                                   skip_b=(stub_b + leg.h) if k == n - 1 else 0.0):
            j, k = k, k + 1
        out.append(P[j])
        i = j
    return out


def _merge_short(leg, P, stub_a, stub_b):
    """Drop a vertex between short segments (< 2.5 cells, the staircase A* leaves at a turn) when the joined
    segment keeps the clearance; longer segments leave room for the bend radius (A3 CAB_12v_mg: 2.5 -> 8 mm)."""
    P = list(P)
    i = 1
    while i < len(P) - 1:
        if min((P[i] - P[i - 1]).length, (P[i + 1] - P[i]).length) < 2.5 * leg.h and \
                leg.seg_ok(P[i - 1], P[i + 1], None, skip_a=(stub_a + leg.h) if i == 1 else 0.0,
                           skip_b=(stub_b + leg.h) if i == len(P) - 2 else 0.0):
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


def fillet(P, bend_r, check, fixed=()):
    """Round each corner of polyline P with radius bend_r where it fits (tangent lengths share each segment),
    keeping check(points, corner) true: push the corner outward (up to 3 times), else shrink the radius by 0.7
    down to 0.5 mm, then leave it sharp. Returns (points, radius per interior vertex)."""
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
            if s > L:
                f[i], f[i + 1] = min(f[i], L / s), min(f[i + 1], L / s)
        return [t[i] * f[i] / tt[i] if tt[i] > 1e-6 else 0.0 for i in range(n)]

    def arc(i, R):
        return _arc(P[i], (P[i] - P[i - 1]).normalized(), (P[i + 1] - P[i]).normalized(), R[i])

    def shrink(i, R):
        want[i] = R[i] * 0.7 if R[i] * 0.7 >= 0.5 else 0.0

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
                    {"p": v["at"], "body": nb, "kind": "via", "straight": True, "from": prev},
                    {"p": a1, "body": nb, "kind": "run"}]
        else:
            wps.append({"p": v["at"], "body": nb, "kind": "via", "from": prev})
    wps.append({"p": Vector(end), "body": None, "kind": "end"})
    return wps


def route(start, end, r, via=(), joint=None, obstacles=None, joints=None, couplings=None, cfg=None, **kw):
    """Route a cable of radius r from start to end through each via. Returns a JSON-safe dict: pts (the list for
    asm.cable), pieces [{joint, pts}] (one per body when a via changes body), length_mm, min_clearance_mm,
    stubs (endpoints that sit in the clearance band), bend_r_min, exposed_mm, slack rows, time_s and grid stats.

    joint: the body of the first leg (the joint you would give asm.cable). obstacles: default Printed +
    Purchased + Fasteners. joints/couplings: scene_joints(cfg) when None. kw overrides DEFAULTS
    (cell, clearance, margin, bend_r, w_open, w_exposed, w_turn, prefer=[(lo, hi)], avoid=[(lo, hi)], ...)."""
    T0 = time.time()
    opt = dict(DEFAULTS, **kw)
    opt["bend_r"] = float(opt["bend_r"]) if opt["bend_r"] is not None else 5.0 * r
    if joints is None:
        joints, cp = scene_joints(cfg)
        couplings = cp if couplings is None else couplings
    couplings = couplings or {}
    obstacles = obstacles if obstacles is not None else mesh_objs(OBSTACLES)
    set_pose({}, joints, couplings)
    tv = tree(mesh_objs(VIEWERS)) if opt["exposure"] else None
    wps = _waypoints(start, end, via, joint, opt["cell"])
    legrows, stubs, legs = [], [], []
    poly, seg_leg, wp_at = [wps[0]["p"].copy()], [], [0]
    for k in range(len(wps) - 1):
        a, b, lb = wps[k]["p"], wps[k + 1]["p"], wps[k]["body"]
        leg = None
        if wps[k].get("straight"):
            seg = [a, b]
        else:
            leg = None
            for grow, mode in ((1, 0), (1, 1), (1, 2), (2, 2)):   # clear ends, safe stubs, any stub, a bigger box
                o2 = dict(opt, margin=opt["margin"] * grow)
                if leg is None or leg.opt["margin"] != o2["margin"]:
                    leg = Leg(np.array(a), np.array(b), r, lb, obstacles, joints, couplings, o2, tv)
                src, dst = leg.entry(a, mode), leg.entry(b, mode)
                if not src or not dst:
                    raise RuntimeError("route: %s is buried: no free cell within lead_in (r + clearance = %.2f)" % (
                        [round(x, 1) for x in (a if not src else b)], leg.R))
                t0 = time.time()
                cells, nexp = astar(leg.G, leg.blocked, leg.W, src, dst, b, opt["w_turn"])
                ts = time.time() - t0
                if cells is not None:
                    break
            if cells is None:
                raise RuntimeError("route: no path from %s to %s with r + clearance = %.2f mm on a %.1f mm grid; try a "
                                   "smaller cell or clearance, or a via" % ([round(x, 1) for x in a], [round(x, 1) for x in b], leg.R, leg.h))
            sa = (Vector(leg.G.xyz[cells[0]]) - a).length if src[cells[0]] else 0.0
            sb = (Vector(leg.G.xyz[cells[-1]]) - b).length if dst[cells[-1]] else 0.0
            P = [a] + [Vector(leg.G.xyz[c]) for c in cells] + [b]
            Wp = [leg.W[cells[0]]] + [float(leg.W[c]) for c in cells] + [leg.W[cells[-1]]]
            t0 = time.time()
            seg = _merge_short(leg, _shortcut(leg, P, Wp, sa, sb), sa, sb)
            legrows.append({"body": lb, "dims": leg.G.n.tolist(), "cells": int(leg.G.N), "margin": o2["margin"],
                            "blocked_frac": round(float(leg.blocked.mean()), 3), "swept_poses": len(leg.sweep),
                            "expanded": nexp, "grid_s": round(leg.t_grid, 2), "exposure_s": round(leg.t_exposure, 2),
                            "search_s": round(ts, 2), "shortcut_s": round(time.time() - t0, 2)})
            for p, s, c in ((a, sa, cells[0]), (b, sb, cells[-1])):
                if s:
                    q = Vector(leg.G.xyz[c])
                    m = max(1, int(math.ceil(s / 0.5)))
                    stubs.append({"at": [round(x, 2) for x in p], "stub_mm": round(s, 1), "clearance_mm": round(leg.clear(p), 2),
                                  "stub_min_clearance_mm": round(min(leg.clear(p.lerp(q, k / m)) for k in range(m + 1)), 2)})
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
        s = min(1.5, 0.25 * din.length, 0.25 * dout.length)
        poly[i:i + 1] = [poly[i] - u * s, poly[i].copy(), poly[i] + u * s]
        seg_leg[i - 1:i] = [seg_leg[i - 1]] * 2
        seg_leg[i + 1:i + 1] = [seg_leg[i + 1]]
        for kk in range(k, len(wp_at)):
            wp_at[kk] += 1 if kk == k else 2
    ends = [Vector(start), Vector(end)]
    skip = max([s["stub_mm"] for s in stubs] + [0.0]) + opt["cell"]

    def clear_by(p, cand):
        """Exact clearance of p for the legs in cand whose grid holds it (None if none does); -r inside a solid."""
        out = None
        for leg in cand:
            if leg is None:
                continue
            ijk = (np.asarray(p, float) - leg.G.lo) / leg.h
            if (ijk >= 0.5).all() and (ijk <= leg.G.n - 1.5).all():
                c = -leg.r if leg.inside[leg.G.at(p)] else leg.clear(p)
                out = c if out is None else min(out, c)
        return out

    def check(pts, i):
        cand = {seg_leg[j] for j in (i - 1, i) if 0 <= j < len(seg_leg)}
        for p in pts:
            if min((p - e).length for e in ends) < skip:
                continue
            c = clear_by(p, cand)
            if c is not None and c < opt["clearance"]:
                return False
        return True

    t0 = time.time()
    fixed = {wp_at[k] for k, w in enumerate(wps) if w["kind"] in ("run", "via")}
    pts, radii = fillet(poly, opt["bend_r"], check, fixed=fixed)
    corner_rows = [{"at": [round(x, 1) for x in poly[i + 1]], "turn_deg": round(_turn(poly, i + 1), 1), "r": round(x, 2)}
                   for i, x in enumerate(radii) if _turn(poly, i + 1) > 1.0]
    t_smooth = time.time() - t0
    # one piece per body: split at the vias that change body (they stay exact vertices of pts)
    cuts = [w["p"] for w in wps if w["kind"] == "via" and w["body"] != w["from"]]
    bodies = [wps[0]["body"]] + [w["body"] for w in wps if w["kind"] == "via" and w["body"] != w["from"]]
    pieces, cur = [{"joint": bodies[0], "pts": []}], 0
    for p in pts:
        pieces[-1]["pts"].append(p)
        if cur < len(cuts) and (p - cuts[cur]).length < 1e-6:
            cur += 1
            pieces.append({"joint": bodies[cur], "pts": [p]})
    body_legs = {}
    for leg, w in zip(legs, wps):
        body_legs.setdefault(w["body"], []).append(leg)
    # stats: exact clearance every 0.5 mm, inside cells, exposure every 2 mm on the centre line (cadcheck's rule)
    clr_all, clr_mid, inside, exp_mm = [], [], 0, 0.0
    for pc in pieces:
        q = pc["pts"]
        for i in range(len(q) - 1):
            L = (q[i + 1] - q[i]).length
            m = max(1, int(math.ceil(L / 0.5)))
            for s in range(m + 1):
                p = q[i].lerp(q[i + 1], s / m)
                c = clear_by(p, body_legs.get(pc["joint"], []))
                if c is None:
                    continue
                clr_all.append(c)
                if min((p - e).length for e in ends) >= skip:
                    clr_mid.append((c, [round(x, 1) for x in p]))
                    inside += int(any(lg is not None and lg.inside[lg.G.at(p)] for lg in body_legs.get(pc["joint"], [])))
            if tv is not None:
                m2 = max(1, int(math.ceil(L / 2.0)))
                exp_mm += sum(L / m2 for s in range(m2) if exposed(tv, q[i].lerp(q[i + 1], (s + 0.5) / m2), opt))
    bent = [x for i, x in enumerate(radii) if _turn(poly, i + 1) > 1.0]
    res = {"pts": [[round(x, 3) for x in p] for p in pts],
           "pieces": [{"joint": pc["joint"], "pts": [[round(x, 3) for x in p] for p in pc["pts"]]} for pc in pieces],
           "r": r, "length_mm": round(_plen(pts), 1), "straight_mm": round((ends[1] - ends[0]).length, 1),
           "min_clearance_mm": round(min(clr_mid)[0], 2) if clr_mid else None, "min_clearance_at": min(clr_mid)[1] if clr_mid else None,
           "min_clearance_incl_ends_mm": round(min(clr_all), 2) if clr_all else None,
           "inside_samples": inside, "stubs": stubs, "vias": [list(map(float, w["p"])) for w in wps if w["kind"] == "via"],
           "bend_r_target": round(opt["bend_r"], 2), "bend_r_min": round(min(bent), 2) if bent else None,
           "sharp_corners": sum(1 for x in bent if x <= 0), "corners": corner_rows,
           "exposed_mm": round(exp_mm, 1), "legs": legrows, "slack": slack(pieces, joints, couplings),
           "time_s": {"total": round(time.time() - T0, 2), "smooth": round(t_smooth, 2)},
           "settings": {k: v for k, v in opt.items() if k not in ("prefer", "avoid")}}
    set_pose({}, joints, couplings)
    return res


def _turn(P, i):
    if i <= 0 or i >= len(P) - 1:
        return 0.0
    a, b = (P[i] - P[i - 1]), (P[i + 1] - P[i])
    return math.degrees(a.angle(b)) if a.length and b.length else 0.0


def slack(pieces, J, CP):
    """Path length at each limit of every joint between consecutive pieces' bodies, with the later pieces
    moving with their body (seen from the first piece's body). slack_mm = longest minus home: the extra lead
    a cable needs to reach both joint extremes."""
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
        if s.get("continuous"):
            vals = [0.0, 90.0, 180.0, 270.0]
        elif s.get("lo") is not None:
            vals = [float(s["lo"]), float(s["hi"])]
        else:
            continue
        Ls = {a: length({j: a}) for a in vals}
        rows.append({"joint": j, "home_mm": round(L0, 1), "at_deg": {("%g" % a): round(L, 1) for a, L in Ls.items()},
                     "slack_mm": round(max(Ls.values()) - L0, 1), "range_mm": round(max(Ls.values()) - min(min(Ls.values()), L0), 1)})
    set_pose({}, J, CP)
    return rows


def cable(name, start, end, r, color="cable_blk", via=(), joint=None, lead_len=None, step=None, **kw):
    """route() then asm.cable(): one object per body (name, name_1, ...), each on its piece's joint.
    Returns (objects, result)."""
    from . import asm
    res = route(start, end, r, via=via, joint=joint, **kw)
    obs = []
    for k, pc in enumerate(res["pieces"]):
        j = None if pc["joint"] == "static" else pc["joint"]
        obs.append(asm.cable(name if k == 0 else "%s_%d" % (name, k), pc["pts"], r, color, joint=j,
                             lead_len=lead_len if k == 0 and len(res["pieces"]) == 1 else None, step=step))
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
