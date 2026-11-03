"""Test scene for cadcheck's exposure check on PCBs, plugs and screw heads (sourced by tools/verify.d/exposure_more.sh).

    cad build tools/verify.d/exposure_more_build.py -- --out /tmp/alex3d-verify/exm

A closed box shell, 80 x 60 x 40 mm, 3 mm side and bottom walls and a 6 mm top plate. Writes exm.blend, checks.json
(defaults), checks_on.json (plugs and heads opted in) and checks_ok.json (also heads_ok for the proud head and pcbs_ok
for BUY_exm_board_peek). With the defaults the two PCBs warn; opted in, the plug and the head too:
  BUY_exm_board      PCB by name (*board*), 30 x 20 x 1.6, half outside the +x wall (V2A1-F11: a PCB seen from outside)
  BUY_exm_board_peek PCB 14 x 15 standing 0.5 mm behind the -x wall, seen through a 10 mm hole: just over pcb_min_share
  BUY_exm_widget     plug by its buy_kind prop (its name matches no glob), half outside the -y wall
  FST_exm_proud      M3 cap head on the top face, standing 3 mm proud (#40: dark heads on a cover, a proud pan head)
Never warn:
  BUY_exm_board_edge PCB 14 x 15 standing 0.5 mm behind the +x wall, seen through an 8 mm hole in it: a few exposed
                     samples, under pcb_min_share (as the v2a2-a7 servo controller behind its slot, 2 of 222)
  BUY_exm_usbc_plug  plug by name (*usb*, *plug*), fully inside the shell
  BUY_exm_usb_board  matches a PCB glob (*board*) and a plug glob (*usb*): checked as a PCB, by default; inside
  FST_exm_cbore      M3 cap head 0.5 mm below the surface in a 3.5 mm deep, 6.5 mm counterbore (features counterbore_d)
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
       G.cyl("cbore", (20, 0), 3.25, 36.5, 41, 'Z'), G.cyl("peep", (19, 22), 4.0, 36, 41, 'X'),
       G.cyl("peep2", (19, 22), 5.0, -41, -36, 'X')]
shell = G.csg(G.box("PRT_exm_shell", -40, 40, -30, 30, 0, 40), sub=cut)
A.part(shell, "PRT_exm_shell", 'PRT', "pla_a", stl="exm_shell", print_rot=A.R_ID, orient="flat", supports="no", infill=20)
A.part(G.box("BUY_exm_board", 25, 55, -10, 10, 10, 11.6), "BUY_exm_board", 'BUY', "pcb", mass_g=10, src="test")
A.part(G.box("BUY_exm_board_edge", 35, 36.5, 12, 26, 15, 30), "BUY_exm_board_edge", 'BUY', "pcb", mass_g=5, src="test")
A.part(G.box("BUY_exm_board_peek", -36.5, -35, 12, 26, 15, 30), "BUY_exm_board_peek", 'BUY', "pcb", mass_g=5, src="test")
A.part(G.box("BUY_exm_usb_board", -20, -8, 10, 20, 5, 7), "BUY_exm_usb_board", 'BUY', "pcb", mass_g=5, src="test")
A.part(G.box("BUY_exm_widget", -10, 10, -40, -20, 15, 22), "BUY_exm_widget", 'BUY', "buy", mass_g=5, src="test", buy_kind="plug")
A.part(G.box("BUY_exm_usbc_plug", -20, -8, -5, 5, 5, 12), "BUY_exm_usbc_plug", 'BUY', "buy", mass_g=5, src="test")
A.fastener("FST_exm_proud", (-20, 0, 40), DOWN, 8, spec="M3_cap")
A.fastener("FST_exm_cbore", (20, 0, 36.5), DOWN, 6, spec="M3_cap")
os.makedirs(OUT, exist_ok=True)
E.save_blend(os.path.join(OUT, "exm.blend"))
with open(os.path.join(OUT, "checks.json"), "w") as f:
    json.dump({}, f)
with open(os.path.join(OUT, "checks_ok.json"), "w") as f:
    json.dump({"exposure": {"plugs": True, "heads": True, "heads_ok": ["FST_exm_proud"], "pcbs_ok": ["BUY_exm_board_peek"]}}, f)
with open(os.path.join(OUT, "checks_on.json"), "w") as f:
    json.dump({"exposure": {"plugs": True, "heads": True}}, f)
print("EXM_BUILT")
