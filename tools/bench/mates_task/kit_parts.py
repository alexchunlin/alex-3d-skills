"""Purchased-part placeholders for the mates_task brief, each in the local frame its components.json entry describes.
Use them unmodified (don't cut or join them): the scorer finds each by its mesh.

    sys.path.insert(0, "<kit>"); import kit_parts as K
    servo = K.servo()          # an object named "servo" in its own frame; place it, then register it as BUY_servo
    K.C["servo"]["mass_g"]     # the data, from components.json next to this file
"""
import json, math, os
from cadlib import geom as G

HERE = os.path.dirname(os.path.abspath(__file__))
C = json.load(open(os.path.join(HERE, "components.json")))


def servo(name="servo"):
    s = C["servo"]
    L, W, H = s["case"]
    off, r, sp = s["spline"]["offset_from_case_centre"], s["spline"]["d"] / 2, s["spline"]["protrudes"]
    case = G.box(name, -off - L / 2, -off + L / 2, -W / 2, W / 2, -H, 0)
    return G.csg(case, add=[G.cyl(name + "_s", (0, 0), r, -0.01, sp, 'Z', n=24)])


def horn(name="horn"):
    h = C["horn"]
    hub = G.cyl(name + "_h", (0, 0), h["hub"]["d"] / 2, 0, h["hub"]["h"] + 0.01, 'Z', n=36)
    disc = G.cyl(name, (0, 0), h["disc"]["d"] / 2, h["hub"]["h"], h["hub"]["h"] + h["disc"]["t"], 'Z', n=60)
    bc, n = h["holes"]["bolt_circle_d"] / 2, h["holes"]["n"]
    holes = [G.cyl(name + "_x%d" % k, (bc * math.cos(2 * math.pi * k / n), bc * math.sin(2 * math.pi * k / n)),
                   h["holes"]["d"] / 2, -1, 10, 'Z', n=16) for k in range(n)]
    return G.csg(disc, add=[hub], sub=holes)


def pcb(name="pcb"):
    p = C["pcb"]
    L, W, T = p["board"]
    hx, hy = p["holes"]["rect"][0] / 2, p["holes"]["rect"][1] / 2
    board = G.box(name, -L / 2, L / 2, -W / 2, W / 2, 0, T)
    bl = p["components"]["block"]
    hd = p["components"]["header"]
    adds = [G.box(name + "_b", -bl[0] / 2, bl[0] / 2, -bl[1] / 2, bl[1] / 2, T - 0.01, T + bl[2]),
            G.box(name + "_h", hd["x"][0], hd["x"][1], hd["y"][0], hd["y"][1], T - 0.01, T + hd["h"])]
    holes = [G.cyl(name + "_x%d" % i, (sx * hx, sy * hy), p["holes"]["d"] / 2, -1, T + 1, 'Z', n=16)
             for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1)))]
    return G.csg(board, add=adds, sub=holes)


BUILDERS = {"BUY_servo": servo, "BUY_horn": horn, "BUY_pcb": pcb}
