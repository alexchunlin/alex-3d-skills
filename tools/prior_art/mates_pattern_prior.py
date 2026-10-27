"""Prior art for cadlib.mates: what features.fastener_joint does when the screw pattern a designer typed for the deck
posts is off the purchased board's hole pattern (the board's holes are rect(42, 32), the posts rect(42, 32 + d)).

    cad build tools/prior_art/mates_pattern_prior.py -- --out /tmp/mates-prior
Prints one PRIOR line per offset, writes pattern_prior.json and off_<d>/pcb.blend (then `cad check` each, no config).
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, asm as A, features as F, export as E

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/mates-prior"
os.makedirs(OUT, exist_ok=True)
res = []
for d in (0.0, 0.25, 0.5, 1.0, 2.0):
    A.new_scene()
    py = 32.0 + d
    posts = [G.cyl("p%d" % i, (sx * 21, sy * py / 2), 3.5, 3.9, 12, 'Z') for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1)))]
    deck = G.csg(G.box("PRT_deck", -40, 40, -30, 30, 0, 4), add=posts)
    board = G.box("BUY_board", -25, 25, -20, 20, 12, 13.6)
    board = G.csg(board, sub=[G.cyl("h%d" % i, (sx * 21, sy * 16), 1.45, 11, 15, 'Z') for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1)))])
    cuts, out = {}, []
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        at = (sx * 21, sy * py / 2, 13.6)
        try:
            F.fastener_joint("FST_pcb_%d" % i, "M2.5", at, (0, 0, -1), [board, deck], head="pan", cuts=cuts)
            st = A.PARTS["FST_pcb_%d" % i]["fastener_joint"]["stack"]
            out.append({"ok": True, "stack": st, "board_cut": bool(cuts.get("BUY_board"))})
        except F.FastenerError as e:
            out.append({"ok": False, "error": str(e)[:200]})
    if cuts.get("PRT_deck"):
        deck = G.csg(deck, sub=cuts["PRT_deck"])
    A.part(deck, "PRT_deck", 'PRT', "pla_a", stl="deck", print_rot=A.R_ID, orient="flat", supports="no", infill=20)
    A.part(board, "BUY_board", 'BUY', "pcb", mass_g=10, src="test")
    E.save_blend(os.path.join(OUT, "off_%g" % d, "pcb.blend"))
    r = {"offset_mm": d, "raised": sum(not o["ok"] for o in out), "board_recut": any(o.get("board_cut") for o in out),
         "first": out[-1]}
    res.append(r)
    print("PRIOR offset %.2f: %d of 4 raise; board gets new holes: %s; %s" % (
        d, r["raised"], r["board_recut"], (out[-1].get("error") or "stack %s" % out[-1]["stack"])[:230]))
json.dump(res, open(os.path.join(OUT, "pattern_prior.json"), "w"), indent=1)
