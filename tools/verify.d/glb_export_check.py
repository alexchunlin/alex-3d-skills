"""glb_export.sh's reader: a GLB checked with the standard library only (the JSON chunk, the animation accessors, node
TRS), against glb_export_build.py's expected world matrices. Prints PASS/FAIL lines.

    python3 -I glb_export_check.py MODEL.glb EXPECT.json LABEL [--require-joint PIV_x] [--expect-fail]

Checks: the root node turns Z-up mm into Y-up metres (scale 0.001); nodes = PRT/BUY/FST/CAB + PIV, names and parents
as in the blend; each joint clip runs lo -> hi -> lo; at every key of every joint clip each PRT_/BUY_ world matrix
under the root equals cadlib.joints.world_at within 0.01 mm and 0.01 deg; the assembly clip ends at home with every
later step's objects hidden at t = 0. --expect-fail inverts the FK line (the negative control).
"""
import json, math, struct, sys

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
    if not neg:
        rt = nodes[roots[0]] if len(roots) == 1 else {}
        h = math.sqrt(0.5)
        say(len(roots) == 1 and all(abs(v - 0.001) < 1e-12 for v in rt.get("scale", [])) and len(rt.get("scale", [])) == 3
            and all(abs(a - b) < 1e-6 for a, b in zip(rt.get("rotation", []), [-h, 0, 0, h])),
            "one root node, scale %s, rotation %s (Z-up mm to Y-up m)" % (rt.get("scale"), [round(v, 4) for v in rt.get("rotation", [])]))
        names = {nd.get("name"): i for i, nd in enumerate(nodes) if i not in roots}
        objs = X["objects"]
        say(len(names) == len(nodes) - 1 == len(objs) and set(names) == set(objs),
            "%d nodes under the root = %d PRT/BUY/FST/CAB + %d PIV, names kept%s" % (
                len(nodes) - 1, sum(not n.startswith("PIV_") for n in objs), sum(n.startswith("PIV_") for n in objs),
                "" if set(names) == set(objs) else " (missing %s, extra %s)" % (sorted(set(objs) - set(names))[:5], sorted(set(names) - set(objs))[:5])))
        if "--extent-m" in sys.argv:   # what a viewer reads: mesh boxes (accessor min/max) through the full node chain
            want = sorted(float(v) for v in sys.argv[sys.argv.index("--extent-m") + 1].split(","))
            full = {}

            def fworld(i):
                if i not in full:
                    full[i] = mat(*trs(nodes[i])) if parent.get(i) is None else mul(fworld(parent[i]), mat(*trs(nodes[i])))
                return full[i]
            pts = []
            for i, nd in enumerate(nodes):
                for pr in (js["meshes"][nd["mesh"]]["primitives"] if "mesh" in nd else []):
                    a = js["accessors"][pr["attributes"]["POSITION"]]
                    M = fworld(i)
                    for c in range(8):
                        p = [a["max"][k] if c >> k & 1 else a["min"][k] for k in range(3)]
                        pts.append([sum(M[r][k] * p[k] for k in range(3)) + M[r][3] for r in range(3)])
            dims = [max(p[k] for p in pts) - min(p[k] for p in pts) for k in range(3)]
            say(all(abs(a - b) < 0.0005 for a, b in zip(sorted(dims), want)),
                "a viewer reads the model as %s m (x, y-up, z), expected %s within 0.5 mm" % (
                    " x ".join("%.4f" % d for d in dims), " x ".join("%g" % w for w in want)))
        bad = [n for n, i in names.items() if n in objs and (nodes[parent[i]]["name"] if parent.get(i) not in (None, roots[0]) else None) != objs[n]]
        say(not bad, "hierarchy kept: every node's parent is its blend parent%s" % ("" if not bad else " (not: %s)" % bad[:5]))

    base = [trs(nd) for nd in nodes]
    by_name = {nd.get("name"): i for i, nd in enumerate(nodes)}
    clips = {an["name"]: an for an in js.get("animations", [])}

    def world(i, loc, cache):
        if i in cache:
            return cache[i]
        t, r, s = loc.get(i, base[i])
        M = mat(t, r, s)
        p = parent.get(i)
        if p is not None and p not in roots:   # stop under the root: the matrices compare in mm, Z-up
            M = mul(world(p, loc, cache), M)
        cache[i] = M
        return M

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
                dt, ang, ds = compare(world(by_name[n], loc, cache), E)
                n_mats += 1
                if max(dt / TOL_MM, ang / TOL_DEG) > max(worst[0] / TOL_MM, worst[1] / TOL_DEG):
                    worst = (dt, ang, cname, n, k)
            n_keys += 1
    fk_ok = n_mats > 0 and worst[0] <= TOL_MM and worst[1] <= TOL_DEG
    msg = "%d joint clips, %d keys, %d PRT/BUY world matrices vs joints.world_at: worst %.4f mm, %.4f deg (%s key %d, %s); tolerance %g mm / %g deg" % (
        len(X["expect"]), n_keys, n_mats, worst[0], worst[1], worst[2], worst[4], worst[3], TOL_MM, TOL_DEG)
    if neg:
        say(not fk_ok, "negative control (a joint's sign flipped at export) is caught: " + msg)
    else:
        say(fk_ok, msg)
        say(not lohi_bad and X["expect"], "every joint clip runs lo -> hi -> lo (continuous: 360 and back)%s" % (
            "" if not lohi_bad else ": not %s" % lohi_bad))
        if req:
            cp = X["joints"][req]
            drv = [c for c, an in clips.items() if req in (an.get("extras") or {}).get("moves", [])]
            say(bool(drv) and cp["coupled_to"] in drv and req not in clips,
                "%s (coupled to %s, ratio %.4f) moves in its driver's clip %s, no clip of its own" % (req, cp["coupled_to"], cp["ratio"] or 0, drv))
        an = clips.get("assembly")
        if X["assembly_steps"]:
            ok, why = an is not None, "no assembly clip"
            if an:
                tin = None
                hidden = home_bad = 0
                for ch in an["channels"]:
                    sm = an["samplers"][ch["sampler"]]
                    tin, tout = accessor(js, bin_, sm["input"]), accessor(js, bin_, sm["output"])
                    b = base[ch["target"]["node"]][{"translation": 0, "rotation": 1, "scale": 2}[ch["target"]["path"]]]
                    if max(abs(x - y) for x, y in zip(tout[-1], b)) > 1e-4:
                        home_bad += 1
                    if ch["target"]["path"] == "scale" and max(tout[0]) == 0:
                        hidden += 1
                nodes_anim = len({ch["target"]["node"] for ch in an["channels"]})
                ok = home_bad == 0 and hidden > 0 and abs(tin[-1][0] - X["assembly_steps"] * an["extras"]["step_s"]) < 1e-6
                why = "%d steps over %.1f s, %d objects fly in (%s), %d hidden at t = 0, %d channels off home at the end" % (
                    X["assembly_steps"], tin[-1][0], nodes_anim, an["extras"]["from"], hidden, home_bad)
            say(ok, "assembly clip: " + why)
    print("\n".join(out))


if __name__ == "__main__":
    main()
