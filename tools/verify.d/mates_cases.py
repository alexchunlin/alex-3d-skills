"""Unit cases for cadlib.mates (run by tools/verify.d/mates.sh through `cad build`): frames, chains, flips, prismatic,
pattern mismatches, loops, a fastened pattern end to end, print_rot, the mate table. Prints "MATES PASS|FAIL <case>".

    cad build tools/verify.d/mates_cases.py -- --out /tmp/mates-cases
"""
import json, math, os, sys, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
import bpy
from mathutils import Vector, Matrix
from cadlib import geom as G, asm as A, mates as M, export as E

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/mates-cases"
os.makedirs(OUT, exist_ok=True)
RESULTS = []


def say(ok, msg):
    RESULTS.append(ok)
    print("MATES %s %s" % ("PASS" if ok else "FAIL", msg))


def near(a, b, tol=1e-4):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _r(v):
    return [round(c, 3) + 0.0 for c in v]


def bbox(ob):
    vs = [ob.matrix_world @ v.co for v in ob.data.vertices]
    return [round(min(v[i] for v in vs), 4) + 0.0 for i in range(3)], [round(max(v[i] for v in vs), 4) + 0.0 for i in range(3)]


def prt(ob, name, **kw):
    info = dict(stl=name[4:], print_rot=A.R_ID, orient="flat", supports="no", infill=20)
    info.update(kw)
    return M.part(ob, name, 'PRT', "pla_a", **info)


def case(fn):
    try:
        fn()
    except Exception:
        traceback.print_exc()
        say(False, "%s raised" % fn.__name__)
    return fn


def raises(fn, *needles):
    try:
        fn()
    except M.MateError as e:
        msg = str(e)
        return all(n in msg for n in needles), msg
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)
    return False, "no error"


# ---------------------------------------------------------------- frames
@case
def face_to_face():
    A.new_scene()
    deck = G.box("deck", -40, 40, -40, 40, 0, 10)
    lid = G.box("lid", -20, 20, -10, 10, 0, 4)                 # modelled on its own underside
    M.connector(deck, "top", (0, 0, 10), z=(0, 0, 1))
    M.connector(lid, "bottom", (0, 0, 0), z=(0, 0, -1))         # z out of the lid's underside
    prt(deck, "PRT_deck"); prt(lid, "PRT_lid")
    M.mate("PRT_deck:top", "PRT_lid:bottom", gap=0.5)
    M.assemble("PRT_deck")
    lo, hi = bbox(bpy.data.objects["PRT_lid"])
    say(near(lo, [-20, -10, 10.5]) and near(hi, [20, 10, 14.5]),
        "face to face: both z out of their faces, gap 0.5 -> lid z %.2f..%.2f, not turned (x %.1f..%.1f)" % (lo[2], hi[2], lo[0], hi[0]))


@case
def rot_and_inverse():
    res = []
    for flip in (False, True):
        A.new_scene()
        deck = G.box("deck", -40, 40, -40, 40, 0, 10)
        bar = G.box("bar", 0, 30, -2, 2, 0, 4)                 # sticks out +X from its connector
        M.connector(deck, "top", (5, 5, 10), z=(0, 0, 1))
        M.connector(bar, "end", (0, 0, 0), z=(0, 0, -1))
        prt(deck, "PRT_deck"); prt(bar, "PRT_bar")
        if flip:   # declared child-first: the same placement
            M.mate("PRT_bar:end", "PRT_deck:top", rot=90)
        else:
            M.mate("PRT_deck:top", "PRT_bar:end", rot=90)
        M.assemble("PRT_deck")
        res.append(bbox(bpy.data.objects["PRT_bar"]))
    ok = all(near(r[0], [3, 5, 10]) and near(r[1], [7, 35, 14]) for r in res)
    say(ok, "rot 90 turns the bar from +X to +Y about the deck's z; declaring the mate child-first places it the same: %s / %s" % tuple(res))


@case
def default_x_rule():
    zs = {(0, 0, 1): (1, 0, 0), (0, 0, -1): (1, 0, 0), (1, 0, 0): (0, 0, 1), (-1, 0, 0): (0, 0, 1), (0, 1, 0): (1, 0, 0)}
    got = {z: tuple(round(c, 6) + 0.0 for c in M.default_x(z)) for z in zs}
    say(got == {k: tuple(float(c) for c in v) for k, v in zs.items()}, "default x: +X flattened into the face, +Z when z is along X: %s" % got)
    # a side mount: both parts modelled upright, connectors on X faces, mate without turning
    A.new_scene()
    wall = G.box("wall", 0, 5, -20, 20, 0, 40)
    box = G.box("box", -10, 0, -5, 5, 0, 8)
    M.connector(wall, "out", (5, 0, 20), z=(1, 0, 0))
    M.connector(box, "back", (-10, 0, 0), z=(-1, 0, 0))
    prt(wall, "PRT_wall"); prt(box, "PRT_box")
    M.mate("PRT_wall:out", "PRT_box:back")
    M.assemble("PRT_wall")
    lo, hi = bbox(bpy.data.objects["PRT_box"])
    say(near(lo, [5, -5, 20]) and near(hi, [15, 5, 28]), "side mount with default x keeps the box upright: %s %s" % (lo, hi))


# ---------------------------------------------------------------- chains and flips
@case
def chain_pan_tilt():
    A.new_scene()
    base = G.box("base", -30, 30, -30, 30, 0, 20)
    pan = G.cyl("pan", (0, 0), 25, 0, 5, 'Z')
    yoke = G.box("yoke", -3, 3, -10, 10, 0, 40)                  # upright plate, pivot hole at z 30
    head = G.box("head", 0, 20, -8, 8, -8, 8)                     # modelled about its pivot, nose +X
    M.connector(base, "deck", (0, 0, 20), z=(0, 0, 1))
    M.connector(pan, "bottom", (0, 0, 0), z=(0, 0, -1))
    M.connector(pan, "top", (10, 0, 5), z=(0, 0, 1))
    M.connector(yoke, "foot", (0, 0, 0), z=(0, 0, -1))
    M.connector(yoke, "pivot", (3, 0, 30), z=(1, 0, 0))          # out of the yoke's +X face
    M.connector(head, "pivot", (0, 0, 0), z=(-1, 0, 0))
    for o, n in ((base, "PRT_base"), (pan, "PRT_pan"), (yoke, "PRT_yoke"), (head, "PRT_head")):
        prt(o, n)
    M.mate("PRT_base:deck", "PRT_pan:bottom", "revolute", name="PIV_pan", lo=-90, hi=90, gap=0.5, sweep_step=15)
    M.mate("PRT_pan:top", "PRT_yoke:foot", "rigid", fit="press")
    M.mate("PRT_yoke:pivot", "PRT_head:pivot", "revolute", name="PIV_tilt", lo=-20, hi=45, gap=0.3)
    M.assemble("PRT_base")
    J = A.JOINTS
    ok = (J["PIV_pan"].parent is None and J["PIV_tilt"].parent == J["PIV_pan"] and J["PIV_tilt"]["joint_axis"] == "X"
          and near(J["PIV_tilt"].matrix_world.translation, (13, 0, 55.5)))
    say(ok, "chain base > pan (revolute Z) > yoke (rigid) > head (revolute X): PIV_tilt under PIV_pan at %s" %
        [round(c, 3) for c in J["PIV_tilt"].matrix_world.translation])
    lo, hi = bbox(bpy.data.objects["PRT_head"])
    say(near(lo, [13.3, -8, 47.5]) and near(hi, [33.3, 8, 63.5]), "head placed at the pivot: %s %s" % (lo, hi))
    A.set_pose(PIV_pan=90, PIV_tilt=30)
    F = M.frame_of("PRT_head:pivot")
    top = bpy.data.objects["PRT_head"].matrix_world @ Vector((13.3, 0, 63.5))
    exp_piv = (0.0, 13.3, 55.5)
    say(near(F.translation, exp_piv, 1e-3) and near(F.col[2][:3], (0, -1, 0), 1e-4),
        "connectors move with the part: head pivot at pan 90 is %s, z %s" % (_r(F.translation), _r(F.col[2][:3])))
    # tilt +30 about the yoke's +X takes the head's top (+8 Z off the axis) to (0, -4, 6.93); pan 90 then turns that
    # offset to (4, 0, 6.93) about the moved pivot
    exp = (4.0, 13.3, 55.5 + 8 * math.cos(math.radians(30)))
    say(near(top, exp, 1e-3), "pan 90 + tilt 30 (right-handed about the parent connector's z): head top at %s, expect %s" % (
        _r(top), _r(exp)))
    A.set_pose()


@case
def revolute_sign_flip():
    """A parent connector whose z is -Z: the PIV gets axis Z with lo/hi negated, and posing the mate value +30 turns the
    child +30 about the parent's z (-Z), i.e. -30 about world Z."""
    A.new_scene()
    ceil = G.box("ceil", -30, 30, -30, 30, 50, 60)
    arm = G.box("arm", 0, 40, -3, 3, 0, 5)                        # hangs below the ceiling, pointing +X
    M.connector(ceil, "under", (0, 0, 50), z=(0, 0, -1))
    M.connector(arm, "top", (0, 0, 5), z=(0, 0, 1))
    prt(ceil, "PRT_ceil"); prt(arm, "PRT_arm")
    M.mate("PRT_ceil:under", "PRT_arm:top", "revolute", name="PIV_sw", lo=-10, hi=60, home=5)
    M.assemble("PRT_ceil")
    e = A.JOINTS["PIV_sw"]
    ok1 = e["joint_axis"] == "Z" and near((e["joint_lo"], e["joint_hi"], e["joint_home"]), (-60, 10, -5))
    say(ok1, "parent z -Z: PIV_sw axis Z, lo/hi/home %s (mate -10..60 home 5)" % [e["joint_lo"], e["joint_hi"], e["joint_home"]])
    A.set_pose(PIV_sw=-30)   # mate value +30
    tip = bpy.data.objects["PRT_arm"].matrix_world @ Vector((40, 0, 45))
    exp = (40 * math.cos(math.radians(-30)), 40 * math.sin(math.radians(-30)), 45)
    say(near(tip, exp, 1e-3), "mate +30 about -Z moves the tip to %s (expect %s)" % (_r(tip), _r(exp)))
    A.set_pose()


@case
def prismatic():
    A.new_scene()
    rail = G.box("rail", -50, 50, -10, 10, 0, 10)
    car = G.box("car", -10, 10, -8, 8, 0, 6)
    M.connector(rail, "end", (-50, 0, 5), z=(-1, 0, 0))
    M.connector(car, "nose", (10, 0, 3), z=(1, 0, 0))
    prt(rail, "PRT_rail"); prt(car, "PRT_car")
    M.mate("PRT_rail:end", "PRT_car:nose", "prismatic", name="PIV_car", lo=0, hi=30, gap=2)
    M.assemble("PRT_rail")
    e = A.JOINTS["PIV_car"]
    ok = e.get("joint_kind") == "prismatic" and e["joint_axis"] == "X" and near((e["joint_lo"], e["joint_hi"]), (-30, 0))
    A.set_pose(PIV_car=-30)   # mate value 30 = 30 mm apart along the rail end's z (-X)
    lo, hi = bbox(bpy.data.objects["PRT_car"])
    A.set_pose()
    say(ok and near(lo, [-102, -8, 2]) and near(hi, [-82, 8, 8]),
        "prismatic along the parent's z (-X): PIV axis X lo/hi %s; at mate 30 the car spans x %.1f..%.1f" % (
            [e["joint_lo"], e["joint_hi"]], lo[0], hi[0]))


# ---------------------------------------------------------------- patterns
def _pcb_scene(deck_pat, board_pat, deck_hole="M2.5", board_hole="M2.5", kind="fastened"):
    A.new_scene()
    deck = G.box("deck", -40, 40, -30, 30, 0, 4)
    board = G.box("board", -25, 25, -20, 20, 0, 1.6)
    M.connector(deck, "pcb", (0, 0, 4), z=(0, 0, 1), pattern=deck_pat, hole=deck_hole)
    M.connector(board, "mount", (0, 0, 0), z=(0, 0, -1), pattern=board_pat, hole=board_hole)
    prt(deck, "PRT_deck")
    M.part(board, "BUY_board", 'BUY', "pcb", mass_g=10, src="test")
    M.mate("PRT_deck:pcb", "BUY_board:mount", kind, name="pcb")
    M.assemble("PRT_deck")


@case
def pattern_mismatch():
    ok, msg = raises(lambda: _pcb_scene(M.rect(42, 32.5), M.rect(42, 32), kind="rigid"),
                     "rect(42, 32.5)", "rect(42, 32)", "0.250 mm")
    say(ok, "pitch mismatch fails with both specs: " + msg.replace("\n", " | ")[:260])
    ok, msg = raises(lambda: _pcb_scene(M.rect(42, 32), M.line(42, 2), kind="rigid"), "4 points on a, 2 on b",
                     "rect(42, 32)", "line(42, 2)")
    say(ok, "count mismatch fails: " + msg.splitlines()[0][:160])
    ok, msg = raises(lambda: _pcb_scene(M.rect(42, 32), M.rect(42, 32), board_hole="M3", kind="rigid"),
                     "hole sizes differ (M2.5 vs M3)")
    say(ok, "hole size mismatch fails: " + msg.splitlines()[0][:160])
    ok, msg = raises(lambda: _pcb_scene(M.circle(30, 4, 45), M.circle(30, 4, 45), kind="rigid"))
    say(msg == "no error", "circle(30, 4, 45) on both faces matches (the board's y flips, the 4-fold circle maps onto itself)")
    ok, msg = raises(lambda: _pcb_scene(M.circle(30, 3, 90), M.circle(30, 3, 90), kind="rigid"), "mirrored in y", "a0 -> -a0")
    say(ok, "circle(30, 3, 90) typed the same on both faces fails with the mirror hint (each face sees the pattern from "
            "outside): " + msg.splitlines()[0][-150:])
    ok, msg = raises(lambda: _pcb_scene(M.circle(30, 3, 90), M.circle(30, 3, -90), kind="rigid"))
    say(msg == "no error", "circle(30, 3, 90) against circle(30, 3, -90) matches")


@case
def fastened_pattern_end_to_end():
    A.new_scene()
    deck = G.box("deck", -40, 40, -30, 30, 0, 4)
    posts = [G.cyl("p%d" % i, (x, y), 3.5, 3.9, 12, 'Z') for i, (x, y) in enumerate(M.pattern_points(M.rect(42, 32)))]
    deck = G.csg(deck, add=posts)
    board = G.box("board", -25, 25, -20, 20, 0, 1.6)
    board = G.csg(board, sub=[G.cyl("h%d" % i, (x, y), 1.45, -1, 3, 'Z') for i, (x, y) in enumerate(M.pattern_points(M.rect(42, 32)))])
    M.connector(deck, "pcb", (0, 0, 12), z=(0, 0, 1), pattern=M.rect(42, 32), hole="M2.5")
    M.connector(board, "mount", (0, 0, 0), z=(0, 0, -1), pattern=M.rect(42, 32), hole="M2.5")
    prt(deck, "PRT_deck")
    M.part(board, "BUY_board", 'BUY', "pcb", mass_g=10, src="test")
    M.mate("PRT_deck:pcb", "BUY_board:mount", "fastened", name="pcb", fit="clearance",
           fastener=dict(style="selftap", head="pan"), step="board")
    M.assemble("PRT_deck")
    fst = sorted(n for n in A.PARTS if n.startswith("FST_pcb"))
    L = [A.PARTS[n]["length"] for n in fst]
    heads = [tuple(round(c, 2) for c in A.PARTS[n]["head"]) for n in fst]
    want = [(-21.0, -16.0, 13.6), (21.0, -16.0, 13.6), (-21.0, 16.0, 13.6), (21.0, 16.0, 13.6)]
    say(fst == ["FST_pcb_%d" % i for i in range(4)] and heads == want and len(set(L)) == 1,
        "fastened rect(42, 32) M2.5: 4 screws, heads on the board top at %s, length %s" % (heads, L))
    tbl = A.MATE_TABLE[0]
    say(tbl["fastener"]["names"] == fst and tbl["kind"] == "fastened" and tbl["pattern_a"] == "rect(42, 32)",
        "mate table row: %s" % json.dumps({k: tbl[k] for k in ("name", "kind", "a", "b", "fit", "pattern_a", "hole_a")}))
    A.write_manifest(os.path.join(OUT, "pcb", "manifest.json"))
    E.save_blend(os.path.join(OUT, "pcb", "pcb.blend"))


# ---------------------------------------------------------------- errors
def _two(kind="rigid"):
    A.new_scene()
    a = G.box("a", 0, 10, 0, 10, 0, 10)
    b = G.box("b", 0, 10, 0, 10, 0, 10)
    c = G.box("c", 0, 10, 0, 10, 0, 10)
    for o in (a, b, c):
        M.connector(o, "top", (5, 5, 10), z=(0, 0, 1))
        M.connector(o, "bot", (5, 5, 0), z=(0, 0, -1))
        M.connector(o, "tilted", (5, 5, 10), z=(0, 1, 1))
    prt(a, "PRT_a"); prt(b, "PRT_b"); prt(c, "PRT_c")


@case
def errors():
    def loop():
        _two()
        M.mate("PRT_a:top", "PRT_b:bot")
        M.mate("PRT_b:top", "PRT_c:bot")
        M.mate("PRT_c:top", "PRT_a:bot")
        M.assemble("PRT_a")
    ok, msg = raises(loop, "closes a loop", "PRT_a -> PRT_b")
    say(ok, "loop raises: " + msg[:200])

    def lost():
        _two()
        M.mate("PRT_a:top", "PRT_b:bot")
        M.assemble("PRT_a")
    ok, msg = raises(lost, "not mated to the ground", "PRT_c")
    say(ok, "unreached part raises: " + msg[:120])

    def tilted():
        _two()
        M.mate("PRT_a:tilted", "PRT_b:bot", "revolute", name="PIV_t", lo=0, hi=10)
        M.mate("PRT_b:top", "PRT_c:bot")
        M.assemble("PRT_a")
    ok, msg = raises(tilted, "not a world axis")
    say(ok, "tilted revolute axis raises: " + msg[:140])

    def badref():
        _two()
        M.mate("PRT_a:topp", "PRT_b:bot")
        M.assemble("PRT_a")
    ok, msg = raises(badref, "has no connector 'topp'", "'bot'")
    say(ok, "unknown connector lists the part's connectors: " + msg[:140])

    def norange():
        _two()
        M.mate("PRT_a:top", "PRT_b:bot", "revolute", name="PIV_x")
    ok, msg = raises(norange, "needs lo and hi")
    say(ok, "revolute without a range raises")

    def moved():
        A.new_scene()
        a = G.box("a", 0, 1, 0, 1, 0, 1)
        a.location = (5, 0, 0)
        prt(a, "PRT_a")
    ok, msg = raises(moved, "has a transform")
    say(ok, "a part with an object transform raises")


@case
def print_rot_local():
    A.new_scene()
    wall = G.box("wall", 0, 5, -20, 20, 0, 40)
    plate = G.box("plate", -10, 10, -10, 10, 0, 3)              # modelled flat, printed flat (R_ID in its frame)
    M.connector(wall, "out", (5, 0, 20), z=(1, 0, 0))
    M.connector(plate, "back", (0, 0, 0), z=(0, 0, -1))
    prt(wall, "PRT_wall"); prt(plate, "PRT_plate", print_rot=A.R_ID)
    M.mate("PRT_wall:out", "PRT_plate:back")
    M.assemble("PRT_wall")
    R = Matrix(A.PARTS["PRT_plate"]["print_rot"])
    lo, hi = bbox(bpy.data.objects["PRT_plate"])
    # the plate stands on the wall's +X face; its own -Z (the face it was modelled on) is now world -X: print_rot
    # must take world -X to print -Z
    d = R @ Vector((-1, 0, 0))
    say(near(lo, [5, -10, 10]) and near(hi, [8, 10, 30]) and near(d, (0, 0, -1)),
        "print_rot in the part's frame: the plate on a wall prints flat (world -X -> print %s)" % _r(d))


@case
def purchased_from_components():
    sys.path.insert(0, os.path.join(HERE, "..", "..", "components"))
    import placeholders as PH
    A.new_scene()
    deck = G.box("deck", -80, 40, -30, 30, 0, 4)
    M.connector(deck, "servo", (-40, 0, 4), (0, 0, 1))
    prt(deck, "PRT_deck")
    srv = M.from_component(PH.servo("servo"), PH.C["hiwonder_bus_servo"])
    horn = M.from_component(PH.horn("horn"), PH.C["servo_horn_disc"])
    M.part(srv, "BUY_servo", 'BUY', "buy", mass_g=66, src="components.json")
    M.part(horn, "BUY_horn", 'BUY', "buy_metal", mass_g=4, src="components.json")
    M.mate("PRT_deck:servo", "BUY_servo:bottom", "rigid", name="servo")
    M.mate("BUY_servo:spline", "BUY_horn:hub", "revolute", name="PIV_arm", lo=-90, hi=90, fit="press")
    M.assemble("PRT_deck")
    F = M.frame_of("BUY_horn:face")
    e = A.JOINTS["PIV_arm"]
    say(near(e.matrix_world.translation, (-30, 0, 47.9)) and near(F.translation, (-30, 0, 51.8)) and len(M.world_points("BUY_horn:face")) == 8,
        "components.json connectors: servo on the deck by its case bottom, horn on the spline (PIV_arm at %s), horn face "
        "pattern circle(14, 8, 0) at %s" % (_r(e.matrix_world.translation), _r(F.translation)))


ok = all(RESULTS)
print("MATES_DONE %d/%d" % (sum(RESULTS), len(RESULTS)))
