"""glb_export.sh's reader: a GLB checked with the standard library only (the JSON chunk, the animation accessors, node
TRS), against glb_export_build.py's expected world matrices. Prints PASS/FAIL lines.

    python3 -I glb_export_check.py MODEL.glb EXPECT.json LABEL [--require-joint PIV_x] [--extent-m X,Y,Z] [--expect-fail]
    python3 -I glb_export_check.py --tamper IN.glb OUT.glb root|order      # negative-control copies

Checks: one root node with scale 0.001 and the 4-element Z-up -> Y-up rotation; nodes = PRT/BUY/FST/CAB + PIV, names and
parents as in the blend; with --extent-m, the mesh boxes through the full chain measure X, Y (up), Z metres per axis;
each joint clip runs lo -> hi -> lo; at every key of every joint clip each PRT_/BUY_ world matrix through the full
chain, mapped back to Z-up mm by a fixed inverse of the expected root, equals cadlib.joints.world_at within 0.01 mm and
0.01 deg; in the assembly clip every object assembly_order names appears exactly once, at its step x step_s, and all
end at home (objects in no step are listed). --expect-fail inverts the FK line (the sign-flip negative control).
"""
import fnmatch, json, math, struct, sys

TOL_MM, TOL_DEG = 0.01, 0.01


def read_glb(path):
    b = open(path, "rb").read()
    assert b[:4] == b"glTF", "not a GLB"
    off, js, bin_ = 12, None, b""
    while off + 8 <= len(b):
        ln, kind = struct.unpack_from("<I4s", b, off)
        if kind == b"JSON":
            js = json.loads(b[off + 8:off + 8 + ln])
        elif kind == b"BIN\0":
            bin_ = b[off + 8:off + 8 + ln]
        off += 8 + ln
    return js, bin_


def accessor(js, bin_, i):
    a = js["accessors"][i]
    assert a["componentType"] == 5126, "float accessors only"
    n = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[a["type"]]
    bv = js["bufferViews"][a["bufferView"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 4 * n)
    return [struct.unpack_from("<%df" % n, bin_, off + k * stride) for k in range(a["count"])]


def mat(t, r, s):
    x, y, z, w = r
    R = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[R[i][0] * s[0], R[i][1] * s[1], R[i][2] * s[2], t[i]] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def mul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def trs(nd):
    if "matrix" in nd:
        raise SystemExit("node %s has a matrix, not TRS" % nd.get("name"))
    return [list(nd.get("translation", [0, 0, 0])), list(nd.get("rotation", [0, 0, 0, 1])), list(nd.get("scale", [1, 1, 1]))]


def compare(G, E):
    """(mm, deg) between a GLB world matrix and an expected flat 4x4 (row-major)."""
    Em = [E[4 * i:4 * i + 4] for i in range(4)]
    dt = math.sqrt(sum((G[i][3] - Em[i][3]) ** 2 for i in range(3)))
    def unit(M):
        cols = [[M[r][c] for r in range(3)] for c in range(3)]
        ns = [math.sqrt(sum(v * v for v in col)) for col in cols]
        return [[cols[c][r] / ns[c] for c in range(3)] for r in range(3)], ns
    Rg, sg = unit(G)
    Re, se = unit(Em)
    tr = sum(Rg[k][i] * Re[k][i] for i in range(3) for k in range(3))   # trace(Rg^T Re)
    ang = math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1) / 2))))
    return dt, ang, max(abs(a - b) for a, b in zip(sg, se))


# the root write_glb must write, inverted: glTF Y-up metres back to Blender Z-up mm. Fixed here, not read from the file,
# so a missing or wrong root fails the FK line as well as the root line.
TO_MM_ZUP = [[1000.0, 0, 0, 0], [0, 0, -1000.0, 0], [0, 1000.0, 0, 0], [0, 0, 0, 1.0]]


def main():
    glb, exp_path, label = sys.argv[1:4]
    req = sys.argv[sys.argv.index("--require-joint") + 1] if "--require-joint" in sys.argv else None
    neg = "--expect-fail" in sys.argv
    js, bin_ = read_glb(glb)
    X = json.load(open(exp_path))
    out = []

    def say(ok, msg):
        out.append(("PASS " if ok else "FAIL ") + label + ": " + msg)

    nodes = js["nodes"]
    roots = js["scenes"][js.get("scene", 0)]["nodes"]
    parent = {c: i for i, nd in enumerate(nodes) for c in nd.get("children", [])}
    base = [trs(nd) for nd in nodes]
    by_name = {nd.get("name"): i for i, nd in enumerate(nodes)}
    clips = {an["name"]: an for an in js.get("animations", [])}

    def world(i, loc, cache):
        """Full node chain, root included."""
        if i not in cache:
            t, r, s = loc.get(i, base[i])
            M = mat(t, r, s)
            cache[i] = M if parent.get(i) is None else mul(world(parent[i], loc, cache), M)
        return cache[i]

    if not neg:
        rt = nodes[roots[0]] if len(roots) == 1 else {}
        h = math.sqrt(0.5)
        sc, rot = rt.get("scale", []), rt.get("rotation", [])
        say(len(roots) == 1 and len(sc) == 3 and all(abs(v - 0.001) < 1e-12 for v in sc) and len(rot) == 4
            and all(abs(a - b) < 1e-6 for a, b in zip(rot, [-h, 0, 0, h])) and "translation" not in rt and "matrix" not in rt,
            "one root node, scale %s, rotation %s (Z-up mm to Y-up m)" % (sc or None, [round(v, 4) for v in rot] or None))
        names = {nd.get("name"): i for i, nd in enumerate(nodes) if i not in roots}
        objs = X["objects"]
        say(len(names) == len(nodes) - 1 == len(objs) and set(names) == set(objs),
            "%d nodes under the root = %d PRT/BUY/FST/CAB + %d PIV, names kept%s" % (
                len(nodes) - 1, sum(not n.startswith("PIV_") for n in objs), sum(n.startswith("PIV_") for n in objs),
                "" if set(names) == set(objs) else " (missing %s, extra %s)" % (sorted(set(objs) - set(names))[:5], sorted(set(names) - set(objs))[:5])))
        if "--extent-m" in sys.argv:   # what a viewer reads: mesh boxes (accessor min/max) through the full node chain
            want = [float(v) for v in sys.argv[sys.argv.index("--extent-m") + 1].split(",")]
            cache, pts = {}, []
            for i, nd in enumerate(nodes):
                for pr in (js["meshes"][nd["mesh"]]["primitives"] if "mesh" in nd else []):
                    a = js["accessors"][pr["attributes"]["POSITION"]]
                    M = world(i, {}, cache)
                    for c in range(8):
                        p = [a["max"][k] if c >> k & 1 else a["min"][k] for k in range(3)]
                        pts.append([sum(M[r][k] * p[k] for k in range(3)) + M[r][3] for r in range(3)])
            dims = [max(p[k] for p in pts) - min(p[k] for p in pts) for k in range(3)]
            say(all(abs(a - b) < 0.0005 for a, b in zip(dims, want)),
                "a viewer reads the model as %s m (x, y up, z), expected %s within 0.5 mm per axis" % (
                    " x ".join("%.4f" % d for d in dims), " x ".join("%g" % w for w in want)))
        bad = [n for n, i in names.items() if n in objs and (nodes[parent[i]]["name"] if parent.get(i) not in (None, roots[0]) else None) != objs[n]]
        say(not bad, "hierarchy kept: every node's parent is its blend parent%s" % ("" if not bad else " (not: %s)" % bad[:5]))

    worst = (0.0, 0.0, "", "", 0)
    n_keys = n_mats = 0
    lohi_bad = []
    for cname, rows in X["expect"].items():
        an = clips[cname]
        sj = X["joints"][an["extras"]["joint"]]
        vals = an["extras"]["values"]
        lo, hi = (sj["home"], sj["home"] + 360.0) if sj["continuous"] else (sj["lo"], sj["hi"])
        if not (abs(vals[0] - lo) < 1e-9 and abs(vals[-1] - lo) < 1e-9 and abs(max(vals) - hi) < 1e-9 and len(rows) == len(vals)):
            lohi_bad.append(cname)
        chans = []
        for ch in an["channels"]:
            sm = an["samplers"][ch["sampler"]]
            chans.append((ch["target"]["node"], ch["target"]["path"], accessor(js, bin_, sm["input"]), accessor(js, bin_, sm["output"])))
        for k, row in enumerate(rows):
            loc = {}
            for node, path, tin, tout in chans:
                assert len(tin) == len(rows), "%s: a channel keyed off the clip's keys" % cname
                cur = loc.setdefault(node, [list(x) for x in base[node]])
                cur[{"translation": 0, "rotation": 1, "scale": 2}[path]] = list(tout[k])
            cache = {}
            for n, E in row.items():
                dt, ang, ds = compare(mul(TO_MM_ZUP, world(by_name[n], loc, cache)), E)
                n_mats += 1
                if max(dt / TOL_MM, ang / TOL_DEG) > max(worst[0] / TOL_MM, worst[1] / TOL_DEG):
                    worst = (dt, ang, cname, n, k)
            n_keys += 1
    fk_ok = n_mats > 0 and worst[0] <= TOL_MM and worst[1] <= TOL_DEG
    msg = ("%d joint clips, %d keys, %d PRT/BUY world matrices (root included, mapped back to Z-up mm) vs joints.world_at: "
           "worst %.4f mm, %.4f deg (%s key %d, %s); tolerance %g mm / %g deg" % (
               len(X["expect"]), n_keys, n_mats, worst[0], worst[1], worst[2], worst[4], worst[3], TOL_MM, TOL_DEG))
    if neg:
        say(not fk_ok, "negative control (a joint's sign flipped at export) is caught: " + msg)
        print("\n".join(out))
        return
    say(fk_ok, msg)
    say(not lohi_bad and X["expect"], "every joint clip runs lo -> hi -> lo (continuous: 360 and back)%s" % (
        "" if not lohi_bad else ": not %s" % lohi_bad))
    if req:
        cp = X["joints"][req]
        drv = [c for c, an in clips.items() if req in (an.get("extras") or {}).get("moves", [])]
        say(bool(drv) and cp["coupled_to"] in drv and req not in clips,
            "%s (coupled to %s, ratio %.4f) moves in its driver's clip %s, no clip of its own" % (req, cp["coupled_to"], cp["ratio"] or 0, drv))
    steps = X["assembly_order"]
    if steps:
        an = clips.get("assembly")
        if an is None:
            say(False, "assembly clip: missing")
        else:
            step_s = an["extras"]["step_s"]
            want = {}
            for n in X["objects"]:   # first step whose glob matches, as cadcheck's assembly_present
                if not n.startswith("PIV_"):
                    i = next((i for i, globs in enumerate(steps) if any(fnmatch.fnmatchcase(n, g) for g in globs)), None)
                    if i is not None:
                        want[n] = i
            seen, appear, home_bad, tend = {}, {}, 0, 0.0
            for ch in an["channels"]:
                sm = an["samplers"][ch["sampler"]]
                tin, tout = accessor(js, bin_, sm["input"]), accessor(js, bin_, sm["output"])
                node, path = ch["target"]["node"], ch["target"]["path"]
                n = nodes[node]["name"]
                tend = tin[-1][0]
                if max(abs(x - y) for x, y in zip(tout[-1], base[node][{"translation": 0, "rotation": 1, "scale": 2}[path]])) > 1e-4:
                    home_bad += 1
                if path == "scale":
                    seen[n] = seen.get(n, 0) + 1
                    appear[n] = next((t[0] for t, v in zip(tin, tout) if max(v) > 0), None)
            wrong_t = sorted(n for n in want if appear.get(n) is None or abs(appear[n] - want[n] * step_s) > 1e-6)
            not_once = sorted(n for n in set(want) | set(seen) if seen.get(n) != 1 or n not in want)
            unordered = sorted(n for n in X["objects"] if not n.startswith("PIV_") and n not in want)
            say(not wrong_t and not not_once and home_bad == 0 and abs(tend - len(steps) * step_s) < 1e-6,
                "assembly clip: %d steps over %.1f s; each of the %d objects in assembly_order appears once, at its step x %g s%s; "
                "all at home at the end (%d channels off); flights %s" % (
                    len(steps), tend, len(want), step_s,
                    "" if not wrong_t else " (NOT: %s)" % ", ".join("%s at %s, step %d" % (n, appear.get(n), want[n]) for n in wrong_t[:4]),
                    home_bad, an["extras"]["from"]) + ("" if not not_once else "; not exactly once: %s" % not_once[:6]))
            out.append("NOTE %s: %d objects in no assembly_order step, there throughout: %s" % (
                label, len(unordered), ", ".join(unordered[:12]) + (" ..." if len(unordered) > 12 else "") if unordered else "none"))
    print("\n".join(out))


def tamper(src, dst, what):
    """Negative controls for the root and order lines: a copy of src with the root's rotation dropped ("root") or one
    object's scale channel shifted a step late ("order")."""
    js, bin_ = read_glb(src)
    if what == "root":
        js["nodes"][js["scenes"][js.get("scene", 0)]["nodes"][0]].pop("rotation")
    else:
        an = next(a for a in js["animations"] if a["name"] == "assembly")
        sm = next(an["samplers"][c["sampler"]] for c in an["channels"] if c["target"]["path"] == "scale")
        tin, tout = accessor(js, bin_, sm["input"]), accessor(js, bin_, sm["output"])
        late = [tout[0]] + list(tout[:-1]) if max(tout[0]) == 0 else [(0.0, 0.0, 0.0)] + list(tout[1:])
        a = js["accessors"][sm["output"]]
        bv = js["bufferViews"][a["bufferView"]]
        flat = [x for v in late for x in v]
        bin_ = bin_[:bv["byteOffset"]] + struct.pack("<%df" % len(flat), *flat) + bin_[bv["byteOffset"] + 4 * len(flat):]
    j = json.dumps(js).encode()
    j += b" " * (-len(j) % 4)
    with open(dst, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(j) + 8 + len(bin_)) + struct.pack("<I4s", len(j), b"JSON") + j
                + struct.pack("<I4s", len(bin_), b"BIN\0") + bin_)


if __name__ == "__main__":
    if sys.argv[1] == "--tamper":
        tamper(*sys.argv[2:5])
    else:
        main()
