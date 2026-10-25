#!/bin/sh
# cad slice end to end with stand-in slicers (no real slicer runs): a crashing one is marked unusable on its one smoke
# test, without a crash report, and is not run again; the working one is used inside the sandbox (no write outside its
# work dir, no network, HOME redirected) and its time, filament, support heights and warnings are parsed.
#   sh tools/test_cad_slice.sh [OUTDIR]        prints CAD_SLICE_TEST ok | FAIL <why>
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
O="${1:-/tmp/alex3d-cad-slice-test}"; rm -rf "$O"; mkdir -p "$O/stl" "$O/bin"
xcrun clang -O0 -o "$O/bin/fake_slicer" "$ROOT/tools/fake_slicer.c" 2>/dev/null || { echo "CAD_SLICE_TEST skip: no clang"; exit 0; }
cp "$O/bin/fake_slicer" "$O/bin/crashy_slicer"
python3 -I -c "
import struct, sys
v=[(x,y,z) for z in (0,10) for y in (0,10) for x in (0,10)]
F=[(0,2,3),(0,3,1),(4,5,7),(4,7,6),(0,1,5),(0,5,4),(2,6,7),(2,7,3),(0,4,6),(0,6,2),(1,3,7),(1,7,5)]
f=open(sys.argv[1],'wb'); f.write(b'cube'.ljust(80,b' ')+struct.pack('<I',len(F)))
[f.write(struct.pack('<3f',0,0,0)+b''.join(struct.pack('<3f',*v[i]) for i in t)+b'\0\0') for t in F]" "$O/stl/cube.stl"
# a local listener the fake tries to reach (loopback only: the test never touches a real network)
python3 -I -c "
import socket, sys
s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(5); open(sys.argv[1],'w').write('%s %d' % (sys.argv[2], s.getsockname()[1]))
s.settimeout(60)
try: s.accept()
except Exception: pass" "$O/bin/fake.cfg" "$O/outside.txt" &
LP=$!
sleep 1
export CAD_SLICE_CACHE="$O/cache.json"
export CAD_SLICE_SLICERS="[{\"name\":\"crashy\",\"kind\":\"test\",\"exe\":\"$O/bin/crashy_slicer\",\"version\":\"1\"},{\"name\":\"fake\",\"kind\":\"test\",\"exe\":\"$O/bin/fake_slicer\",\"version\":\"1\"}]"
T0=$(date +%s)
python3 "$ROOT/skills/print-cad-blender/scripts/cadslice.py" "$O/stl" --out "$O/res" > "$O/run1.txt" 2>&1; rc1=$?
python3 "$ROOT/skills/print-cad-blender/scripts/cadslice.py" "$O/stl" --out "$O/res2" > "$O/run2.txt" 2>&1
python3 "$ROOT/skills/print-cad-blender/scripts/cadslice.py" --detect > "$O/detect.txt" 2>&1
kill $LP 2>/dev/null; wait $LP 2>/dev/null
sleep 8
python3 -I - "$O" "$rc1" "$T0" "$ROOT" <<'PY'
import json, os, sys
o, rc1, t0, root = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
sys.path.insert(0, os.path.join(root, "skills/print-cad-blender/scripts"))
import guarded_run as G
bad = []
c = json.load(open(os.path.join(o, "cache.json")))
cr = c.get("crashy@1", {})
if cr.get("status") != "unusable" or "crashed" not in cr.get("why", ""): bad.append("crashy not marked unusable: %s" % cr)
if c.get("fake@1", {}).get("status") != "usable": bad.append("fake not usable: %s" % c.get("fake@1"))
r = json.load(open(os.path.join(o, "res", "slice.json")))
p = r["parts"][0]
a, b = p["no_supports"], p["with_supports"]
if r["slicer"]["name"] != "fake" or rc1 != 0: bad.append("slicer %s rc %d" % (r["slicer"]["name"], rc1))
if a.get("time_s") != 750.0 or a.get("filament_g") != 3.7 or a.get("support_layers"): bad.append("no-support pass parsed %s" % a)
if (b or {}).get("support_layers") != [0.6, 0.8, 1.0] or not p["slicer_adds_support"]: bad.append("support pass parsed %s" % (b or {}).get("support_layers"))
w = " ".join(a.get("warnings", []))
if "floating part" not in w: bad.append("warning not parsed: %s" % w)
if "write_outside=denied" not in w or "net=denied" not in w or "/cad-slice-" not in w: bad.append("sandbox: %s" % w)
if os.path.exists(os.path.join(o, "outside.txt")): bad.append("the slicer wrote outside its work dir")
if json.load(open(os.path.join(o, "cache.json")))["crashy@1"]["date"] != cr.get("date"): bad.append("crashy re-run")
if "smoke test" in open(os.path.join(o, "run2.txt")).read().split("crashy")[1][:60] and "unusable" not in open(os.path.join(o, "run2.txt")).read(): bad.append("run 2 re-probed crashy")
if "unusable" not in open(os.path.join(o, "detect.txt")).read(): bad.append("--detect does not show the verdict")
leak = G.crash_reports_since(t0, ["crashy_slicer", "fake_slicer", "Python", "python"])
if leak: bad.append("crash reports written: %s" % leak)
print("CAD_SLICE_TEST", "ok" if not bad else "FAIL", "; ".join(bad))
PY
