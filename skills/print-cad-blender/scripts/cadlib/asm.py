"""Assembly conventions: collections, PRT/BUY/FST/CAB naming, joints (PIV_*), fasteners, cables, manifest.

Conventions (what cadcheck and the web viewer rely on):
- Collections Printed / Purchased / Fasteners / Cables. Names PRT_<part>, BUY_<part>, FST_<what>_<n>, CAB_<what>.
- Moving links hang under PIV_<joint> empties. A joint stores axis, limits, home and step as custom
  properties, so checks sweep the real range (attempt 1 checked only 0/22.5/45 deg: FINDINGS A1-F5).
- Mesh data is baked in world coordinates at the home pose; parenting keeps the world placement.
- Every printed part carries stl, print_rot (3x3), orient, supports, infill. The STL export and the
  bed-fit/overhang checks both use print_rot, so they cannot disagree.
- Fasteners carry fst_head / fst_dir / fst_len (local), so checks know which end is the head.
- write_manifest() dumps parts, joints, fasteners, cables, features and parameters as JSON, so a
  reviewer doesn't have to reverse-engineer the script (attempt 1: 7 calls reading code, A1-T8).
"""
import bpy, json, math, os
from mathutils import Vector, Matrix
from . import geom, features

COLL_NAMES = {'PRT': 'Printed', 'BUY': 'Purchased', 'FST': 'Fasteners', 'CAB': 'Cables'}
PARTS, JOINTS, MATS, COLLS = {}, {}, {}, {}
PARAMS = {}

PALETTE = {
    # two coordinated PLA colours plus neutral purchased parts (brief: restrained palette)
    "pla_a": (0.82, 0.80, 0.76, 1.0),     # warm light grey
    "pla_b": (0.77, 0.33, 0.17, 1.0),     # terracotta (alex-style light accent #c4532a)
    "buy": (0.22, 0.23, 0.25, 1.0),
    "buy_metal": (0.62, 0.63, 0.65, 1.0),
    "pcb": (0.10, 0.32, 0.20, 1.0),
    "screw": (0.55, 0.56, 0.58, 1.0),
    "cable_red": (0.70, 0.12, 0.10, 1.0), "cable_blk": (0.08, 0.08, 0.08, 1.0),
    "cable_wht": (0.90, 0.90, 0.88, 1.0), "cable_yel": (0.85, 0.70, 0.15, 1.0),
}


def new_scene(params=None):
    """Empty scene in mm. `params` (dict of the script's named parameters) goes into the manifest."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 0.001
    sc.unit_settings.length_unit = 'MILLIMETERS'
    for d in (PARTS, JOINTS, MATS, COLLS, PARAMS):
        d.clear()
    features.LOG.clear()
    if params:
        PARAMS.update({k: v for k, v in params.items() if isinstance(v, (int, float, str, bool, list, tuple, dict))})
        # in the .blend too, so cadcheck can evaluate "=EXPR" rows on a copied blend without its manifest
        sc["cad_params"] = json.dumps(PARAMS, default=str)
    geom.scratch()


def coll(name):
    if name not in COLLS:
        c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
        if c.name not in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.link(c)
        COLLS[name] = c
    return COLLS[name]


def mat(rgba):
    if isinstance(rgba, str):
        rgba = PALETTE[rgba]
    key = tuple(round(x, 3) for x in rgba)
    if key not in MATS:
        m = bpy.data.materials.new("M_%d" % len(MATS))
        m.diffuse_color = rgba
        m.roughness = 0.6
        MATS[key] = m
    return MATS[key]


# ------------------------------------------------------------------ joints

def joint(name, loc, axis, lo=None, hi=None, parent=None, home=0.0, step=None, continuous=False,
          couple_to=None, couple_ratio=1.0, prismatic=False):
    """PIV_<name> empty at world `loc`, rotating about its local `axis` ('X', 'Y' or 'Z').
    lo/hi in degrees (the range the mechanism must reach); continuous=True for wheels;
    couple_to makes it follow another joint (gears): angle = couple_ratio * other.
    prismatic=True makes it a slide along +axis instead, with lo/hi/home/step in mm: a gate, a drawer, a plunger.
    v2 A2 and A3 left the feeder gate's open state out of every sweep because cadlib had no slide joint, and the
    reviewer moved the gate by hand in copies of the blend (FINDINGS V2A2-T4, V2A3-T6)."""
    assert name.startswith("PIV_"), "joint names start with PIV_"
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = 'ARROWS'
    e.empty_display_size = 25
    e.location = loc
    bpy.context.scene.collection.objects.link(e)
    if parent:
        p = JOINTS[parent]
        bpy.context.view_layer.update()
        e.parent = p
        e.matrix_parent_inverse = p.matrix_world.inverted()
    e["joint_axis"] = axis
    if lo is not None:
        e["joint_lo"], e["joint_hi"] = float(lo), float(hi)
    e["joint_home"] = float(home)
    if step:
        e["joint_step"] = float(step)
    e["joint_continuous"] = bool(continuous)
    if prismatic:
        assert not continuous, "a prismatic joint can't be continuous"
        e["joint_kind"] = "prismatic"
        e["joint_base_loc"] = [float(c) for c in e.location]
    if couple_to:
        e["couple_to"], e["couple_ratio"] = couple_to, float(couple_ratio)
    JOINTS[name] = e
    bpy.context.view_layer.update()
    return e


def set_pose(**deg):
    """set_pose(PIV_pan=30, PIV_tilt=45). Unlisted joints go home; coupled joints follow."""
    vals = {n: deg.get(n, e.get("joint_home", 0.0)) for n, e in _all_joints().items()}
    for n, e in _all_joints().items():
        if "couple_to" in e.keys():
            vals[n] = vals.get(e["couple_to"], 0.0) * e.get("couple_ratio", 1.0)
    for n, e in _all_joints().items():
        if e.get("joint_kind") == "prismatic":
            v = [0.0, 0.0, 0.0]
            v["XYZ".index(e["joint_axis"])] = float(vals[n])
            e.location = Vector(e["joint_base_loc"]) + Vector(v)
            continue
        r = [0.0, 0.0, 0.0]
        r["XYZ".index(e["joint_axis"])] = math.radians(vals[n])
        e.rotation_euler = r
    bpy.context.view_layer.update()


def _all_joints():
    return {o.name: o for o in bpy.data.objects if o.type == 'EMPTY' and o.name.startswith("PIV_") and "joint_axis" in o.keys()}


def body_of(ob):
    p = ob.parent
    while p is not None:
        if p.name.startswith("PIV_"):
            return p.name
        p = p.parent
    return "static"


# ------------------------------------------------------------------ parts

def part(ob, name, kind, color, joint=None, **info):
    """Register a finished solid: rename, collection, material, parent to a joint, store metadata.

    Printed parts need stl=, print_rot= (3x3 Matrix taking world-at-home into print orientation,
    Z up from the bed), orient= (one line a human can follow), supports= ("no" / "yes: where"),
    infill= (percent). Purchased parts should give mass_g= for the tip check and src= (datasheet,
    STEP file or measurement) so dimensions stay traceable.
    """
    assert name.startswith(kind + "_"), "%s must start with %s_" % (name, kind)
    if kind == 'PRT':
        missing = [k for k in ("stl", "print_rot", "orient", "supports") if k not in info]
        assert not missing, "%s is missing %s" % (name, missing)
        nm, vol = geom.solid_stats(ob)
        if nm or vol <= 0:
            raise geom.CSGError("%s is not a closed solid (non-manifold edges %d, volume %.1f)" % (name, nm, vol))
    ob.name = name
    ob.data.name = name
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    coll(COLL_NAMES[kind]).objects.link(ob)
    ob.data.materials.clear()
    ob.data.materials.append(mat(color))
    if joint:
        p = JOINTS[joint]
        ob.parent = p
        ob.matrix_parent_inverse = p.matrix_world.inverted()
    info = dict(info, kind=kind, joint=joint or "static")
    if "print_rot" in info:
        R = info["print_rot"]
        ob["print_rot"] = [list(R[i]) for i in range(3)]
        info["print_rot"] = [list(map(float, R[i])) for i in range(3)]
    for k, v in info.items():
        if isinstance(v, (int, float, str, bool)):
            ob[k] = v
    PARTS[name] = info
    return ob


# common print rotations (world-at-home -> print)
R_ID = Matrix.Identity(3)
R_FLIP = Matrix.Rotation(math.pi, 3, 'X')            # upside down
R_NX_DOWN = Matrix.Rotation(-math.pi / 2, 3, 'Y')    # world -X face onto the bed
R_PX_DOWN = Matrix.Rotation(math.pi / 2, 3, 'Y')     # world +X face onto the bed
R_NY_DOWN = Matrix.Rotation(math.pi / 2, 3, 'X')     # world -Y face onto the bed
R_PY_DOWN = Matrix.Rotation(-math.pi / 2, 3, 'X')    # world +Y face onto the bed


# ------------------------------------------------------------------ fasteners and cables

FASTENER_SPECS = {
    # spec: (shank d, head d, head h)
    "M3_cap": (3.0, 5.5, 3.0), "M3_pan": (3.0, 6.0, 2.4), "M3_csk": (3.0, 6.0, 1.7),
    "M3_selftap_pan": (3.0, 6.0, 2.4), "M2_pan": (2.0, 3.8, 1.3),
    # ISO 4762 / ISO 7045 M2.5 (MotorGo board screws; the v2 A1 finisher looked this table up and found none)
    "M2.5_cap": (2.5, 4.5, 2.5), "M2.5_pan": (2.5, 5.0, 1.75),
    # ISO 4017 hex head, 5.5 AF x 2.0, as a round head across flats (v2 A3 modelled a hex stud as M3_cap, V2A3-F6)
    "M3_hex": (3.0, 5.5, 2.0),
}


def fastener(name, at, into, length, spec="M3_cap", joint=None, host=None, step=None):
    """Screw whose head bears at `at` and whose shank runs `length` mm along `into`
    (same placement as features.screw_hole). host = the part the thread bites into;
    step = the assembly step that drives it (cadcheck uses it for tool access)."""
    d, hd, hh = FASTENER_SPECS[spec]
    w = Vector(into).normalized()
    if spec.endswith("csk"):
        sh = geom.cyl(name, (0, 0), d / 2, 0, length, 'Z', n=12)
        hdo = geom.cone(name + "h", (0, 0), hd / 2, d / 2, 0, hh, 'Z', n=16)
    else:
        sh = geom.cyl(name, (0, 0), d / 2, 0, length, 'Z', n=12)
        hdo = geom.cyl(name + "h", (0, 0), hd / 2, -hh, 0, 'Z', n=16)
    ob = geom.join(name, [sh, hdo])
    geom.xform(ob, features._frame(at, w))
    ob = part(ob, name, 'FST', "screw", joint, part="%s x %g" % (spec, length), host=host or "", step=step or "")
    # stored in the object's local frame (mesh is world-baked, so convert through the parent inverse)
    Minv = ob.matrix_world.inverted()
    ob["fst_head"] = list(Minv @ Vector(at))
    ob["fst_dir"] = list((Minv.to_3x3() @ w).normalized())
    ob["fst_len"], ob["fst_d"], ob["fst_head_d"] = float(length), float(d), float(hd)
    ob["fst_kind"] = "screw"
    PARTS[name].update(head=list(at), into=list(w), length=length, spec=spec)
    return ob


def nut(name, at, into, joint=None, af=None, h=None, step=None):
    """M3 hex nut whose bearing face is at `at`, body extending along `into` (same frame as features.nut_trap).
    Tagged fst_kind="nut", so cadcheck pairs it with the bolt on its axis and fails a bolt that stops short of it
    (attempt 2: the M3 x 16 pinch bolts ended 0.36 mm before their nuts, FINDINGS A2-F3)."""
    af = af or features.RULES["m3_nut_af"]
    h = h or features.RULES["m3_nut_h"]
    w = Vector(into).normalized()
    r = af / 2 / math.cos(math.pi / 6)
    ob = geom.cyl(name, (0, 0), r, 0, h, 'Z', n=6)
    geom.xform(ob, features._frame(at, w))
    ob = part(ob, name, 'FST', "screw", joint, part="M3 hex nut", step=step or "")
    ob["fst_kind"] = "nut"
    PARTS[name].update(face=list(at), into=list(w), nut_h=h)
    return ob


def cable(name, pts, r, color="cable_blk", joint=None, lead_len=None, step=None):
    """Tube along a polyline. Stores path_len (and lead_len if given) so cadcheck can compare them
    (attempt 1: the bullet joints of 80 mm leads landed at a moving bend, A1-F12)."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0], p[1], p[2], 1)
    cu.bevel_depth = r
    cu.bevel_resolution = 3
    cu.use_fill_caps = True
    tmp = bpy.data.objects.new(name, cu)
    geom.scratch().objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    ob = bpy.data.objects.new(name, me)
    geom.scratch().objects.link(ob)
    L = sum((Vector(pts[i + 1]) - Vector(pts[i])).length for i in range(len(pts) - 1))
    ob = part(ob, name, 'CAB', color, joint, part="cable route", step=step or "")
    ob["path_len"] = float(L)
    # both ends at home, world mm: cadcheck finds cables that meet with no connector there (V2A3-F3)
    ob["cab_ends"] = [float(c) for c in list(pts[0]) + list(pts[-1])]
    if lead_len:
        ob["lead_len"] = float(lead_len)
    PARTS[name].update(path=[list(map(float, p)) for p in pts], path_len=L, lead_len=lead_len,
                       path_ends=[list(map(float, pts[0])), list(map(float, pts[-1]))])
    return ob


# ------------------------------------------------------------------ manifest

def manifest():
    set_pose()
    js = {}
    for n, e in _all_joints().items():
        js[n] = {k.replace("joint_", ""): (e[k] if not hasattr(e[k], "to_list") else e[k].to_list()) for k in e.keys()}
        js[n]["origin"] = [round(c, 3) for c in e.matrix_world.translation]
        js[n]["parent"] = e.parent.name if e.parent else None
    parts = {}
    for name, info in PARTS.items():
        ob = bpy.data.objects.get(name)
        if ob is None:
            continue
        bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        lo = [round(min(v[i] for v in bb), 2) for i in range(3)]
        hi = [round(max(v[i] for v in bb), 2) for i in range(3)]
        parts[name] = {**{k: v for k, v in info.items() if k not in ("path",)}, "bbox_world_home": [lo, hi]}
    return {"units": "mm", "params": PARAMS, "joints": js, "parts": parts, "features": features.LOG}


def write_manifest(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(manifest(), f, indent=1, default=str)
    return path


def cleanup():
    """Remove the scratch collection before saving."""
    c = bpy.data.collections.get("TMP")
    if c:
        for o in list(c.objects):
            geom.kill(o)
        bpy.data.collections.remove(c)
