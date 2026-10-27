"""Pan horn on the pan spline (PIV_pan), the pan bracket on it, the tilt servo screwed to the bracket's upright."""
from cadlib import geom as G, mates as M, asm as A
import kit_parts as K


def build(P):
    S, H = K.C["servo"], K.C["horn"]
    horn = M.from_component(K.horn("horn_pan"), H)
    M.part(horn, "BUY_horn_pan", 'BUY', "buy_metal", mass_g=H["mass_g"], src=H["src"])
    M.mate("BUY_servo_pan:spline", "BUY_horn_pan:hub", "revolute", name="PIV_pan", lo=P.PAN_LO, hi=P.PAN_HI,
           sweep_step=15, fit="press", note="pan horn on the spline")

    # bracket, modelled on its foot's underside at the pan axis: a foot on the horn, an upright behind the tilt servo
    c = S["case"]
    side = S["connectors"]["side"]
    up_z = P.TILT_ABOVE_HORN + side["origin"][0]          # side-face centre: case centre_x along the servo's x (= up)
    face_x = -c["width_y"] / 2                            # the tilt servo's side face, half its width behind the axis
    half = c["height_z"] / 2                              # the case's 40 mm along the tilt axis, centred
    foot = G.box("foot", face_x - P.T, c["width_y"] / 2 + 2, -half, half, 0, P.T)
    upright = G.box("upright", face_x - P.T, face_x, -half, half, P.T - 0.01, up_z + 14 + 6)
    br = G.csg(foot, add=[upright])
    G.bevel(br, P.EB)
    M.connector(br, "hub", (0, 0, 0), (0, 0, -1), pattern=M.circle(14, 4, 0), hole="M2")
    # x along +Z (the default for a +X face) is the servo's +X (its case length) on the mating side: case hangs below
    M.connector(br, "servo", (face_x, 0, up_z), (1, 0, 0), pattern=side["pattern"], hole="M2.5")
    M.part(br, "PRT_pan_bracket", 'PRT', "pla_b", stl="pan_bracket", print_rot=A.R_ID, orient="foot on the bed",
           supports="no", infill=30)
    M.mate("BUY_horn_pan:face_4", "PRT_pan_bracket:hub", "fastened", name="pbr", step="pan bracket onto the pan horn (bench)",
           fastener=dict(style="selftap", head="pan", head_on="a", through_ok=True))

    tsrv = M.from_component(K.servo("servo_tilt"), S)
    M.part(tsrv, "BUY_servo_tilt", 'BUY', "buy", mass_g=S["mass_g"], src=S["src"])
    M.mate("PRT_pan_bracket:servo", "BUY_servo_tilt:side", "fastened", name="tsrv", step="tilt servo into the bracket (bench)",
           fastener=dict(style="tapped", depth=S["tapped_holes"]["side"]["depth"], head="cap", head_on="a"))
