"""Test scene for cadcheck's exposure check on PCBs, plugs and screw heads (sourced by tools/verify.d/exposure_more.sh).

    cad build tools/verify.d/exposure_more_build.py -- --out /tmp/alex3d-verify/exm

A closed box shell, 80 x 60 x 40 mm, 3 mm side and bottom walls and a 6 mm top plate. Writes exm.blend, checks.json
(defaults) and checks_ok.json (heads_ok silences the proud head).
Must warn:
  BUY_exm_board     PCB by name (*board*), 30 x 20 x 1.6, half outside the +x wall (V2A1-F11: a PCB seen from outside)
  BUY_exm_widget    plug by its buy_kind prop (its name matches no glob), half outside the -y wall
  FST_exm_proud     M3 cap head on the top face, standing 3 mm proud (#40: dark heads on a cover, a proud pan head)
Must not warn:
  BUY_exm_usbc_plug plug by name (*usb*, *plug*), fully inside the shell
  FST_exm_cbore     M3 cap head in a 3 mm deep, 6.5 mm counterbore in the top plate (features counterbore_d)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, asm as A, export as E

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-exm-test"
DOWN = (0, 0, -1)
A.new_scene()
cut = [G.box("cav", -37, 37, -27, 27, 3, 34),
       G.cyl("pilot_p", (-20, 0), 1.25, 30, 41, 'Z'), G.cyl("pilot_c", (20, 0), 1.25, 30, 41, 'Z'),
       G.cyl("cbore", (20, 0), 3.25, 37, 41, 'Z')]
shell = G.csg(G.box("PRT_exm_shell", -40, 40, -30, 30, 0, 40), sub=cut)
A.part(shell, "PRT_exm_shell", 'PRT', "pla_a", stl="exm_shell", print_rot=A.R_ID, orient="flat", supports="no", infill=20)
A.part(G.box("BUY_exm_board", 25, 55, -10, 10, 10, 11.6), "BUY_exm_board", 'BUY', "pcb", mass_g=10, src="test")
A.part(G.box("BUY_exm_widget", -10, 10, -40, -20, 15, 22), "BUY_exm_widget", 'BUY', "buy", mass_g=5, src="test", buy_kind="plug")
A.part(G.box("BUY_exm_usbc_plug", -20, -8, -5, 5, 5, 12), "BUY_exm_usbc_plug", 'BUY', "buy", mass_g=5, src="test")
A.fastener("FST_exm_proud", (-20, 0, 40), DOWN, 8, spec="M3_cap")
A.fastener("FST_exm_cbore", (20, 0, 37), DOWN, 6, spec="M3_cap")
os.makedirs(OUT, exist_ok=True)
E.save_blend(os.path.join(OUT, "exm.blend"))
with open(os.path.join(OUT, "checks.json"), "w") as f:
    json.dump({}, f)
with open(os.path.join(OUT, "checks_ok.json"), "w") as f:
    json.dump({"exposure": {"heads_ok": ["FST_exm_proud"]}}, f)
print("EXM_BUILT")
