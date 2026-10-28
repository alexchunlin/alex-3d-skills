# printcheck.read_stl, the one plain-Python STL reader (push-assist PA-A3-T9, PA-A5-T13: bought-part STLs came as
# ASCII; hand-rolled binary readers failed on them, and tools/prior_art had three binary-only copies).
# watch: @layer tools/prior_art/overhang_regions.py tools/prior_art/tri_dist.py tools/prior_art/stl_edges_compare.py examples/mm-launcher-v2a7/stl.tar.gz
# Sourced by tools/verify_all.sh (uses $ROOT $V, calls ok/bad). About 5 s, plain python3 with numpy.
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
e = os.path.join(d, "empty.stl")
open(e, "w").write("solid empty\nendsolid empty\n")
say(read_stl(e).shape == (0, 3, 3), "an empty ASCII solid is 0 triangles")
j = os.path.join(d, "junk.stl")
open(j, "wb").write(b"not an stl " * 20)
try:
    read_stl(j)
    say(False, "a file that is neither raises (read it)")
except ValueError as x:
    say("not a binary or ASCII STL" in str(x), "a file that is neither raises: %s" % x)
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
