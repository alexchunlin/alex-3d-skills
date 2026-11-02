"""Render docs/img/sweep.gif: the v2 launcher swept through its full pan, tilt and feeder ranges, with a joint readout.

    python3 docs/img/make_sweep.py MODEL.blend [OUT.gif]

MODEL.blend: the v2a7 model as verify_all unpacks it (/tmp/alex3d-verify/run-<pid>/v2a7/model.blend), or
gunzip -c examples/mm-launcher-v2a7/mm_launcher_v2a7.blend.gz > /tmp/v2a7.blend. Needs Pillow and Blender (via cad q).
Fonts come from the alex-style guide (AX_FONTS, default ~/code-stuff/alex-style-guide/fonts).
"""
import math, os, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
CAD = os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts", "cad")
FONTS = os.environ.get("AX_FONTS", os.path.expanduser("~/code-stuff/alex-style-guide/fonts"))
N, MS = 48, 80                       # frames, ms per frame (GIF stores 1/100 s): a 3.8 s loop
CAM, TARGET, LENS = "760,-820,560", "0,0,165", "50"
W, H, MH = 560, 406, 362             # canvas and model height, px: the README shows it at native size


def poses():
    for i in range(N):
        t = i / N
        yield i, {"PIV_pan": 90 * math.sin(2 * math.pi * t), "PIV_tilt": 22.5 * (1 - math.cos(2 * math.pi * t)),
                  "PIV_feeder": 60 * math.sin(4 * math.pi * t), "PIV_flywheel": (t * 1080) % 360}


def render(blend, tmp, i, p):
    out = os.path.join(tmp, "f%02d.png" % i)
    pose = ",".join("%s=%.2f" % kv for kv in p.items())
    r = subprocess.run([CAD, "q", blend, "render", out, CAM, TARGET, "--lens", LENS, "--pose", pose],
                       capture_output=True, text=True)
    if r.returncode or not os.path.exists(out):
        sys.exit("render failed at %s:\n%s" % (pose, r.stdout[-2000:] + r.stderr[-2000:]))
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    blend = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "sweep.gif")
    ps = list(poses())
    with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(4) as ex:
        files = list(ex.map(lambda ip: render(blend, tmp, *ip), ps))
        frames = [Image.open(f).convert("RGB") for f in files]
    box = None                                     # one crop for every frame, so the base stays put
    for f in frames:
        b = ImageChops.difference(f, Image.new("RGB", f.size, "white")).convert("L").point(lambda v: 255 if v > 12 else 0).getbbox()
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    box = (box[0] - 16, box[1] - 16, box[2] + 16, box[3] + 16)
    font = ImageFont.truetype(os.path.join(FONTS, "RobotoMono-500.ttf"), 15)
    gif = []
    for f, (_, p) in zip(frames, ps):
        m = f.crop(box)
        m = m.resize((int(m.width * MH / m.height), MH), Image.LANCZOS)
        r, g, b = m.split()                            # the render's background is noisy near-white: make it white
        m.paste((255, 255, 255), mask=ImageChops.darker(ImageChops.darker(r, g), b).point(lambda v: 255 if v >= 250 else 0))
        c = Image.new("RGB", (W, H), "white")
        c.paste(m, ((W - m.width) // 2, 4))
        d = ImageDraw.Draw(c)
        txt = "pan %+6.1f°   tilt %4.1f°   feeder %+5.1f°" % tuple(round(p[k], 1) + 0.0 for k in ("PIV_pan", "PIV_tilt", "PIV_feeder"))
        x0 = (W - d.textlength(txt, font=font)) // 2
        d.rectangle((x0 - 16, H - 30, x0 - 8, H - 22), fill=(196, 83, 42))    # light-mode accent
        d.text((x0, H - 35), txt, font=font, fill=(60, 60, 58))
        q = c.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        pal = q.getpalette()[:64 * 3]                 # the background's entry comes out off-white: snap it to white
        k = max(range(len(pal) // 3), key=lambda j: sum(pal[3 * j:3 * j + 3]))
        pal[3 * k:3 * k + 3] = [255, 255, 255]
        q.putpalette(pal)
        gif.append(q)
    gif[0].save(out, save_all=True, append_images=gif[1:], duration=MS, loop=0, optimize=True, disposal=1)
    print(out, os.path.getsize(out) // 1024, "KB")


if __name__ == "__main__":
    main()
