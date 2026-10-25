"""Blended connector: Blender's own volume, remesh, metaball and hull routes against cadlib.blend, on the 6-way node.

    nice -n 10 Blender -b --factory-startup --python tools/prior_art/blend_compare.py -- --out /tmp/alex3d-bb-cmp [--render]

The node: 3 tubes of 20 mm on X, Y and Z, wall 4, clearance 0.2, arms 40 mm from the centre, blind sockets that stop
14.2 mm from the centre, fillet 6. Every approach makes the outer skin; then the same exact Manifold socket cutters
are subtracted, so the fit and wall numbers compare the skins alone. Columns:
  t_s           time to make the skin (s)
  tris          triangles after the sockets are cut
  closed        non-manifold edges after the cut (0 = a printable closed solid)
  clr_min/max   fit clearance by radial rays from each tube axis (spec 0.2)
  wall_min      radial wall from socket to outer skin (spec 4.0)
  arm_dev       max |outer radius - 14.2| on the plain arms, 22-34 mm from the centre (the offset surface)
  blend_dev     max |round-union field| over skin vertices: distance from the intended filleted surface
  fill_edge     how far the surface stands out of the sharp crease between two arms, along (1,1,0) (intended 2.49)
  fill_corner   the same at the 3-arm corner along (1,1,1) (intended 3.11)
Writes blend_compare.json, plus cmp_<name>.png with --render. Results: docs/features/blend-bracket.md.
"""
import bpy, json, math, os, sys, time
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, asm as A, blend as B, render as R  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-bb-cmp"
RENDER = "--render" in argv
os.makedirs(OUT, exist_ok=True)

D, WALL, CLR, L, FIL, VOX = 20.0, 4.0, 0.2, 40.0, 6.0, 0.5
RO = D / 2 + CLR + WALL                 # 14.2 outer arm radius
A.new_scene()


def node_holds():
    hs = []
    for i, ax in enumerate("XYZ"):
        for sg in (1, -1):
            b = [0.0, 0.0, 0.0]
            b[i] = sg * L
            hs.append(B.Tube((0, 0, 0), b, D, WALL, CLR, stop=RO, edge=1.0, lead_in=0.5, name="%s%s" % ("+" if sg > 0 else "-", ax)))
    return hs


HOLDS = node_holds()
FIELDS = [h.field() for h in HOLDS]
f_int = lambda pts: B.field_at(FIELDS, pts, FIL)


def ray_root(dirv, r0=5.0, r1=40.0):
    """Distance along dirv from the origin where the intended field crosses zero (bisection)."""
    d = np.array(dirv) / np.linalg.norm(dirv)
    a, b = r0, r1
    for _ in range(50):
        m = (a + b) / 2
        if f_int([d * m])[0] < 0:
            a = m
        else:
            b = m
    return (a + b) / 2


SHARP_EDGE, SHARP_CORNER = RO * math.sqrt(2), RO * math.sqrt(1.5)
INT_EDGE, INT_CORNER = ray_root((1, 1, 0)) - SHARP_EDGE, ray_root((1, 1, 1)) - SHARP_CORNER
DIAG_E = [Vector(v).normalized() for v in ((1, 1, 0), (1, -1, 0), (-1, 1, 0), (-1, -1, 0), (1, 0, 1), (1, 0, -1), (-1, 0, 1), (-1, 0, -1),
                                          (0, 1, 1), (0, 1, -1), (0, -1, 1), (0, -1, -1))]
DIAG_C = [Vector((sx, sy, sz)).normalized() for sx in (1, -1) for sy in (1, -1) for sz in (1, -1)]


def tree_of(ob):
    me = ob.data
    return BVHTree.FromPolygons([ob.matrix_world @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])


def sharp_union(n=96):
    cs = [G.cyl("arm" + a, (0, 0), RO, -L, L, a, n=n) for a in "XYZ"]
    return G.csg(cs[0], add=cs[1:])


def metrics(name, skin, t_s, settings=""):
    tr = tree_of(skin)
    # offset surface on the plain arms
    arm = []
    for h in HOLDS:
        u, v, w = (Vector(h.M.col[i][:3]) for i in range(3))
        for z in (22.0, 26.0, 30.0, 34.0):
            for k in range(24):
                t = 2 * math.pi * (k + 0.5) / 24
                hit = tr.ray_cast(h.a + w * z, u * math.cos(t) + v * math.sin(t), 100.0)
                arm.append(abs(hit[3] - RO) if hit[0] else 99.0)
    fe = [(tr.ray_cast(Vector((0, 0, 0)), d, 100.0)[3] or 0) - SHARP_EDGE for d in DIAG_E]
    fc = [(tr.ray_cast(Vector((0, 0, 0)), d, 100.0)[3] or 0) - SHARP_CORNER for d in DIAG_C]
    vs = np.array([tuple(skin.matrix_world @ v.co) for v in skin.data.vertices])
    if len(vs) > 60000:
        vs = vs[np.random.default_rng(1).choice(len(vs), 60000, replace=False)]
    bdev = float(np.max(np.abs(f_int(vs))))
    fin = skin.copy()
    fin.data = skin.data.copy()
    G.scratch().objects.link(fin)
    cut = []
    for h in HOLDS:
        cut += h.cutters()
    t1 = time.time()
    try:
        G.csg(fin, sub=cut, check=False)
        err = ""
    except Exception as e:  # noqa: BLE001
        err = str(e)[:120]
    t_cut = time.time() - t1
    nm, vol = G.solid_stats(fin)
    m = B.measure(fin, HOLDS)
    cl = [x for r in m.values() for x in (r["clearance_min"], r["clearance_max"]) if x is not None]
    wl = [r["wall_min"] for r in m.values() if r["wall_min"] is not None]
    row = {"name": name, "settings": settings, "t_s": round(t_s, 2), "t_cut_s": round(t_cut, 2), "tris": B.tri_count(fin),
           "non_manifold_edges": nm, "volume_mm3": round(vol, 1), "clr_min": min(cl) if cl else None, "clr_max": max(cl) if cl else None,
           "wall_min": min(wl) if wl else None, "arm_dev": round(max(arm), 3), "blend_dev": round(bdev, 3),
           "fill_edge": round(sum(fe) / len(fe), 2), "fill_corner": round(sum(fc) / len(fc), 2), "error": err}
    print("CMP", json.dumps(row), flush=True)
    if RENDER:
        render(fin, name, ["%.1f s  wall %.2f" % (t_s, row["wall_min"] or 0), "arm %.2f  fill %.1f/%.1f" % (row["arm_dev"], row["fill_edge"], row["fill_corner"])])
    G.kill(skin)
    G.kill(fin)
    return row


FONTS = os.path.expanduser("~/code-stuff/alex-style-guide/fonts")
INK = (0.043, 0.043, 0.043, 1.0)        # alex-style light ink #0b0b0b
MUTED = (0.11, 0.11, 0.10, 1.0)         # #5f5f5a in linear


def label(cam, text, y, size, font, color):
    cu = bpy.data.curves.new("lbl", 'FONT')
    cu.body, cu.size = text, size
    fp = os.path.join(FONTS, font)
    if os.path.exists(fp):
        cu.font = bpy.data.fonts.load(fp, check_existing=True)
    o = bpy.data.objects.new("lbl", cu)
    G.scratch().objects.link(o)
    o.parent = cam
    o.location = (-2.85, y, -10)
    cu.materials.append(A.mat(color))
    return o


def render(ob, name, caption):
    """480 x 360 view of one result, titled in the alex-style light mode (Roboto Condensed title, Roboto Mono numbers)."""
    for o in list(bpy.data.objects):
        if o.type == 'MESH' and o is not ob:
            o.hide_render = True
    ob.hide_render = False
    ob.data.materials.clear()
    ob.data.materials.append(A.mat((0.89, 0.14, 0.11, 1.0)))
    R.setup(res=(480, 360))
    cam = R.camera((125, -158, 112), (0, 0, -5), lens=60)
    bpy.context.view_layer.update()
    lbls = [label(cam, TITLES.get(name, name).upper(), 1.88, 0.21, "RobotoCondensed-700.ttf", INK),
            label(cam, caption[0], 1.62, 0.15, "RobotoMono-400.ttf", MUTED), label(cam, caption[1], 1.42, 0.15, "RobotoMono-400.ttf", MUTED)]
    R.shot(os.path.join(OUT, "cmp_%s.png" % name))
    for o in lbls:
        bpy.data.objects.remove(o)


TITLES = {"sharp_union": "Sharp union (no blend)", "a1_volume_t0.1_smooth20": "(a) Mesh to Volume + smooth",
          "a2_sdf_fillet70_v0.5": "(a) SDF Grid Fillet x70", "b_remesh_smooth40": "(b) Remesh + smooth x40",
          "c_metaball": "(c) Metaballs", "d_hull_bevel": "(d) Convex hull + bevel", "e_blend_ad0_30000_b0.02": "(e) cadlib.blend (this)"}
SHEET = ["sharp_union", "e_blend_ad0_30000_b0.02", "a2_sdf_fillet70_v0.5", "a1_volume_t0.1_smooth20", "b_remesh_smooth40",
         "c_metaball", "d_hull_bevel"]


def sheet(names, path, cols=2):
    """Tile the 480 x 360 renders into one 960 px wide image (white fill for an empty cell)."""
    ims = [bpy.data.images.load(os.path.join(OUT, "cmp_%s.png" % n)) for n in names]
    w, h = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    out = np.ones((rows * h, cols * w, 4), np.float32)
    for i, im in enumerate(ims):
        px = np.array(im.pixels[:], np.float32).reshape(h, w, 4)
        r, c = rows - 1 - i // cols, i % cols          # Blender pixels run bottom-up
        out[r * h:(r + 1) * h, c * w:(c + 1) * w] = px
    img = bpy.data.images.new("sheet", cols * w, rows * h)
    img.pixels = out.ravel()
    img.filepath_raw, img.file_format = path, 'PNG'
    img.save()
    print("RENDER", path)


def gn_modifier(ob, build):
    ng = bpy.data.node_groups.new("gn", 'GeometryNodeTree')
    ng.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    gi, go = ng.nodes.new('NodeGroupInput'), ng.nodes.new('NodeGroupOutput')
    out = build(ng, gi.outputs[0])
    ng.links.new(out, go.inputs[0])
    m = ob.modifiers.new("gn", 'NODES')
    m.node_group = ng
    return ob


def node(ng, kind, inp=None, **vals):
    n = ng.nodes.new(kind)
    if inp is not None:
        ng.links.new(inp, n.inputs[0])
    for k, v in vals.items():
        n.inputs[k.replace("_", " ").title() if k not in ("Band_Width",) else "Band Width"].default_value = v
    return n


def smooth(ob, iters, lam=1.0):
    m = ob.modifiers.new("ls", 'LAPLACIANSMOOTH')
    m.iterations, m.lambda_factor, m.use_volume_preserve = iters, lam, True
    return ob


rows = []
# 0: the sharp union, no blend (the "kit of boxes" baseline every v1 attempt used)
t0 = time.time()
s = sharp_union()
rows.append(metrics("sharp_union", s, time.time() - t0, "Manifold union of 3 cylinders, n=96"))

# (a1) Mesh to Volume -> Volume to Mesh, then Laplacian smoothing (volume preserving)
for it, thr in ((0, 0.5), (0, 0.1), (20, 0.1)):
    t0 = time.time()
    s = sharp_union()
    gn_modifier(s, lambda ng, g, thr=thr: node(ng, 'GeometryNodeVolumeToMesh', node(ng, 'GeometryNodeMeshToVolume', g, Voxel_Size=VOX, Interior_Band_Width=2.0).outputs[0],
                                               Threshold=thr, Adaptivity=0.0).outputs[0])
    for nd in s.modifiers[0].node_group.nodes:
        if nd.bl_idname in ('GeometryNodeMeshToVolume', 'GeometryNodeVolumeToMesh'):
            nd.inputs["Resolution Mode"].default_value = "Size"
    G.apply_mods(s)
    if it:
        smooth(s, it)
        G.apply_mods(s)
    rows.append(metrics("a1_volume_t%g_smooth%d" % (thr, it), s, time.time() - t0, "Mesh to Volume %.1f, Volume to Mesh threshold %g, Laplacian x%d" % (VOX, thr, it)))

# (a2) Mesh to SDF Grid -> SDF Grid Fillet -> Grid to Mesh
# the fill depends on the voxel as well as the iterations (a curvature flow): the last row halves the voxel
for it, bw, vx in ((10, 16, VOX), (40, 16, VOX), (70, 16, VOX), (100, 16, VOX), (120, 16, VOX), (70, 32, VOX / 2)):
    t0 = time.time()
    s = sharp_union()

    def build(ng, g, it=it, bw=bw, vx=vx):
        sdf = node(ng, 'GeometryNodeMeshToSDFGrid', g, Voxel_Size=vx)
        sdf.inputs["Band Width"].default_value = bw
        fil = ng.nodes.new('GeometryNodeSDFGridFillet')
        ng.links.new(sdf.outputs[0], fil.inputs[0])
        fil.inputs["Iterations"].default_value = it
        gm = ng.nodes.new('GeometryNodeGridToMesh')
        ng.links.new(fil.outputs[0], gm.inputs[0])
        gm.inputs["Threshold"].default_value = 0.0
        return gm.outputs[0]
    gn_modifier(s, build)
    G.apply_mods(s)
    rows.append(metrics("a2_sdf_fillet%d_v%g" % (it, vx), s, time.time() - t0, "Mesh to SDF Grid %.2f band %d, SDF Grid Fillet x%d, Grid to Mesh" % (vx, bw, it)))

# (b) Remesh modifier (voxel) + Laplacian smoothing
for it in (10, 40):
    t0 = time.time()
    s = sharp_union()
    m = s.modifiers.new("rm", 'REMESH')
    m.mode, m.voxel_size, m.adaptivity = 'VOXEL', VOX, 0.0
    G.apply_mods(s)
    smooth(s, it)
    G.apply_mods(s)
    rows.append(metrics("b_remesh_smooth%d" % it, s, time.time() - t0, "Remesh voxel %.1f, Laplacian x%d" % (VOX, it)))


# (c) metaballs: 3 capsules, radius calibrated so the plain arm comes out at 14.2
def metaball(r, res=VOX):
    mb = bpy.data.metaballs.new("mb")
    mb.resolution = mb.render_resolution = res
    for rot in (Matrix.Identity(3), Matrix.Rotation(math.pi / 2, 3, 'Z'), Matrix.Rotation(-math.pi / 2, 3, 'Y')):
        e = mb.elements.new(type='CAPSULE')
        e.co, e.radius, e.size_x = (0, 0, 0), r, L - RO
        e.rotation = rot.to_quaternion()
    o = bpy.data.objects.new("mbo", mb)
    G.scratch().objects.link(o)
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(o)
    ob = bpy.data.objects.new("mbm", me)
    G.scratch().objects.link(ob)
    return ob


t0 = time.time()
lo_r, hi_r = 10.0, 30.0
for _ in range(12):
    r = (lo_r + hi_r) / 2
    ob = metaball(r, 1.0)
    hit = tree_of(ob).ray_cast(Vector((25, 0, 0)), Vector((0, 0.6, 0.8)), 100.0)
    G.kill(ob)
    if hit[0] is not None and hit[3] > RO:
        hi_r = r
    else:
        lo_r = r
t_cal = time.time() - t0
t0 = time.time()
s = metaball((lo_r + hi_r) / 2)
rows.append(metrics("c_metaball", s, time.time() - t0 + t_cal, "3 capsules r=%.2f (calibrated in %.1f s), threshold 0.6, res %.1f" % ((lo_r + hi_r) / 2, t_cal, VOX)))

# (d) convex hull + bevel
t0 = time.time()
s = sharp_union()
bm = __import__("bmesh").new()
bm.from_mesh(s.data)
__import__("bmesh").ops.convex_hull(bm, input=bm.verts)
bm.to_mesh(s.data)
bm.free()
m = s.modifiers.new("bv", 'BEVEL')
m.width, m.segments, m.limit_method, m.angle_limit, m.use_clamp_overlap = FIL, 6, 'ANGLE', math.radians(30), True
G.apply_mods(s)
rows.append(metrics("d_hull_bevel", s, time.time() - t0, "convex hull of the sharp union, bevel 6 mm x6 over 30 deg"))

# (e) numpy SDF + round union + OpenVDB mesher (cadlib.blend)
for ad, mt, bias in ((0.0, None, 0.0), (0.05, None, 0.0), (0.05, None, 0.2), (0.0, 60000, 0.0), (0.0, 60000, 0.02), (0.0, 30000, 0.02)):
    t0 = time.time()
    s, rep = B.skin("e", FIELDS, FIL, voxel=VOX, adaptivity=ad, bias=bias, max_tris=mt)
    rows.append(metrics("e_blend_ad%g_%s_b%g" % (ad, mt or "full", bias), s, time.time() - t0,
                        "round union r=6, voxel %.1f, adaptivity %g, max_tris %s, bias %g" % (VOX, ad, mt, bias)))

res = {"spec": {"d": D, "wall": WALL, "clearance": CLR, "arm": L, "fillet": FIL, "voxel": VOX, "r_out": RO,
                "intended_fill_edge": round(INT_EDGE, 2), "intended_fill_corner": round(INT_CORNER, 2)}, "rows": rows}
with open(os.path.join(OUT, "blend_compare.json"), "w") as f:
    json.dump(res, f, indent=1)
if RENDER:
    sheet(SHEET, os.path.join(OUT, "compare.png"))
print("INTENDED", round(INT_EDGE, 2), round(INT_CORNER, 2))
print("WROTE", os.path.join(OUT, "blend_compare.json"))
