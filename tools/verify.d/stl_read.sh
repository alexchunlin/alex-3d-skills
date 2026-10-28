# printcheck.read_stl, the one plain-Python STL reader (push-assist PA-A3-T9, PA-A5-T13: bought-part STLs came as
# ASCII; hand-rolled binary readers failed on them, and tools/prior_art had three binary-only copies).
# watch: @core @layer tools/prior_art/overhang_regions.py tools/prior_art/tri_dist.py tools/prior_art/stl_edges_compare.py examples/mm-launcher-v2a7/stl.tar.gz
# watch: tools/verify.d/stl_read_build.py
# Sourced by tools/verify_all.sh (uses $ROOT $CAD $V, calls ok/bad). About 20 s: plain python3 with numpy, then one build
# and one cad check for an unreadable STL in cadcheck's parts check (PR #17 review).
SR="$V/stlread"; mkdir -p "$SR"
tar -C "$SR" -xzf "$ROOT/examples/mm-launcher-v2a7/stl.tar.gz"
python3 -I - "$ROOT" "$SR" <<'PY' > "$SR/asserts.txt" 2>&1
import os, re, struct, subprocess, sys
import numpy as np
root, d = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(root, "skills", "print-cad-blender", "scripts"))
from printcheck import read_stl
def say(ok, msg):
    print(("PASS " if ok else "FAIL ") + "read_stl: " + msg)
src = os.path.join(d, "stl", "jar_valve.stl")
B = read_stl(src)
# the same part as ASCII, laid out as the push-assist bought parts are ("solid Mesh", indented facets, %g numbers),
# and once more in upper case with CRLF line ends and exponents
def ascii_copy(path, T, upper=False):
    rows = ["solid Mesh"]
    for t in T:
        n = np.cross(t[1] - t[0], t[2] - t[0]); n = n / (np.linalg.norm(n) or 1)
        rows += ["  facet normal %g %g %g" % tuple(n), "    outer loop"] + ["      vertex %.9e %.9e %.9e" % tuple(v) for v in t] + ["    endloop", "  endfacet"]
    rows.append("endsolid Mesh")
    s = ("\r\n".join(rows) + "\r\n").upper() if upper else "\n".join(rows) + "\n"
    open(path, "w").write(s)
    return path
A = read_stl(ascii_copy(os.path.join(d, "jar_valve_ascii.stl"), B))
U = read_stl(ascii_copy(os.path.join(d, "jar_valve_upper.stl"), B, upper=True))
say(len(B) > 100 and A.shape == B.shape and np.array_equal(A, B), "an ASCII copy of jar_valve.stl gives the same %d triangles as the binary" % len(B))
say(np.array_equal(U, B), "upper-case ASCII with CRLF line ends gives them too")
raw = open(src, "rb").read()
z = os.path.join(d, "jar_valve_count0.stl")
open(z, "wb").write(b"solid header of a binary file".ljust(80) + b"\0\0\0\0" + raw[84:])
say(np.array_equal(read_stl(z), B), "a binary file whose header says solid and whose count is 0 reads by its size (origin/next: 0 triangles)")
# PR #17 review: a binary cut short exactly on a record boundary read as a partial mesh, and an ASCII file with a
# UTF-8 BOM read as 0 triangles
def raises(path, want):
    try:
        read_stl(path)
        return False
    except ValueError as x:
        return want in str(x)
t = os.path.join(d, "jar_valve_cut.stl")
open(t, "wb").write(raw[:84 + 50 * 100])
say(raises(t, "header count %d" % len(B)), "a binary cut short on a record boundary (100 of %d records) raises, not 100 triangles" % len(B))
open(t, "wb").write(raw + b"\0\0")
say(raises(t, "not a whole binary"), "a binary with 2 bytes after its records raises")
bom = os.path.join(d, "bom.stl")
open(bom, "wb").write(b"\xef\xbb\xbf" + open(os.path.join(d, "jar_valve_ascii.stl"), "rb").read())
say(np.array_equal(read_stl(bom), B), "ASCII with a UTF-8 BOM gives the same triangles")
open(bom, "wb").write(b"solid a\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nendloop\nendfacet\nendsolid a\n")
say(raises(bom, "not a whole"), "ASCII with a vertex missing raises, not 0 triangles")
e = os.path.join(d, "empty.stl")
open(e, "w").write("solid empty\nendsolid empty\n")
say(read_stl(e).shape == (0, 3, 3), "an empty ASCII solid is 0 triangles")
j = os.path.join(d, "junk.stl")
open(j, "wb").write(b"not an stl " * 20)
try:
    read_stl(j)
    say(False, "a file that is neither raises (read it)")
except ValueError as x:
    say("not a whole binary or ASCII STL" in str(x), "a file that is neither raises: %s" % x)
# the prior_art scripts read through it: overhang_regions.py gives the same numbers on the ASCII copy
out = [subprocess.run([sys.executable, "-I", os.path.join(root, "tools", "prior_art", "overhang_regions.py"), p], capture_output=True, text=True).stdout
       for p in (src, os.path.join(d, "jar_valve_ascii.stl"))]
strip = lambda s: re.sub(r'"part": "[^"]*"', "", s)
say(out[0] and strip(out[0]) == strip(out[1]), "prior_art/overhang_regions.py: the ASCII copy gives the binary's numbers (it asserted binary before)")
for f in ("tri_dist.py", "stl_edges_compare.py"):
    s = open(os.path.join(root, "tools", "prior_art", f)).read()
    say("from printcheck import read_stl" in s and "struct.unpack" not in s, "prior_art/%s reads through printcheck.read_stl" % f)
PY
while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$SR/asserts.txt"
# cadcheck's parts check on an STL cut short: a fail naming the file, not a traceback; the other part's STL still read
mkdir -p "$SR/m"
$CAD build "$ROOT/tools/verify.d/stl_read_build.py" -- --out "$SR/m" > "$SR/m/build.log" 2>&1
python3 -I -c "import sys; p=sys.argv[1]; d=open(p,'rb').read(); open(p,'wb').write(d[:84+50*5])" "$SR/m/stl/sr_a.stl"
CAD_LAYER_CHECK=1 $CAD check "$SR/m/m.blend" "" "$SR/m/cadcheck.json" --only parts > "$SR/m/check.log" 2>&1
python3 -I - "$SR/m/cadcheck.json" <<'PY' > "$SR/m/asserts.txt"
import json, sys
try:
    s = json.load(open(sys.argv[1]))["summary"]
except Exception as e:
    print("FAIL read_stl: cad check on a cut-short STL wrote no report (%s)" % e); sys.exit()
a = [x for x in s["fail_list"] if x.startswith("parts: PRT_sr_a:") and "sr_a.stl" in x and "re-export it" in x]
b = [x for x in s["fail_list"] + s["warn_list"] if "PRT_sr_b" in x]
print(("PASS" if len(a) == 1 and not b else "FAIL") + " read_stl: cadcheck parts on an STL cut short: one fail naming the file, "
      "the other part clean: %s %s" % (a or s["fail_list"], b))
PY
while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$SR/m/asserts.txt"
