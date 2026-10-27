"""mates_task reference solution (the mates template, filled in). Headless Blender 5.1+:

    cad build blender/build_assembly.py                 # build, STLs, manifest, .blend
    cad build blender/build_assembly.py -- --render     # + preview renders (960 px)
    CAD_RENDER_FINAL=1 cad build blender/build_assembly.py -- --render --out-renders renders/attempt-N
    cad check blender/model.blend blender/checks.json
    cad build blender/build_assembly.py -- --out /tmp/proj-feeder   # model.blend, manifest.json, stl/ go there instead
                                                                    # (parallel builders must not share one model.blend)
    cad mates blender/manifest.json [REGEX]             # one line per interface: what mates with what, how, screws, fit

Parameters live in params.py; each subsystem is one module in parts/ with a build(P) function that models its parts in
their own frames, names their connectors and declares their mates (cadlib.mates). assemble() then places every part
from P.GROUND, makes the PIV_ joints and cuts the fastener holes. Don't place parts with world coordinates.
Edit the module you are changing; rebuild; check. Keep each module small enough to edit in place.
"""
import importlib, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# `cad build` sets CAD_SKILL to its own checkout; set it yourself if you run Blender directly
SKILL = os.environ.get("CAD_SKILL") or sys.exit("CAD_SKILL is not set: run this through <skill>/scripts/cad build")
sys.path.insert(0, os.path.join(SKILL, "scripts"))
sys.path.insert(0, HERE)
# the kit (kit_parts.py, components.json): MATES_KIT, else this file's kit two levels up
sys.path.insert(0, os.environ.get("MATES_KIT") or os.path.dirname(os.path.dirname(HERE)))
from cadlib import asm, mates, export, render  # noqa: E402
import params as P  # noqa: E402

SUBSYSTEMS = ["deck", "servo_arm", "board"]          # build order; each is parts/<name>.py with build(P)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


t0 = time.time()
asm.new_scene(params={k: getattr(P, k) for k in dir(P) if k.isupper()})
for name in (arg("--only", "") or ",".join(SUBSYSTEMS)).split(","):
    mod = importlib.import_module("parts." + name)
    importlib.reload(mod)
    t = time.time()
    mod.build(P)
    print("SUBSYSTEM %s built in %.1f s" % (name, time.time() - t))
t = time.time()
mates.assemble(P.GROUND)                # places every part through the mates, makes the joints, cuts the screws
print("ASSEMBLED %d parts, %d mates in %.1f s" % (len(asm.MATE_PARTS), len(asm.MATES), time.time() - t))
# cables come after: route them with cadlib.route (reference/route.md) around the placed parts

OUT = arg("--out")
if OUT:
    os.makedirs(OUT, exist_ok=True)
qty = export.export_stls(os.path.join(OUT or ROOT, "stl"))
asm.write_manifest(os.path.join(OUT or HERE, "manifest.json"))
if "--render" in argv:
    out = arg("--out-renders", os.path.join(ROOT, "renders", "preview"))
    render.view_set(out, poses=P.RENDER_POSES)
    render.exploded(out)
export.save_blend(os.path.join(OUT or HERE, "model.blend"))
print("BUILD_DONE %.1f s, stls %s" % (time.time() - t0, qty))
