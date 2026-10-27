"""Joint specs and posing, shared by cadcheck (and so cadq) and cadlib.route, so that a pose means the same thing in
the checks and in the router. Before this module the router kept its own copy of cadcheck's set_pose without the
prismatic branch, and applied a slide's lo/hi (mm) as degrees of rotation (PR #3 review, scene `slide`).

    J, CP = joints.read(bpy.data.objects, cfg)          # PIV props, then cfg["joints"] / cfg["couplings"]
    joints.apply(J, CP, {"PIV_tilt": 30})               # unlisted joints go home, couplings follow

It also holds the reach bound both sweeps size their sampling with (move_terms / move_rate): how far a point of one
part can move against another per degree (or mm) of each free joint between them. The router sizes its steps and
inflation with it; cadcheck bisects between sampled poses where the sampled clearance is under it (PR #3 review,
scene `wedge`: 15 deg steps against a 2 mm arm at 70 mm reach).
"""
import bpy, math
import numpy as np
from mathutils import Vector, Euler, Matrix


def is_joint(o):
    return o is not None and o.type == 'EMPTY' and o.name.startswith("PIV_")


def spec(e, override=None):
    """One joint's spec: cadlib props (asm.joint), then the legacy "axis" prop (attempt-1 blends), then `override`
    (a checks.json "joints" row). kind is "revolute" (lo/hi/home/step in degrees) or "prismatic" (mm along +axis)."""
    s = {"axis": None, "lo": None, "hi": None, "home": 0.0, "step": None, "continuous": False}
    for k_src, k in (("joint_axis", "axis"), ("joint_lo", "lo"), ("joint_hi", "hi"), ("joint_home", "home"),
                     ("joint_step", "step"), ("joint_continuous", "continuous")):
        if k_src in e.keys():
            s[k] = e[k_src]
    if s["axis"] is None and "axis" in e.keys():
        s["axis"] = str(e["axis"]).strip()[:1].upper()
    s.update(override or {})
    if s["axis"] not in ("X", "Y", "Z"):
        s["axis"] = None
    s["base_rot"] = tuple(e.rotation_euler)
    s["kind"] = str(e.get("joint_kind", s.get("kind", "revolute")))
    s["base_loc"] = tuple(e["joint_base_loc"]) if "joint_base_loc" in e.keys() else tuple(e.location)
    return s


def read(objs=None, cfg=None):
    """(joints, couplings) for every PIV_* empty in objs (default bpy.data.objects)."""
    cfg = cfg or {}
    objs = bpy.data.objects if objs is None else objs
    J, CP = {}, dict(cfg.get("couplings", {}))
    for e in objs:
        if not is_joint(e):
            continue
        J[e.name] = spec(e, cfg.get("joints", {}).get(e.name, {}))
        if "couple_to" in e.keys() and e.name not in CP:
            CP[e.name] = {"to": e["couple_to"], "ratio": float(e.get("couple_ratio", 1.0))}
    return J, CP


def values(J, CP, pose):
    """Every joint's value for `pose` ({driver: deg or mm}): unlisted joints at home, coupled joints following."""
    vals = {n: pose.get(n, s.get("home", 0.0) or 0.0) for n, s in J.items()}
    for n, c in CP.items():
        vals[n] = vals.get(c["to"], 0.0) * c["ratio"] + c.get("offset", 0.0)
    return vals


def apply(J, CP, pose, objs=None):
    """Pose the scene. A prismatic joint slides base_loc along its own axis in mm (cadlib asm.joint(prismatic=True));
    a revolute one sets its axis' Euler angle in degrees, keeping the other base angles."""
    objs = bpy.data.objects if objs is None else objs
    vals = values(J, CP, pose)
    for n, s in J.items():
        if s["axis"] is None:
            continue
        e = objs[n]
        if s.get("kind") == "prismatic":
            ax = Vector([1.0 if i == "XYZ".index(s["axis"]) else 0.0 for i in range(3)])
            e.location = Vector(s["base_loc"]) + (Euler(s["base_rot"]).to_matrix() @ ax) * float(vals[n])
            continue
        r = list(s["base_rot"])
        r["XYZ".index(s["axis"])] = math.radians(vals[n])
        e.rotation_euler = r
    bpy.context.view_layer.update()


_EULER = ('XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX')


def world_at(name, J, vals, cache, objs=None):
    """matrix_world of object `name` with every joint at `vals` (joint name -> value, from values()), computed from the
    parent chain (parent world @ parent inverse @ basis) without posing the scene or updating the depsgraph. The
    router sweeps hundreds of poses; a view-layer update per pose made the A3 re-route 6x slower."""
    if name in cache:
        return cache[name]
    objs = bpy.data.objects if objs is None else objs
    e = objs[name]
    s = J.get(name)
    if s is not None and s["axis"] is not None and name in vals:
        ax = Vector([1.0 if i == "XYZ".index(s["axis"]) else 0.0 for i in range(3)])
        loc, scale = Vector(e.location), Vector(e.scale)
        if e.rotation_mode in _EULER:
            rot = Euler(e.rotation_euler, e.rotation_mode).to_matrix()
        else:
            rot = e.matrix_basis.to_3x3().normalized()
        if s.get("kind") == "prismatic":
            loc = Vector(s["base_loc"]) + (Euler(s["base_rot"]).to_matrix() @ ax) * float(vals[name])
        elif e.rotation_mode in _EULER:
            r = list(s["base_rot"])
            r["XYZ".index(s["axis"])] = math.radians(vals[name])
            rot = Euler(r, e.rotation_mode).to_matrix()
        basis = Matrix.LocRotScale(loc, rot, scale)
    else:
        basis = e.matrix_basis.copy()
    M = (world_at(e.parent.name, J, vals, cache, objs) @ e.matrix_parent_inverse @ basis) if e.parent else basis
    cache[name] = M
    return M


# ------------------------------------------------------------------ reach bounds (moved from cadlib.route)

def driver_of(n, CP):
    """(driver, ratio): the free joint behind n and how far n moves per unit of it."""
    k = 1.0
    while n in CP:
        k *= float(CP[n]["ratio"])
        n = CP[n]["to"]
    return n, k


def motion(j, J):
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


def ranged(j, J, CP):
    """Joint j moves: it has an axis and its driver has a range (a coupled gear follows its driver's)."""
    d = J.get(driver_of(j, CP)[0]) or {}
    return bool((J.get(j) or {}).get("axis") and d.get("axis") and (d.get("continuous") or d.get("lo") is not None))


def travel(s):
    if s.get("lo") is None:
        return 0.0
    h = float(s.get("home", 0.0) or 0.0)
    return max(abs(float(s["lo"]) - h), abs(float(s["hi"]) - h))


def axis_dist(P, piv, u):
    P = np.asarray(P, float).reshape(-1, 3) - np.asarray(piv, float)
    return np.linalg.norm(np.cross(P, np.asarray(u, float)), axis=1)


def path_rho(j, path, info, J):
    """(P0, K) such that any point p hanging off path[0] stays within |p - P0| + K of joint j's axis, whatever the
    joints in `path` do: path runs from the point's side to j through moving joints (their pivots), and each pivot is
    fixed relative to the next, so only the last pivot's distance from j's axis and the links between pivots add.
    (None, 0): no joint in between, the point's own distance from the axis is exact."""
    if not path:
        return None, 0.0
    kind, piv, u = info[j]
    K = float(axis_dist([info[path[-1]][1]], piv, u)[0])
    for a, b in zip(path, path[1:]):
        K += (info[a][1] - info[b][1]).length
    K += sum(travel(J[x]) for x in path if info[x][0] == "prismatic")
    return np.array(info[path[0]][1], float), K


def rho(P, P0, K, piv, u):
    P = np.asarray(P, float).reshape(-1, 3)
    return axis_dist(P, piv, u) if P0 is None else np.linalg.norm(P - P0, axis=1) + K


def move_terms(obj_pts, obj_chain, leg_chain, J, CP, info=None):
    """{driver: [term]}: how far a point of one side can move against the other per unit of each free (driver) joint,
    for two parts on chains obj_chain and leg_chain (joint names, nearest first), obj_pts the obstacle side's box corners
    (world, at the current pose; the leg side's points go to move_rate). The relative motion comes from the moving joints in exactly one of the two chains.
    A term is ("const", mm per mm / 2) for a slide or ("rho", rad per unit / 2, P0, K, pivot, axis, obstacle cap) for
    a revolute joint: a point at distance rho from the axis moves at most rho * step / 2 to the nearer sample. rho is
    bounded on both sides (through the pivots of the joints in between, see path_rho) and the move is at most the
    smaller. move_rate turns the terms into mm per unit; route.inflation into mm per query point. `info`: a
    {joint: motion()} cache, filled as needed (motion nudges the empty, so call at one pose)."""
    mo, ml = [j for j in obj_chain if j not in leg_chain], [j for j in leg_chain if j not in obj_chain]
    mo, ml = [j for j in mo if ranged(j, J, CP)], [j for j in ml if ranged(j, J, CP)]
    info = {} if info is None else info
    for j in mo + ml:
        if j not in info:
            info[j] = motion(j, J)
    terms_by = {}
    for j in mo + ml:
        d, k = driver_of(j, CP)
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
        P0, K = path_rho(j, qpath, info, J)
        O0, OK = path_rho(j, opath, info, J)
        ocap = float(rho(obj_pts, O0, OK, piv, u).max())
        terms_by.setdefault(d, []).append(("rho", abs(k) * math.pi / 360.0, P0, K, piv, u, ocap))
    return terms_by


def move_rate(terms, leg_pts):
    """mm that the worst of leg_pts can move toward the nearer sample per unit of driver step (move_terms' terms of
    one driver): half the most a point moves between two samples one unit apart."""
    return sum(t[1] if t[0] == "const" else t[1] * min(t[6], float(rho(leg_pts, t[2], t[3], t[4], t[5]).max())) for t in terms)
