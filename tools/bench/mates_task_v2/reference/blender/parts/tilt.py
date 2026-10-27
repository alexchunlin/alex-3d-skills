"""Tilt horn on the tilt spline (PIV_tilt, + raises the camera), the tilt bracket on it, the camera on the bracket."""
import os
from cadlib import geom as G, mates as M, asm as A
import kit_parts as K


def build(P):
    S, H, C = K.C["servo"], K.C["horn"], K.C["camera"]
    horn = M.from_component(K.horn("horn_tilt"), H)
    M.part(horn, "BUY_horn_tilt", 'BUY', "buy_metal", mass_g=H["mass_g"], src=H["src"])
    # the spline points +Y and the joint turns right-handed about it, so + lowers a +X camera: the brief's -25..60
    # (+ up) is -60..25 here
    lo, hi = (P.TILT_LO, P.TILT_HI) if os.environ.get("MATES_REF_TILT_SENSE_WRONG") else (-P.TILT_HI, -P.TILT_LO)   # selftest
    M.mate("BUY_servo_tilt:spline", "BUY_horn_tilt:hub", "revolute", name="PIV_tilt", lo=lo, hi=hi,
           sweep_step=5, fit="press", note="tilt horn on the spline; + lowers the camera")

    # bracket modelled upright (world orientation) about the horn's disc-top centre: a side plate on the horn, a
    # front plate across to the camera; y 0 is the horn face, y < 0 back toward the pan axis
    reach = H["hub"]["h"] + H["disc"]["t"] + S["spline"]["protrudes"] + S["case"]["height_z"] / 2   # horn face to pan axis
    (bx0, bx1), (by0, by1) = C["board"]["x"], C["board"]["y"]
    fx = P.CAM_AHEAD                                    # front plate's front face = board back
    side_p = G.prism("side", G.hull2d(G.circle((0, 0), 10.0) + [(fx, -by1), (fx, by1)]), 0, P.T, 'Y')
    front = G.box("front", fx - P.T, fx, -reach + bx0 - 1, P.T, by0, by1)
    br = G.csg(side_p, add=[front])
    G.bevel(br, P.EB)
    # hub: z out of the bracket toward the horn (-Y), x = the horn's x, which is the servo's x: up
    M.connector(br, "hub", (0, 0, 0), (0, -1, 0), x=(0, 0, 1), pattern=M.circle(14, 4, 0), hole="M2")
    back = C["connectors"]["back"]
    # the camera's back connector: x is the camera's +X (= world +Y here), its origin 3 below the lens (camera -Y = down)
    M.connector(br, "cam", (fx, -reach, back["origin"][1]), (1, 0, 0), x=(0, 1, 0), pattern=back["pattern"], hole="M2")
    M.part(br, "PRT_tilt_bracket", 'PRT', "pla_b", stl="tilt_bracket", print_rot=A.R_PY_DOWN,
           orient="side plate's outer face on the bed", supports="yes: under the front plate", infill=30)
    M.mate("BUY_horn_tilt:face_4", "PRT_tilt_bracket:hub", "fastened", name="tbr", step="tilt bracket onto the tilt horn (bench)",
           fastener=dict(style="selftap", head="pan", head_on="a", through_ok=True))

    cam = M.from_component(K.camera("cam"), C)
    M.part(cam, "BUY_cam", 'BUY', "pcb", mass_g=C["mass_g"], src=C["src"])
    M.mate("PRT_tilt_bracket:cam", "BUY_cam:back", "fastened", name="cam", step="camera onto the tilt bracket (bench)",
           fastener=dict(style="selftap", head="pan", through_ok=True))
