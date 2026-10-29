"""Blender side of tools/bench/assembly.py: the scene as cadcheck reads it (its collections, its nut test, its
fastener axis and head height, its joint bodies), dumped as JSON. Run by assembly.py:

    Blender -b model.blend --python assembly_scan.py -- --config checks.json --scan-out scan.json

CAD_SCRIPTS names the skills/print-cad-blender/scripts dir whose cadcheck is imported (CADCHECK_NO_MAIN: import only).
"""
import json
import os
import sys

os.environ["CADCHECK_NO_MAIN"] = "1"
sys.path.insert(0, os.environ["CAD_SCRIPTS"])
import cadcheck as C  # noqa: E402

fst = []
for o in C.FASTENERS:
    rec = {"name": o.name, "nut": bool(C.is_nut(o)), "body": C.body(o), "part": o.get("part")}
    if not rec["nut"]:
        head, tip, d, hr, sr = C.fastener_axis(o)
        hh = C.head_height(o, head, d, sr)
        rec.update(d=round(2 * sr, 2), length=round((tip - head).length - hh, 1), head_d=round(2 * hr, 2),
                   source="cadlib" if "fst_head" in o.keys() else "geometry")
    fst.append(rec)
out = {"printed": [{"name": o.name, "body": C.body(o)} for o in C.PRINTED],
       "purchased": [{"name": o.name, "body": C.body(o)} for o in C.PURCHASED],
       "cables": [o.name for o in C.CABLES], "fasteners": fst,
       "assembly_order": [s.get("step", "") for s in (C.CFG.get("assembly_order") or [])],
       "service_ops": len(C.CFG.get("service") or []), "slide_out_rows": len(C.CFG.get("slide_out") or []),
       "joins": [{"kind": j.get("kind"), "name": j.get("name")} for j in C.JOINS]}     # snap / pip_hinge records
with open(C._arg("--scan-out"), "w") as f:
    json.dump(out, f, indent=1)
print("ASSEMBLY_SCAN ok", len(out["printed"]), len(fst))
