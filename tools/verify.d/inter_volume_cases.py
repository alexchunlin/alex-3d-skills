"""cadcheck.inter_volume: the EXACT-solver retry must fix the open-tube artefact and nothing else (run by cable_router.sh).

1. artefact: the A3 blend's own open (unwelded) CAB_12v_ctrl tube and BUY_servo_controller, controller as the base.
   Raw EXACT returns the tube's whole volume (1331.9 mm3); inter_volume must report the real overlap (38.0).
   Simple synthetic tubes through boxes don't trigger the artefact, so the real pair is loaded from the A3 blend.
2. containment: a closed cube wholly inside a non-manifold box reports the cube's whole volume, in both orders.
3. open tube wholly inside a closed box: the retry fires (result = the tube's own volume) but must keep it.

    Blender -b --factory-startup --python inter_volume_cases.py -- <skill scripts dir> <A3 blend>
Prints one line: IVOL {json}.
"""
import bpy, bmesh, json, os, sys
os.environ["CADCHECK_NO_MAIN"] = "1"
ARGS = sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, ARGS[0])
sys.argv = sys.argv[:sys.argv.index("--") + 1]          # cadcheck reads its own args after "--"
import cadcheck as C  # noqa: E402


def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def box(name, lo, hi, split_top=False):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = [lo[i] if v.co[i] < 0 else hi[i] for i in range(3)]
    if split_top:      # non-manifold but still closed in shape: the top face's edges are split
        top = [f for f in bm.faces if f.normal.z > 0.5][0]
        bmesh.ops.split_edges(bm, edges=list(top.edges))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me))


def open_tube(name, a, b, r):
    """The pre-weld cadlib/D3 tube: curve bevel with fill caps, cap rings not joined to the tube (non-manifold)."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(1)
    sp.points[0].co = (*a, 1)
    sp.points[1].co = (*b, 1)
    cu.bevel_depth = r
    cu.bevel_resolution = 3
    cu.use_fill_caps = True
    tmp = link(bpy.data.objects.new(name + "_c", cu))
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(tmp)
    return link(bpy.data.objects.new(name, me))


out = {}
if len(ARGS) > 1 and os.path.exists(ARGS[1]):
    with bpy.data.libraries.load(ARGS[1], link=False) as (src, dst):
        dst.objects = ["CAB_12v_ctrl", "BUY_servo_controller"]
    cab, ctrl = (link(o) for o in dst.objects)
    bpy.context.view_layer.update()
    out.update(a3_tube_manifold=C.manifold_ok(cab), a3_tube_own_mm3=round(C.own_volume(cab), 1),
               a3_raw_ctrl_first_mm3=round(C.inter_volume(ctrl, cab, _swapped=True)[0], 1),   # EXACT, no retry
               a3_ctrl_first_mm3=round(C.inter_volume(ctrl, cab)[0], 1),
               a3_cab_first_mm3=round(C.inter_volume(cab, ctrl)[0], 1))
outer = box("PRT_outer", (-20, -20, -20), (20, 20, 20), split_top=True)
inner = box("PRT_inner", (-2.5, -2.5, -2.5), (2.5, 2.5, 2.5))       # 125 mm3, wholly inside outer
t_in = open_tube("CAB_inside", (100, 0, 0), (120, 0, 0), 2.0)
blk2 = box("BUY_block2", (90, -10, -10), (130, 10, 10))               # closed, holds the whole open tube
bpy.context.view_layer.update()
out.update(outer_manifold=C.manifold_ok(outer), inner_in_outer_mm3=round(C.inter_volume(inner, outer)[0], 1),
           outer_around_inner_mm3=round(C.inter_volume(outer, inner)[0], 1),
           tube_inside_own_mm3=round(C.own_volume(t_in), 1),
           tube_inside_block_first_mm3=round(C.inter_volume(blk2, t_in)[0], 1),
           tube_inside_tube_first_mm3=round(C.inter_volume(t_in, blk2)[0], 1))
print("IVOL " + json.dumps(out))
