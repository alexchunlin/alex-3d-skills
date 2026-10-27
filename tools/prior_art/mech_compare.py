"""Prior-art measurement: cadsmith's `mech` clearance sweep against cadcheck on attempt 1.

    git clone https://github.com/JonFermin/cadsmith /tmp/x/cs && git -C /tmp/x/cs checkout 00c334d
    gunzip -c examples/mm-launcher-a1/mm_launcher_a1.blend.gz > /tmp/x/a1.blend
    Blender -b /tmp/x/a1.blend --factory-startup --python-exit-code 1 -P mech_export.py -- <parts_dir> <objects...>
    uv run --no-project --python 3.12 --with 'build123d==0.13.0' --with numpy==2.5.4 --with scipy==1.18.1 \
        python -I mech_compare.py /tmp/x/cs <parts_dir> <out_dir> [tilt_lo tilt_hi] > result.json

cadsmith is MIT (c) 2026 Jonathan Fermin; the clone is put on sys.path here, nothing is copied or run from inside it.
The object lists for mech_export.py are in its docstring: 13 parts, or 15 with the tilt journal (PRT_yoke_arm_L,
PRT_arm_cap_L). Each exported STL becomes an OCC solid (StlAPI read, sewing, MakeSolid, ShapeFix, orientation by
signed volume; time and validity per part are reported). The assembly mirrors the blend's pivots: PIV_tilt (X through
its origin) carries the trunnion and everything on the tilt body, PIV_flywheel spins the flywheel in the launcher
body, PIV_feeder spins the feeder disc in the feeder plate; the pan body is ground. Fasteners are parts fixed to the
body they sit on (as cadcheck reads them). Clearance 0.5 mm, as cadcheck's `clearance.min_mm`. Studies: tilt over
[tilt_lo, tilt_hi] in 2.5 deg frames (default the 0..45 stop; mech rejects a drive past a joint's limits, so the
overtravel run widens the limits instead), flywheel and feeder a full turn at cadcheck's steps (60 and 30 deg).
MECH_CHECK_HINGE=1 holds the A1-F9 pair (arm_cover_L / trunnion_L) to the clearance with `check_clearance`.

The output's `f9_pair` records why mech exempts that pair: `asm.is_joined` is true when both parts come within
`pin_tol` (5 mm) of the tilt axis and touch at home, and `tilt_parent` is the hinge's parent part.
"""
import json, os, sys, time

clone, parts_dir, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
tilt = (float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else (0.0, 45.0)
sys.path.insert(0, clone)

from OCP.StlAPI import StlAPI_Reader
from OCP.TopoDS import TopoDS_Shape, TopoDS
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
from OCP.ShapeFix import ShapeFix_Solid
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopAbs import TopAbs_SHELL
from OCP.TopExp import TopExp_Explorer
from build123d import Solid
from mech import Assembly, analyze

scene = json.load(open(os.path.join(parts_dir, "scene.json")))
piv = scene["pivots"]
load_log = {}


def stl_solid(name):
    t = time.time()
    raw = TopoDS_Shape()
    StlAPI_Reader().Read(raw, os.path.join(parts_dir, name + ".stl"))
    sew = BRepBuilderAPI_Sewing(1e-4)
    sew.Add(raw)
    sew.Perform()
    ex = TopExp_Explorer(sew.SewedShape(), TopAbs_SHELL)
    mk = BRepBuilderAPI_MakeSolid()
    n_shells = 0
    while ex.More():
        mk.Add(TopoDS.Shell(ex.Current()))
        n_shells += 1
        ex.Next()
    fix = ShapeFix_Solid(mk.Solid())
    fix.Perform()
    s = Solid(fix.Solid())
    if s.volume < 0:
        s = Solid(TopoDS.Solid(s.wrapped.Reversed()))
    load_log[name] = {"seconds": round(time.time() - t, 2), "shells": n_shells, "volume_mm3": round(s.volume, 1),
                      "valid": bool(BRepCheck_Analyzer(s.wrapped).IsValid())}
    return s


# The tilt hinge's parent: with the journal parts exported (PRT_yoke_arm_L, PRT_arm_cap_L, the real bearing), the yoke
# arm; in the 13-part export PRT_arm_cover_L stands in for it. The 15-part run is the fair one. In both, mech exempts the
# A1-F9 pair (arm_cover_L / trunnion_L): each part is within pin_tol of the tilt axis and they touch at home, so
# `is_joined` holds whichever part is the parent (see `f9_pair` in the output).
journal = [n for n in ("PRT_yoke_arm_L", "PRT_arm_cap_L") if n in scene["objects"]]
ground = ["PRT_hopper", "PRT_feeder_plate", "PRT_arm_cover_L", "FST_cap_R-1"] + journal
on_tilt = ["PRT_launcher_body", "PRT_launcher_cover", "FST_motor_0", "FST_motor_1", "FST_motor_2", "FST_motor_3"]
asm = Assembly("a1_prior_art", clearance=0.5)
for n in ground:
    asm.part(n, stl_solid(n), ground=True)
for n in ["PRT_trunnion_L"] + on_tilt + ["PRT_flywheel", "PRT_feeder_disc"]:
    asm.part(n, stl_solid(n))
asm.revolute("PIV_tilt", journal[0] if journal else "PRT_arm_cover_L", "PRT_trunnion_L", origin=piv["PIV_tilt"]["origin"],
             axis=piv["PIV_tilt"]["x"], limits=tilt)
for n in on_tilt:
    asm.fix(n, "PRT_trunnion_L")
asm.revolute("PIV_flywheel", "PRT_launcher_body", "PRT_flywheel", origin=piv["PIV_flywheel"]["origin"],
             axis=piv["PIV_flywheel"]["x"])
asm.revolute("PIV_feeder", "PRT_feeder_plate", "PRT_feeder_disc", origin=piv["PIV_feeder"]["origin"],
             axis=piv["PIV_feeder"]["z"])
if os.environ.get("MECH_CHECK_HINGE"):   # hold the hinge-carrying pair to the clearance too (off by default)
    asm.check_clearance("PRT_arm_cover_L", "PRT_trunnion_L")
asm.study("tilt", drive={"PIV_tilt": tilt}, frames=int(round((tilt[1] - tilt[0]) / 2.5)) + 1)
asm.study("flywheel", drive={"PIV_flywheel": (0, 300)}, frames=6)
asm.study("feeder", drive={"PIV_feeder": (0, 330)}, frames=12)

f9 = ("PRT_arm_cover_L", "PRT_trunnion_L")
tj = asm.joints["PIV_tilt"]
f9_pair = {"tilt_parent": tj.parent, "is_joined": bool(asm.is_joined(*f9)), "touching_at_home": bool(asm._touching(*f9)),
           "pin_tol_mm": asm.pin_tol, "within_pin_tol_of_tilt_axis": asm._carriers(list(asm.parts), tj.origin, tj.axis)}
t = time.time()
report = analyze(asm, export=True, out_root=out_dir, progress=False)
print(json.dumps({"tilt": tilt, "objects": sorted(scene["objects"]), "f9_pair": f9_pair, "load": load_log,
                  "analyze_seconds": round(time.time() - t, 1), "report": report}, default=str))
