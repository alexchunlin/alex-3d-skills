"""Purchased-part placeholders for the mates_task_v2 brief, each in the local frame its components.json entry
describes. Use them unmodified (don't cut or join them): the scorer finds each by its mesh.

    sys.path.insert(0, "<kit>"); import kit_parts as K
    pan = K.servo("servo_pan")      # an object in its own frame; place it, then register it as BUY_servo_pan
    K.C["servo"]["tapped_holes"]    # the data, from components.json next to this file
"""
import json, math, os
from cadlib import geom as G

HERE = os.path.dirname(os.path.abspath(__file__))
C = json.load(open(os.path.join(HERE, "components.json")))


def servo(name="servo"):
    s = C["servo"]
    c = s["case"]
    L, W, H, cx = c["length_x"], c["width_y"], c["height_z"], c["centre_x"]
    case = G.box(name, cx - L / 2, cx + L / 2, -W / 2, W / 2, -H, 0)
    return G.csg(case, add=[G.cyl(name + "_s", (0, 0), s["spline"]["d"] / 2, -0.01, s["spline"]["protrudes"], 'Z', n=24)])


def horn(name="horn"):
    h = C["horn"]
    hub = G.cyl(name + "_h", (0, 0), h["hub"]["d"] / 2, 0, h["hub"]["h"] + 0.01, 'Z', n=36)
    disc = G.cyl(name, (0, 0), h["disc"]["d"] / 2, h["hub"]["h"], h["hub"]["h"] + h["disc"]["t"], 'Z', n=60)
    bc, n = h["holes"]["bolt_circle_d"] / 2, h["holes"]["n"]
    holes = [G.cyl(name + "_x%d" % k, (bc * math.cos(2 * math.pi * k / n), bc * math.sin(2 * math.pi * k / n)),
                   h["holes"]["d"] / 2, -1, 10, 'Z', n=16) for k in range(n)]
    return G.csg(disc, add=[hub], sub=holes)


def camera(name="camera"):
    c = C["camera"]
    (x0, x1), (y0, y1), t = c["board"]["x"], c["board"]["y"], c["board"]["t"]
    board = G.box(name, x0, x1, y0, y1, 0, t)
    lens = G.cyl(name + "_l", (0, 0), c["lens"]["d"] / 2, t - 0.01, t + c["lens"]["h"], 'Z', n=32)
    hx, hy = c["holes"]["rect"][0] / 2, c["holes"]["rect"][1] / 2
    cy = c["holes"]["centre"][1]
    holes = [G.cyl(name + "_x%d" % i, (sx * hx, cy + sy * hy), c["holes"]["d"] / 2, -1, t + 1, 'Z', n=16)
             for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1)))]
    return G.csg(board, add=[lens], sub=holes)


BUILDERS = {"BUY_servo_pan": servo, "BUY_servo_tilt": servo, "BUY_horn_pan": horn, "BUY_horn_tilt": horn,
            "BUY_cam": camera}
