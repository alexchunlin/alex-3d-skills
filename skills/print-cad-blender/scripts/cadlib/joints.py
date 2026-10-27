"""Joint specs and posing, shared by cadcheck (and so cadq) and cadlib.route, so that a pose means the same thing in
the checks and in the router. Before this module the router kept its own copy of cadcheck's set_pose without the
prismatic branch, and applied a slide's lo/hi (mm) as degrees of rotation (PR #3 review, scene `slide`).

    J, CP = joints.read(bpy.data.objects, cfg)          # PIV props, then cfg["joints"] / cfg["couplings"]
    joints.apply(J, CP, {"PIV_tilt": 30})               # unlisted joints go home, couplings follow
"""
import bpy, math
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
