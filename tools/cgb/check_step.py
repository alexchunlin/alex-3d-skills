"""Validity gate + 4 renders for a candidate STEP. Usage: check_step.py <step> <out_dir>"""
import sys, subprocess
from pathlib import Path
from cadgenbench.common.viewer import render_step

step, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
gate = subprocess.run([sys.executable, "-I", "/tmp/cgb-data/sanity_check_submission.py", str(step)],
                      capture_output=True, text=True)
for img in render_step(step, ["iso", "front", "top", "right", "bottom"], width=900, height=700):
    (out / f"{img.name}.png").write_bytes(img.data)
    print("render:", out / f"{img.name}.png")
# gate result last, with stderr, so `tail` never hides it
print("\n".join(l for l in (gate.stdout + gate.stderr).splitlines() if l.strip() and "vtk" not in l.lower()))
sys.exit(gate.returncode)
