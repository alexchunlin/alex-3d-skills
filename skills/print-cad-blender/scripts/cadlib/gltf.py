"""glTF: the one Blender glTF exporter call (cad view's page and model.glb share it) and write_glb, model.glb for any
glTF viewer: a node per part under a root that turns Z-up mm into Y-up m, a clip per joint and one for the assembly
order (issue #31). The clips are appended to the exported GLB here (float accessors in its one buffer), keyed with
cadlib.joints' maths, so the scene's actions are never touched.
"""
import bpy, contextlib, ctypes, fnmatch, json, math, os, struct, sys, time
from mathutils import Vector, Matrix
from . import joints as JT, render

# ------------------------------------------------------------------ glTF (cad view's page and write_glb's model.glb)

# Blender's bundled glTF exporter, as cad view has called it since PR #48: Z-up node transforms (write_glb's root node
# turns them Y-up), no normals or UVs (a viewer computes flat normals), Draco at 14-bit positions (about 0.03 mm on
# the 433 mm v2 launcher): for looking, never for measuring.
GLTF_OPTS = dict(export_format='GLB', use_selection=True, export_yup=False, export_apply=False, export_normals=False,
                 export_texcoords=False, export_extras=False, export_cameras=False, export_lights=False,
                 export_animations=False)
DRACO_OPTS = dict(export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=10,
                  export_draco_position_quantization=14)
ROLES = ("PRT_", "BUY_", "FST_", "CAB_")
FLOAT = 5126   # glTF accessor componentType: 32-bit float


@contextlib.contextmanager
def quiet(path):
    """stdout and stderr (the file descriptors, so C++ output too) into `path` for the block."""
    sys.stdout.flush(); sys.stderr.flush()
    saved = [os.dup(1), os.dup(2)]
    with open(path, "w") as f:
        os.dup2(f.fileno(), 1); os.dup2(f.fileno(), 2)
        try:
            yield
        finally:
            sys.stdout.flush(); sys.stderr.flush()
            try:
                ctypes.CDLL(None).fflush(None)   # Draco prints through C stdio, which would flush after the restore
            except (OSError, AttributeError):
                pass
            os.dup2(saved[0], 1); os.dup2(saved[1], 2)
            for d in saved:
                os.close(d)


def export(path, names, draco=True, materials=False):
    """Export the objects in `names`, with their ancestors so the hierarchy holds, as one GLB at `path`. The exporter
    and Draco print a line per object: that goes to path + ".log", removed on success."""
    O = bpy.data.objects
    sel = set(names)
    for n in list(sel):
        p = O[n].parent
        while p is not None:
            sel.add(p.name)
            p = p.parent
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name in sel)
    log = path + ".log"
    if os.path.exists(path):
        os.remove(path)
    with quiet(log):
        bpy.ops.export_scene.gltf(filepath=path, export_materials='EXPORT' if materials else 'NONE', **GLTF_OPTS,
                                  **(DRACO_OPTS if draco else {"export_draco_mesh_compression_enable": False}))
    if not os.path.isfile(path):
        raise RuntimeError("the glTF export wrote nothing; its log:\n" + open(log).read()[-3000:])
    os.remove(log)
    return path


def read_glb(path):
    """(JSON dict, BIN bytes) of a GLB."""
    with open(path, "rb") as f:
        b = f.read()
    if b[:4] != b"glTF":
        raise ValueError("%s is not a GLB" % path)
    off, js, bin_ = 12, None, b""
    while off + 8 <= len(b):
        ln, kind = struct.unpack_from("<I4s", b, off)
        if kind == b"JSON":
            js = json.loads(b[off + 8:off + 8 + ln])
        elif kind == b"BIN\0":
            bin_ = b[off + 8:off + 8 + ln]
        off += 8 + ln
    return js, bin_


def save_glb(path, js, bin_):
    j = json.dumps(js, separators=(",", ":")).encode()
    j += b" " * (-len(j) % 4)
    bin_ = bin_ + b"\0" * (-len(bin_) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(j) + (8 + len(bin_) if bin_ else 0)))
        f.write(struct.pack("<I4s", len(j), b"JSON") + j)
        if bin_:
            f.write(struct.pack("<I4s", len(bin_), b"BIN\0") + bin_)


class _Anim:
    """glTF animations appended to a GLB's one buffer: float accessors for keyframe times and TRS values."""

    def __init__(self, js, bin_):
        self.js, self.bin = js, bytearray(bin_)
        if not js.get("buffers"):
            js["buffers"] = [{"byteLength": 0}]

    def acc(self, vals, typ):
        n = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[typ]
        flat = [float(x) for v in vals for x in ((v,) if n == 1 else v)]
        self.bin += b"\0" * (-len(self.bin) % 4)
        self.js.setdefault("bufferViews", []).append({"buffer": 0, "byteOffset": len(self.bin), "byteLength": 4 * len(flat)})
        self.bin += struct.pack("<%df" % len(flat), *flat)
        a = {"bufferView": len(self.js["bufferViews"]) - 1, "componentType": FLOAT, "count": len(vals), "type": typ}
        if n == 1:   # an animation input needs its min and max
            a.update(min=[min(flat)], max=[max(flat)])
        self.js.setdefault("accessors", []).append(a)
        return len(self.js["accessors"]) - 1

    def clip(self, name, times, tracks, extras):
        """tracks: [(node index, "translation" | "rotation" | "scale", values, interpolation)], all keyed on `times`."""
        t = self.acc(times, "SCALAR")
        smp, ch = [], []
        for node, path, vals, interp in tracks:
            smp.append({"input": t, "output": self.acc(vals, "VEC4" if path == "rotation" else "VEC3"), "interpolation": interp})
            ch.append({"sampler": len(smp) - 1, "target": {"node": node, "path": path}})
        self.js.setdefault("animations", []).append({"name": name, "samplers": smp, "channels": ch, "extras": extras})

    def done(self):
        self.bin += b"\0" * (-len(self.bin) % 4)
        self.js["buffers"][0]["byteLength"] = len(self.bin)
        return self.js, bytes(self.bin)


def _trs(M):
    loc, q, sc = M.decompose()
    return tuple(loc), (q.x, q.y, q.z, q.w), tuple(sc)


def sweep_keys(J, CP, d, max_step=10.0):
    """(driver values lo -> hi -> lo, the joints that move): a continuous joint turns home -> home + 360 -> home. No
    moving joint (couplings included) turns more than max_step deg (or slides max_step mm) between keys, so a viewer's
    slerp between keys stays on the joint's own path."""
    s = J[d]
    if s.get("continuous"):
        lo = float(s.get("home") or 0.0)
        hi = lo + 360.0
    else:
        lo, hi = float(s["lo"]), float(s["hi"])
    v0, v1 = JT.values(J, CP, {d: lo}), JT.values(J, CP, {d: hi})
    moved = [n for n in J if J[n]["axis"] and abs(v1[n] - v0[n]) > 1e-9]
    n = max(2, int(math.ceil(max([abs(v1[m] - v0[m]) for m in moved] or [0.0]) / max_step)))
    up = [lo + (hi - lo) * i / n for i in range(n + 1)]
    return up + up[-2::-1], moved


def _load(x):
    if x is None or isinstance(x, dict):
        return x or {}
    if not os.path.exists(x):
        return {}
    with open(x) as f:
        return json.load(f)


def _dir(row):
    """An insertion row's way out as a unit vector: cadcheck's free_dir_vec, else (an older report) its free_dir label
    when it is "+Z" or "dir [x, y, z]"; None otherwise ("along FST_x" or "snap y" carry no vector in an old report)."""
    v = row.get("free_dir_vec")
    if isinstance(v, list) and len(v) == 3:
        v = Vector(v)
        return v.normalized() if v.length > 0 else None
    label = row.get("free_dir")
    if not isinstance(label, str):
        return None
    if len(label) == 2 and label[0] in "+-" and label[1] in "XYZ":
        v = Vector((0, 0, 0))
        v["XYZ".index(label[1])] = 1.0 if label[0] == "+" else -1.0
        return v
    if label.startswith("dir ["):
        try:
            v = Vector(json.loads(label[4:]))
            return v.normalized() if v.length > 0 else None
        except (ValueError, TypeError):
            return None
    return None


def write_glb(path, checks=None, report=None, draco=True, clip_s=4.0, step_s=1.0):
    """model.glb for any glTF viewer: every PRT_/BUY_/FST_/CAB_ mesh and PIV_ empty as a node with its name, in the
    blend's hierarchy, under one root node that turns Blender's Z-up mm into glTF's Y-up metres (rotation -90 deg about
    X, scale 0.001: with no root scale a viewer read the v2 launcher as 433 m, issue #31). Animations:
      - one clip per driven joint, named after it: lo -> hi -> lo over clip_s seconds (a continuous joint turns 360
        and back), coupled joints following. Keyframes are cadlib.joints values / world_at, the maths cadcheck poses
        with; the clip's extras hold the driver value at each key ({"joint", "values", "moves"}).
      - one "assembly" clip from checks.json assembly_order, a step per step_s seconds: a step's objects appear (scale
        0 before) and fly home along the way they come out, which is the insertion check's free direction from a
        cadcheck `report` row for the object, else render.explode_offsets' radial direction (fasteners, cables, merged
        groups). Bench sub-assemblies are shown built in place, in listed order; objects in no step are there throughout.
    checks: checks.json path or dict (its "joints" / "couplings" overrides and "assembly_order"); report: a cadcheck.json
    path or dict, read only when given (build scripts pass --glb-report PATH), so a stale report in the out dir is never
    picked up on its own. draco=False writes raw meshes (v2a7: about 9x the size). Returns a summary dict."""
    cfg, rep = _load(checks), _load(report)
    O = bpy.data.objects
    J, CP = JT.read(O, cfg)
    JT.apply(J, CP, {})
    vl = bpy.context.view_layer
    parts = sorted(o.name for o in O if o.type == 'MESH' and o.name.startswith(ROLES) and o.name in vl.objects)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    export(path, parts + list(J), draco=draco, materials=True)
    js, bin_ = read_glb(path)
    idx = {nd.get("name"): i for i, nd in enumerate(js["nodes"])}
    scene = js["scenes"][js.get("scene", 0)]
    js["nodes"].append({"name": "ROOT_zup_mm", "rotation": [-math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5)],
                        "scale": [0.001, 0.001, 0.001], "children": scene["nodes"]})
    scene["nodes"] = [len(js["nodes"]) - 1]
    an = _Anim(js, bin_)

    def local(n, vals):
        cache = {}
        M = JT.world_at(n, J, vals, cache)
        p = O[n].parent
        return (JT.world_at(p.name, J, vals, cache).inverted() @ M) if p is not None else M

    clips = []
    for d, s in J.items():
        if not s["axis"] or d in CP or (s.get("lo") is None and not s.get("continuous")):
            continue
        keys, moved = sweep_keys(J, CP, d)
        moved = [n for n in moved if n in idx]
        tr = {n: [] for n in moved}
        for v in keys:
            vals = JT.values(J, CP, {d: v})
            for n in moved:
                tr[n].append(_trs(local(n, vals)))
        tracks = []
        for n in moved:
            if J[n].get("kind") == "prismatic":
                tracks.append((idx[n], "translation", [k[0] for k in tr[n]], "LINEAR"))
                continue
            q = [k[1] for k in tr[n]]
            for i in range(1, len(q)):   # keep each quaternion on the previous one's side, so slerp goes the short way
                if sum(a * b for a, b in zip(q[i], q[i - 1])) < 0:
                    q[i] = tuple(-c for c in q[i])
            tracks.append((idx[n], "rotation", q, "LINEAR"))
        an.clip(d, [clip_s * i / (len(keys) - 1) for i in range(len(keys))], tracks, {"joint": d, "values": keys, "moves": moved})
        clips.append(d)

    steps = cfg.get("assembly_order") or []
    step_of = {}
    for i, st in enumerate(steps):   # first step whose glob matches, as cadcheck's assembly_present
        for n in parts:
            if n not in step_of and any(fnmatch.fnmatch(n, g) for g in st.get("objects", [])):
                step_of[n] = i
    if report and not isinstance(report, dict):
        print("glb: insertion directions from %s (%s)" % (report, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(report))))
              if os.path.exists(report) else "glb: no report at %s: assembly flights are radial" % report)
    ways = {r["object"]: _dir(r) for r in ((rep.get("checks") or {}).get("insertion") or {}).get("rows") or []
            if isinstance(r, dict) and r.get("object") in step_of}
    by = {"insertion": 0, "radial": 0}
    if step_of:
        radial = render.explode_offsets([O[n] for n in step_of])
        fly = 0.75 * step_s
        times = sorted({0.0, len(steps) * step_s} | {t for i in range(len(steps)) for t in (i * step_s, i * step_s + fly)})
        tracks = []
        for n, i in sorted(step_of.items()):
            o = O[n]
            box = [o.matrix_world @ Vector(c) for c in o.bound_box]
            size = max(20.0, (Vector(map(max, *box)) - Vector(map(min, *box))).length)
            if ways.get(n) is not None:
                off = ways[n] * size
                by["insertion"] += 1
            else:
                r = Vector(radial[n])
                off = (r.normalized() if r.length > 1.0 else Vector((0, 0, 1))) * max(size, r.length)
                by["radial"] += 1
            Pw = o.parent.matrix_world if o.parent is not None else Matrix.Identity(4)
            loc, _q, sc = (Pw.inverted() @ o.matrix_world).decompose()
            off_l = Pw.inverted().to_3x3() @ off
            t0 = i * step_s
            tracks.append((idx[n], "translation", [tuple(loc + off_l * min(1.0, max(0.0, (t0 + fly - t) / fly))) for t in times], "LINEAR"))
            tracks.append((idx[n], "scale", [tuple(sc) if t >= t0 else (0.0, 0.0, 0.0) for t in times], "STEP"))
        an.clip("assembly", times, tracks, {"steps": [st.get("step", "") for st in steps], "step_s": step_s, "from": by})
    js, bin_ = an.done()
    js.setdefault("asset", {})["extras"] = {"generator": "alex-3d-skills cadlib.gltf.write_glb",
                                            "units": "mm under ROOT_zup_mm (scale 0.001: metres)"}
    save_glb(path, js, bin_)
    out = {"path": path, "bytes": os.path.getsize(path), "draco": draco, "nodes": len(idx), "parts": len(parts),
           "joints": len(J), "clips": clips + (["assembly"] if step_of else []), "assembly_from": by}
    print("GLB %s %.2f MB %s: %d nodes (%d parts, %d joints) under a 0.001 root; clips %s; assembly flights %s" % (
        path, out["bytes"] / 1e6, "Draco" if draco else "raw", out["nodes"], len(parts), len(J),
        ", ".join(out["clips"]) or "none", by))
    return out
