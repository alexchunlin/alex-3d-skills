"""Workbench renders: standard view set, sections, exploded view, STL contact sheet, review markers.

Defaults are cheap previews (960 x 720, about 0.3-0.6 s each). Pass final=True (or set
CAD_RENDER_FINAL=1) for the 1600 px+ deliverable set. A render budget (CAD_RENDER_BUDGET, default 40
per process) stops runaway re-render loops. The model sees a 2 MB render as ~100-170 KB anyway
(FINDINGS A1-T6), so higher resolution buys nothing for agent review.

Look: white background, thin ink outlines, cavity shading, flat materials (alex-style light mode:
bg #ffffff, ink #0b0b0b). Section faces take a saturated yellow so they read against both PLA colours
(the attempt-1 reviewer read these sections without trouble).
"""
import bpy, math, os
from mathutils import Vector, Matrix
from . import asm, geom

BUDGET = int(os.environ.get("CAD_RENDER_BUDGET", "40"))
COUNT = [0]
INK = (0.043, 0.043, 0.043)
CUT = (0.98, 0.83, 0.25, 1.0)


def setup(final=None, res=None):
    final = final if final is not None else os.environ.get("CAD_RENDER_FINAL") == "1"
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sh = sc.display.shading
    sh.light = 'STUDIO'
    sh.color_type = 'MATERIAL'
    sh.show_shadows = True
    sh.shadow_intensity = 0.3
    sh.show_cavity = True
    sh.cavity_type = 'BOTH'
    sh.show_object_outline = True
    sh.object_outline_color = INK
    sh.show_specular_highlight = False
    sc.display.light_direction = (0.45, -0.45, 0.75)
    sc.render.resolution_x, sc.render.resolution_y = res or ((1800, 1350) if final else (960, 720))
    sc.render.resolution_percentage = 100
    if sc.world is None:
        sc.world = bpy.data.worlds.new("W")
    sc.world.color = (1.0, 1.0, 1.0)
    sc.view_settings.view_transform = 'Standard'
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGB'
    sc.render.image_settings.compression = 90
    for o in bpy.data.objects:
        if o.type == 'EMPTY':
            o.hide_render = True


def camera(loc, target, ortho=None, lens=50, name="CAM"):
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        bpy.context.scene.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    cam.data.clip_start, cam.data.clip_end = 1, 10000
    if ortho:
        cam.data.type, cam.data.ortho_scale = 'ORTHO', ortho
    else:
        cam.data.type, cam.data.lens = 'PERSP', lens
    bpy.context.scene.camera = cam
    return cam


def shot(path):
    if COUNT[0] >= BUDGET:
        print("RENDER_BUDGET exhausted (%d); skipped %s" % (BUDGET, path))
        return None
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    COUNT[0] += 1
    print("RENDER", path)
    return path


def scene_bounds(kinds=("Printed", "Purchased")):
    pts = []
    for cn in kinds:
        c = bpy.data.collections.get(cn)
        if c:
            for o in c.all_objects:
                if o.type == 'MESH' and not o.hide_render:
                    pts += [o.matrix_world @ Vector(b) for b in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def view_set(outdir, poses=None, final=None, prefix=""):
    """iso, iso_front_left, front, side, top, rear, plus one iso per named pose
    (poses = {"pan+90_tilt45": {"PIV_pan": 90, "PIV_tilt": 45}, ...}).
    World frame: X right, Y forward (front/muzzle), Z up, so the front camera sits on +Y."""
    setup(final)
    asm.set_pose()
    lo, hi = scene_bounds()
    c = (lo + hi) / 2
    size = max(hi - lo)
    d = size * 2.2
    out = []
    iso = c + Vector((0.85, -1.0, 0.75)) * d
    views = {
        "iso": (iso, None), "iso_front_left": (c + Vector((-0.8, 0.95, 0.7)) * d, None),
        "front": (c + Vector((0, d * 2, 0)), size * 1.25), "side": (c + Vector((d * 2, 0, 0)), size * 1.25),
        "top": (c + Vector((0, 0.001, d * 2)), size * 1.2), "rear": (c + Vector((0, -d * 2, 0)), size * 1.25),
    }
    for name, (loc, ortho) in views.items():
        camera(loc, c, ortho=ortho, lens=55)
        out.append(shot(os.path.join(outdir, prefix + name + ".png")))
    for pname, pose in (poses or {}).items():
        asm.set_pose(**pose)
        camera(iso, c, lens=55)
        out.append(shot(os.path.join(outdir, prefix + pname + ".png")))
    asm.set_pose()
    return [p for p in out if p]


def _ancestors(ob):
    s, p = set(), ob.parent
    while p is not None:
        s.add(p.name)
        p = p.parent
    return s


def section(outdir, fname, axis, val, cam_loc, cam_tgt, ortho, keep_side="-", scope=None,
            show=("Printed", "Purchased", "Fasteners", "Cables"), max_cut_verts=30000):
    """Cut everything at axis = val and render. keep_side '-' keeps the part below val (camera on '+').
    scope = set of joint names: only objects under those joints (plus 'static' if listed) are shown.
    Objects too heavy to boolean (> max_cut_verts) are hidden when they cross the plane."""
    k = "xyz".index(axis.lower())
    big = 5000
    lo, hi = [-big] * 3, [big] * 3
    if keep_side == "-":
        lo[k] = val
    else:
        hi[k] = val
    cutter = geom.box("SECTION_CUT", lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])
    cutter.data.materials.append(asm.mat(CUT))
    hidden, mods = [], []
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or ob is cutter or ob.hide_render or ob.get("marker"):
            continue
        cname = ob.users_collection[0].name if ob.users_collection else ""
        in_scope = scope is None or (_ancestors(ob) & scope) or ("static" in scope and not _ancestors(ob))
        if cname not in show or not in_scope:
            ob.hide_render = True
            hidden.append(ob)
            continue
        bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        mn, mx = min(v[k] for v in bb), max(v[k] for v in bb)
        gone = mn >= val if keep_side == "-" else mx <= val
        crosses = mn < val < mx
        if gone or (crosses and len(ob.data.vertices) > max_cut_verts):
            ob.hide_render = True
            hidden.append(ob)
        elif crosses:
            # Manifold on closed solids: EXACT turned PRT_jar_valve, PRT_base_shell and PRT_journal_plate inside out,
            # so they flooded the view and the v2 A1 finisher wrote its own pre-cut script (FINDINGS V2A1-T5)
            nm, vol = geom.solid_stats(ob)
            m = ob.modifiers.new("sec", 'BOOLEAN')
            m.operation, m.solver, m.object = 'DIFFERENCE', ('MANIFOLD' if not nm and vol > 0 else 'EXACT'), cutter
            if hasattr(m, "material_mode"):
                m.material_mode = 'TRANSFER'
            mods.append((ob, m))
    cutter.hide_render = True
    camera(cam_loc, cam_tgt, ortho=ortho)
    path = shot(os.path.join(outdir, fname))
    for ob, m in mods:
        ob.modifiers.remove(m)
    for ob in hidden:
        ob.hide_render = False
    geom.kill(cutter)
    return path


def explode_offsets(obs, scale=1.0):
    """{name: (dx, dy, dz)}: each object moved away from the assembly centre (scene_bounds) by 0.6 x scale of its box
    centre's distance from it. exploded() draws these; export.write_glb's assembly clip flies parts in along them."""
    lo, hi = scene_bounds()
    c = (lo + hi) / 2
    out = {}
    for ob in obs:
        b = [ob.matrix_world @ Vector(x) for x in ob.bound_box]
        out[ob.name] = tuple((sum(b, Vector()) / 8 - c) * 0.6 * scale)
    return out


def exploded(outdir, offsets=None, fname="exploded.png", scale=1.0, cam=None):
    """Exploded view. offsets: {object name: (dx, dy, dz)}; by default every object moves away from
    the assembly centre along its body's direction, scaled by `scale`. Fasteners and cables hidden."""
    asm.set_pose()
    lo, hi = scene_bounds()
    c = (lo + hi) / 2
    radial = explode_offsets([o for o in bpy.data.objects if o.type == 'MESH'], scale) if offsets is None else {}
    saved = {}
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        cn = ob.users_collection[0].name if ob.users_collection else ""
        if cn in ("Fasteners", "Cables"):
            saved[ob.name] = None
            ob.hide_render = True
            continue
        off = (offsets or radial).get(ob.name)
        if off is None:
            continue
        saved[ob.name] = ob.matrix_world.copy()
        ob.matrix_world = Matrix.Translation(Vector(off)) @ ob.matrix_world
    bpy.context.view_layer.update()
    size = max(hi - lo)
    camera(cam or (c + Vector((0.85, -1.0, 0.75)) * size * 3.0), c, lens=45)
    path = shot(os.path.join(outdir, fname))
    for name, mw in saved.items():
        ob = bpy.data.objects[name]
        if mw is None:
            ob.hide_render = False
        else:
            ob.matrix_world = mw
    bpy.context.view_layer.update()
    return path


def contact_sheet(stl_dir, out_png, cols=6, gap=30.0, bed=(256, 256)):
    """All STLs in print orientation on one image, each with its name and the P1S bed outline.
    Run in a fresh process (it resets the scene). Attempt 1's designer found this one image the
    fastest print-orientation review (FINDINGS 'What worked')."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    fs = sorted(f for f in os.listdir(stl_dir) if f.endswith(".stl"))
    x = y = rowh = 0.0
    m_part = bpy.data.materials.new("p")
    m_part.diffuse_color = asm.PALETTE["pla_a"]
    m_bed = bpy.data.materials.new("b")
    m_bed.diffuse_color = (0.93, 0.93, 0.92, 1)
    xmax = 0.0
    for i, f in enumerate(fs):
        before = set(bpy.data.objects)
        bpy.ops.wm.stl_import(filepath=os.path.join(stl_dir, f))
        o = [ob for ob in bpy.data.objects if ob not in before][0]
        o.data.materials.append(m_part)
        bb = [Vector(c) for c in o.bound_box]
        w = max(v.x for v in bb) - min(v.x for v in bb)
        h = max(v.y for v in bb) - min(v.y for v in bb)
        if i % cols == 0 and i:
            y -= rowh + gap + 12
            x, rowh = 0.0, 0.0
        o.location = (x - min(v.x for v in bb), y - max(v.y for v in bb), -min(v.z for v in bb))
        t = bpy.data.curves.new(f, 'FONT')
        t.body = "%s  %.0fx%.0fx%.0f" % (f[:-4], w, h, max(v.z for v in bb) - min(v.z for v in bb))
        t.size = 6
        to = bpy.data.objects.new(f + "_t", t)
        bpy.context.scene.collection.objects.link(to)
        to.location = (x, y + 4, 0)
        to.data.materials.append(asm.mat((0.04, 0.04, 0.04, 1)))
        x += max(w, 60) + gap
        xmax = max(xmax, x)
        rowh = max(rowh, h)
    # P1S bed footprint for scale, bottom-left
    bpy.ops.mesh.primitive_plane_add(size=1, location=(bed[0] / 2, y - rowh - gap - bed[1] / 2, -0.3))
    p = bpy.context.object
    p.scale = (bed[0], bed[1], 1)
    p.data.materials.append(m_bed)
    t = bpy.data.curves.new("bed", 'FONT')
    t.body, t.size = "P1S bed %dx%d" % bed, 8
    to = bpy.data.objects.new("bed_t", t)
    bpy.context.scene.collection.objects.link(to)
    to.location = (0, y - rowh - gap + 4, 0)
    setup(res=(1800, 1350))
    ymin = y - rowh - gap - bed[1]
    ymax = 20.0
    cx, cy = xmax / 2, (ymin + ymax) / 2
    tilt = math.radians(35)     # oblique so part heights read
    H = (ymax - ymin) * math.cos(tilt) + 60
    D = 4000
    camera((cx, cy - D * math.sin(tilt), D * math.cos(tilt)), (cx, cy, 0), ortho=max(xmax + 40, H * 4 / 3) * 1.05)
    return shot(out_png)


# ------------------------------------------------------------------ review markers

def marker_lentil(name, center, normal, d=13.0, t=7.0, color=(0.12, 0.31, 0.85, 1), parent=None):
    """M&M-sized lentil (13 x 7) with its thin axis along `normal`: show payload positions in sections."""
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
    bm.to_mesh(me)
    bm.free()
    q = Vector((0, 0, 1)).rotation_difference(Vector(normal).normalized())
    ob.matrix_world = Matrix.Translation(center) @ q.to_matrix().to_4x4() @ Matrix.Diagonal((d / 2, d / 2, t / 2, 1))
    me.materials.append(asm.mat(color))
    ob["marker"] = True
    if parent:
        p = bpy.data.objects[parent]
        mw = ob.matrix_world.copy()
        ob.parent = p
        ob.matrix_world = mw
    return ob


def marker_rod(name, a, b, r=0.6, color=(0.83, 0.16, 0.11, 1)):
    """Thin rod from a to b (tangent directions, ray paths)."""
    a, b = Vector(a), Vector(b)
    ob = geom.cyl(name, (0, 0), r, 0, (b - a).length, 'Z', n=10)
    q = Vector((0, 0, 1)).rotation_difference((b - a).normalized())
    geom.xform(ob, Matrix.Translation(a) @ q.to_matrix().to_4x4())
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(asm.mat(color))
    ob["marker"] = True
    return ob
