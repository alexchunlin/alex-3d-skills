"""Servo in its rim, horn on the spline (PIV_arm), arm screwed to the horn from below."""
from cadlib import geom as G, mates as M, asm as A
import kit_parts as K


def build(P):
    srv = M.from_component(K.servo(), K.C["servo"])
    M.part(srv, "BUY_servo", 'BUY', "buy", mass_g=K.C["servo"]["mass_g"], src=K.C["servo"]["src"])
    horn = M.from_component(K.horn(), K.C["horn"])
    M.part(horn, "BUY_horn", 'BUY', "buy_metal", mass_g=K.C["horn"]["mass_g"], src=K.C["horn"]["src"])
    # arm modelled about its pivot, underside at z 0, pointing +X
    arm = G.prism("arm", G.hull_circles([((0, 0), P.ARM_HUB_R), ((P.ARM_LEN, 0), P.ARM_TIP_R)]), 0, P.ARM_T, 'Z')
    G.bevel(arm, P.EB)
    M.connector(arm, "hub", (0, 0, 0), (0, 0, -1), pattern=M.circle(14, 4, 0), hole="M2")
    M.part(arm, "PRT_arm", 'PRT', "pla_b", stl="arm", print_rot=A.R_ID, orient="flat", supports="no", infill=30)

    M.mate("PRT_deck:servo", "BUY_servo:bottom", "rigid", name="servo", fit="slip", note="case in the deck rim")
    M.mate("BUY_servo:spline", "BUY_horn:hub", "revolute", name="PIV_arm", lo=P.ARM_LO, hi=P.ARM_HI, sweep_step=10,
           fit="press", note="horn on the spline")
    # screws from under the horn disc up into the arm: put on at the bench, before the horn goes on the spline
    M.mate("BUY_horn:face_4", "PRT_arm:hub", "fastened", name="arm", step="arm onto horn (bench)",
           fastener=dict(style="selftap", head="pan", head_on="a", through_ok=True))
