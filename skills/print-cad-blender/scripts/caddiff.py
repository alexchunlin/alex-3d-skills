"""caddiff: what changed between two cadcheck runs of one design. Plain python3, no Blender.

    cad diff OLD.json NEW.json [--manifest OLD_M NEW_M] [--max N]
    cad diff NEW.json            # against NEW's .prev.json: the report `cad check` kept when it overwrote it

  findings      new / fixed / worse / better ("changed" when the direction of a measured number is not known), and
                the untriaged ones still there (what a reviewer marks NOT FIXED)
  requirements  report["config"]: rows removed, limits loosened, allows / accepts / fits added ("requirements cannot
                silently disappear"), drop tests removed, warns newly accepted
  manifest      parts added / removed, fastener lengths, joint ranges, params (manifest.json next to each report,
                or --manifest OLD NEW)

A finding's key is (check, objects, kind), cadcfg's accepted_warns matching: objects from the finding's own fields
(object, a/b, test) or the object names in its text, kind from cadcfg.kind_of (the fixed text of the check's
messages). Messages carry measured numbers, so text matching would call every changed value fixed + new. Same key,
other number or fail<->warn: worse / better. Checks that ran in one run only (--only) are not compared.

`cad check` prints the short form of this (counts, then the new / worse / fixed findings and loosened requirements,
about 20 lines) when it overwrites a report, and keeps the old one as <out>.prev.json; --no-diff turns that off.
Exit status: 1 when something got worse (a new untriaged finding, worse, a requirement removed or loosened), else 0;
2 on a bad input. Why: the reviewer worked out FIXED / NOT FIXED by hand, and a params change that added fails
elsewhere was only seen by reading the whole report again (V2A5-T2: a shared params change brought 14 drop fails).
"""
import difflib, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cadcfg as CC   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SUBJ = ("object", "part", "a", "b", "test")
ALWAYS = {"config", "build"}          # pseudo-checks every run reports
# a list section whose added row lets more through (an allow skips a pair, an accept hides a warn, a fit lowers a
# clearance floor); removing one of these tightens. Any other section's removed row is a requirement gone.
LOOSEN_ON_ADD = {"allow", "accepted_warns", "fits", "cable_junctions_ok", "exposure.cables_ok", "exposure.nuts_ok",
                 "fasteners.stock_ok", "unordered_ok"}
HIGHER_LOOSER = {"overhang_deg", "min_escape", "sweep_tol", "vol_tol", "dist_tol"}
MANIFEST_PART_KEYS = ("part", "spec", "length", "host", "joint", "step", "stl", "supports", "mass_g", "lead_len")
NUM = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?")
_TMPL = None


def templates():
    global _TMPL
    if _TMPL is None:
        try:
            _TMPL = CC.templates(os.path.join(HERE, "cadcheck.py"))
        except (OSError, SyntaxError):
            _TMPL = {}
    return _TMPL


# ------------------------------------------------------------------ findings

def findings(rep):
    """[{check, status, msg, line, accepted, data}] for every fail and warn of a report."""
    acc = (rep.get("summary") or {}).get("accepted_warns") or {}
    out = []
    for chk, sec in (rep.get("checks") or {}).items():
        for f in (sec or {}).get("findings") or []:
            if f.get("status") not in ("fail", "warn"):
                continue
            line = "%s: %s" % (chk, f.get("msg", ""))
            out.append({"check": chk, "status": f["status"], "msg": f.get("msg", ""), "line": line,
                        "accepted": f["status"] == "warn" and line in acc, "data": f})
    return out


def ran(rep):
    """The checks that ran: those with a runtime (cadcheck sets it per check run). None: no runtimes, assume all."""
    secs = rep.get("checks") or {}
    r = {c for c, s in secs.items() if isinstance(s, dict) and "runtime_s" in s}
    return (r | ALWAYS | ({"clearance"} if "interference" in r else set())) if r else None


def subject(f):
    d = f["data"]
    objs = [d[k] for k in SUBJ if isinstance(d.get(k), str) and d[k]]
    if not objs and isinstance(d.get("objects"), list):
        objs = [o for o in d["objects"] if isinstance(o, str)]
    return tuple(sorted(set(objs or CC.OBJ.findall(f["msg"]))))


def key(f):
    return f["check"], subject(f), CC.kind_of(f["check"], f["msg"], templates())


def measured(msg):
    """[(value, direction)] for the numbers a message measures, where direction is 'low' (smaller is worse: a gap, a
    thread length, a minimum wall) or 'high' (bigger is worse: a volume, an area, a count, an exposed length).
    Object names, poses (pan=-90, z=12..14), coordinates in [..] and limits (< 1.6, max 1.0, needs 6.0, /13, of 26)
    are left out: a limit only moves with the config, and the config diff says so."""
    t = CC.OBJ.sub(" ", msg)
    t = re.sub(r"\[[^\]]*\]|\w+=\S+|\bat z\s*\S+", " ", t)
    out = []
    for m in NUM.finditer(t):
        before = t[max(0, m.start() - 12):m.start()].lower()
        if re.search(r"(<|>|=|/|\bmax|\bneeds|\blimit|\bof|\bvs|\bthan|\bx|\bstep)\s*$", before):
            continue
        low = re.search(r"(only|min|minimum)\s*$", before) or re.match(r"\s*mm (at|across)\b", t[m.end():])
        out.append((float(m.group()), "low" if low else "high"))
    return out


def compare(o, n):
    """'same', 'worse', 'better' or 'changed' for two findings with one key."""
    if o["status"] != n["status"]:
        return "worse" if n["status"] == "fail" else "better"
    a, b = measured(o["msg"]), measured(n["msg"])
    if len(a) != len(b) or [d for _, d in a] != [d for _, d in b]:
        return "same" if o["msg"] == n["msg"] else "changed"
    votes = set()
    for (x, d), (y, _) in zip(a, b):
        if abs(x - y) > 1e-9:
            votes.add("worse" if (y > x) == (d == "high") else "better")
    return "same" if not votes else votes.pop() if len(votes) == 1 else "changed"


def pair(old, new):
    """Within one key: identical text first, then the closest messages; the rest are fixed / new."""
    out, old, new = [], list(old), list(new)
    for f in list(new):
        g = next((g for g in old if g["msg"] == f["msg"]), None)
        if g is not None:
            out.append((g, f)); old.remove(g); new.remove(f)
    cand = sorted(((difflib.SequenceMatcher(None, g["msg"], f["msg"]).ratio(), i, j) for i, g in enumerate(old)
                   for j, f in enumerate(new)), reverse=True)
    used_o, used_n = set(), set()
    for _, i, j in cand:
        if i not in used_o and j not in used_n:
            out.append((old[i], new[j])); used_o.add(i); used_n.add(j)
    return out, [g for i, g in enumerate(old) if i not in used_o], [f for j, f in enumerate(new) if j not in used_n]


def diff_findings(old_rep, new_rep):
    ro, rn = ran(old_rep), ran(new_rep)
    both = None if ro is None or rn is None else ro & rn
    skipped = sorted((ro or set()) ^ (rn or set())) if both is not None else []
    groups = {}
    for side, rep in ((0, old_rep), (1, new_rep)):
        for f in findings(rep):
            if both is not None and f["check"] not in both:
                continue
            groups.setdefault(key(f), ([], []))[side].append(f)
    res = {k: [] for k in ("new", "fixed", "worse", "better", "changed", "same", "now_accepted", "now_untriaged")}
    for k, (o, n) in groups.items():
        pairs, gone, came = pair(o, n)
        res["fixed"] += gone
        res["new"] += came
        for g, f in pairs:
            v = compare(g, f)
            res[v].append((g, f))
            if g["accepted"] != f["accepted"] and f["status"] == "warn":
                res["now_accepted" if f["accepted"] else "now_untriaged"].append((g, f))
    rank = {"fail": 0, "warn": 1}
    for k in ("new", "fixed"):
        res[k].sort(key=lambda f: (rank[f["status"]], f["accepted"], f["line"]))
    for k in ("worse", "better", "changed", "same", "now_accepted", "now_untriaged"):
        res[k].sort(key=lambda p: (rank[p[1]["status"]], p[1]["line"]))
    res["not_compared"] = skipped
    return res


# ------------------------------------------------------------------ requirements (report["config"])

def row_id(sec, r):
    if sec == "accepted_warns":
        return CC.accept_label(r) or json.dumps(r, sort_keys=True)
    if sec in ("allow", "fits") or ("a" in r and "b" in r and not r.get("name")):
        return "%s > %s" % (r.get("a", "*"), r.get("b", "*"))
    lab = CC.row_label(r)
    if isinstance(r.get("objects"), list) and not lab:
        lab = " ".join(map(str, r["objects"]))
    return lab if isinstance(lab, str) else json.dumps({k: v for k, v in r.items() if k != "why"}, sort_keys=True)[:120]


def looser(path, x, y):
    """'loosened' / 'tightened' / 'changed' for a limit moving x -> y, from its name."""
    name = path.split(".")[-1]
    if isinstance(x, bool) or isinstance(y, bool):
        if name.endswith("_ok") or name in ("any", "home_only_ok", "past_limit_ok", "insert_ok"):
            return "loosened" if y else "tightened"
        return "changed"
    if not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
        return "changed"
    if name in HIGHER_LOOSER or name.startswith("max") or name.endswith(("_max", "max_mm3", "tol")) or name == "max":
        return "loosened" if y > x else "tightened"
    if name.startswith("min") or name.endswith(("_min", "_clearance", "min_mm")) or name == "min" or "min_" in name:
        return "loosened" if y < x else "tightened"
    return "changed"


def _short(v, n=50):
    s = json.dumps(v) if not isinstance(v, str) or not v else v
    return s if len(s) <= n else s[:n - 3] + "..."


def _flat(d, pre=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict) and v:
            out.update(_flat(v, "%s%s." % (pre, k)))
        else:
            out[pre + str(k)] = v
    return out


def _delta(x, y, n=4):
    """x -> y, short: changed members of two dicts, members added / removed of two lists of names or numbers."""
    if isinstance(x, dict) and isinstance(y, dict):
        x, y = _flat(x), _flat(y)
        ch = ["%s %s" % (k, "added %s" % _short(y[k], 30) if k not in x else "removed" if k not in y else
                         "%s -> %s" % (_short(x[k], 30), _short(y[k], 30)))
              for k in sorted(set(x) | set(y), key=str) if x.get(k, "<none>") != y.get(k, "<none>")]
        return "; ".join(ch[:n]) + ("; %d more" % (len(ch) - n) if len(ch) > n else "")
    if isinstance(x, list) and isinstance(y, list) and all(not isinstance(v, (dict, list)) for v in x + y):
        add, rem = [v for v in y if v not in x], [v for v in x if v not in y]
        if add or rem:
            return " ".join(filter(None, ("+%s" % _short(add, 60) if add else "", "-%s" % _short(rem, 60) if rem else "")))
    return "%s -> %s" % (_short(x), _short(y))


def _fields(sec, label, a, b, out, renamed=None):
    for k in sorted(set(a) | set(b)):
        if k in ("why", "generated") or str(k).startswith("_"):
            continue
        x, y = a.get(k), b.get(k)
        if x == y or (renamed and x == renamed[0] and y == renamed[1]):
            continue
        path = "%s.%s" % (sec, k)
        if x is None:
            v = "loosened" if (isinstance(y, bool) and y and str(k).endswith("_ok")) or k == "any" else "added"
        elif y is None:
            v = "removed" if not str(k).endswith("_ok") else "tightened"
        else:
            v = looser(path, x, y)
        out.append((v, "%s%s: %s %s" % (sec, " '%s'" % label if label else "", k, _delta(x, y))))


def _rows(sec, old, new, out):
    o = [r for r in old if isinstance(r, dict) and not r.get("generated")]
    n = [r for r in new if isinstance(r, dict) and not r.get("generated")]
    idx = {}
    for side, rows in ((0, o), (1, n)):
        for r in rows:
            idx.setdefault(row_id(sec, r), ([], []))[side].append(r)
    gone, came = [], []
    for rid, (a, b) in idx.items():
        for x, y in zip(a, b):
            _fields(sec, rid, x, y, out)
        gone += [(rid, x) for x in a[len(b):]]
        came += [(rid, y) for y in b[len(a):]]
    strip = lambda r: {k: v for k, v in r.items() if k not in ("name", "why")}
    for g in list(gone):           # a row renamed but otherwise the same is not a requirement gone
        c = next((c for c in came if strip(c[1]) == strip(g[1])), None)
        if c is not None:
            gone.remove(g); came.remove(c)
            out.append(("renamed", "%s row '%s' renamed '%s'" % (sec, g[0], c[0])))
    # a row renamed and edited (v2a7 renamed assembly step '2c turntable ... groove cap, posts ...' and moved the cap
    # out): pair close labels, then list its field changes, so a removed requirement still shows as one
    def close(g, c):     # 0.6 of the label in common, or the same step number ("2c ...", "10d ...")
        t, u = g.split()[:1], c.split()[:1]
        return difflib.SequenceMatcher(None, g, c).ratio() + (1 if t and t == u and re.search(r"\d", t[0]) else 0)
    cand = sorted(((close(g[0], c[0]), i, j) for i, g in enumerate(gone) for j, c in enumerate(came)), reverse=True)
    ug, uc = set(), set()
    for r, i, j in cand:
        if r >= 0.6 and i not in ug and j not in uc:
            ug.add(i); uc.add(j)
            out.append(("renamed", "%s row '%s' renamed '%s'" % (sec, gone[i][0], came[j][0])))
            _fields(sec, came[j][0], gone[i][1], came[j][1], out, (gone[i][0], came[j][0]))
    gone = [g for i, g in enumerate(gone) if i not in ug]
    came = [c for j, c in enumerate(came) if j not in uc]
    loose = sec in LOOSEN_ON_ADD
    for rid, r in gone:
        out.append(("tightened" if loose else "removed", "%s row removed: '%s'%s" % (sec, rid, "  | %s" % r["why"] if r.get("why") else "")))
    for rid, r in came:
        out.append(("loosened" if loose else "added", "%s row added: '%s'%s" % (sec, rid, "  | %s" % r["why"] if r.get("why") else "")))


def _walk(path, a, b, out):
    if isinstance(a, list) and isinstance(b, list) and (any(isinstance(r, dict) for r in a + b) or path in LOOSEN_ON_ADD):
        if any(isinstance(r, dict) for r in a + b):
            return _rows(path, a, b, out)
        for x in a:
            if x not in b:
                out.append(("tightened" if path in LOOSEN_ON_ADD else "removed", "%s: '%s' removed" % (path, _short(x))))
        for y in b:
            if y not in a:
                out.append(("loosened" if path in LOOSEN_ON_ADD else "added", "%s: '%s' added" % (path, _short(y))))
        return
    if isinstance(a, dict) and isinstance(b, dict):
        top = path.split(".")[0]
        named = top in ("joints", "couplings", "carry", "masses_g", "cable_leads", "joint_drives", "printers")
        for k in sorted(set(a) | set(b), key=str):
            if str(k).startswith("_"):
                continue
            p = "%s.%s" % (path, k) if path else str(k)
            if k not in b:
                out.append(("removed", "%s removed (was %s)" % (p, _short(a[k]))))
            elif k not in a:
                out.append(("added", "%s added: %s" % (p, _short(b[k]))))
            elif named and isinstance(a[k], dict) and isinstance(b[k], dict):
                _fields(p, None, a[k], b[k], out)
            else:
                _walk(p, a[k], b[k], out)
        return
    if a != b:
        out.append((looser(path, a, b), "%s: %s -> %s" % (path, _short(a), _short(b))))


def _drop_tests(rep):
    return [t.get("name") for t in ((rep.get("checks") or {}).get("drop") or {}).get("tests") or []
            if isinstance(t, dict) and t.get("name")]


def diff_config(old_rep, new_rep):
    """[(verdict, text)]: verdict removed / loosened (a requirement weaker), tightened / added, renamed, changed."""
    out = []
    _walk("", old_rep.get("config") or {}, new_rep.get("config") or {}, out)
    ro, rn = ran(old_rep), ran(new_rep)
    if (ro is None or "drop" in ro) and (rn is None or "drop" in rn):    # report["config"] leaves drop_tests out
        a, b = _drop_tests(old_rep), _drop_tests(new_rep)
        out += [("removed", "drop_tests row removed: '%s'" % t) for t in a if t not in b]
        out += [("added", "drop_tests row added: '%s'" % t) for t in b if t not in a]
    order = {"removed": 0, "loosened": 1, "tightened": 2, "added": 3, "renamed": 4, "changed": 5}
    return sorted(out, key=lambda x: (order.get(x[0], 9), x[1]))


# ------------------------------------------------------------------ manifest

def diff_manifest(a, b):
    """[(verdict, text)] for parts added / removed / changed, joints, params."""
    out = []
    pa, pb = a.get("parts") or {}, b.get("parts") or {}
    for n in sorted(set(pa) - set(pb)):
        out.append(("removed", "part removed: %s (%s)" % (n, pa[n].get("part") or pa[n].get("kind"))))
    for n in sorted(set(pb) - set(pa)):
        out.append(("added", "part added: %s (%s)" % (n, pb[n].get("part") or pb[n].get("kind"))))
    moved = []
    for n in sorted(set(pa) & set(pb)):
        x, y = pa[n], pb[n]
        for k in MANIFEST_PART_KEYS:
            if x.get(k) != y.get(k) and not (k == "spec" and x.get("part") != y.get("part")):
                v = "length" if k == "length" else "changed"
                out.append((v, "%s %s: %s -> %s" % (n, k, _short(x.get(k)), _short(y.get(k)))))
        bx, by = x.get("bbox_world_home"), y.get("bbox_world_home")
        if bx and by and max(abs(p - q) for u, w in zip(bx, by) for p, q in zip(u, w)) > 0.05:
            moved.append(n)
    if moved:
        out.append(("moved", "%d parts moved or resized at home: %s" % (len(moved), " ".join(moved[:12]) + (" ..." if len(moved) > 12 else ""))))
    ja, jb = a.get("joints") or {}, b.get("joints") or {}
    for n in sorted(set(ja) | set(jb)):
        if n not in jb:
            out.append(("removed", "joint removed: %s" % n))
        elif n not in ja:
            out.append(("added", "joint added: %s %s..%s" % (n, jb[n].get("lo"), jb[n].get("hi"))))
        else:
            x, y = ja[n], jb[n]
            if (x.get("lo"), x.get("hi")) != (y.get("lo"), y.get("hi")):
                out.append(("range", "joint %s range %s..%s -> %s..%s" % (n, x.get("lo"), x.get("hi"), y.get("lo"), y.get("hi"))))
            for k in ("axis", "home", "parent", "continuous", "origin"):
                if x.get(k) != y.get(k):
                    out.append(("changed", "joint %s %s: %s -> %s" % (n, k, _short(x.get(k)), _short(y.get(k)))))
    qa, qb = a.get("params") or {}, b.get("params") or {}
    for k in sorted(set(qa) | set(qb)):
        x, y = qa.get(k), qb.get(k)
        if x != y and not (isinstance(x, str) and isinstance(y, str) and x.startswith("/") and y.startswith("/")):
            out.append(("param", "param %s: %s" % (k, _delta(x, y))))
    return out


# ------------------------------------------------------------------ output

def _tag(f):
    return "FAIL" if f["status"] == "fail" else "warn(accepted)" if f["accepted"] else "warn"


def _nums(g, f):
    a, b = [x for x, _ in measured(g["msg"])], [x for x, _ in measured(f["msg"])]
    ch = ["%g -> %g" % (x, y) for x, y in zip(a, b) if abs(x - y) > 1e-9] if len(a) == len(b) else []
    st = ["%s -> %s" % (g["status"], f["status"])] if g["status"] != f["status"] else []
    return "  [%s]" % ", ".join(st + ch) if st or ch else "  [was: %s]" % g["msg"]


def counts(fd, cd):
    c = {k: len(fd[k]) for k in ("new", "fixed", "worse", "better", "changed")}
    c["new_untriaged"] = sum(1 for f in fd["new"] if not f["accepted"])
    c["req_weaker"] = sum(1 for v, _ in cd if v in ("removed", "loosened")) + len(fd["now_accepted"])
    return c


def regressed(fd, cd):
    c = counts(fd, cd)
    return bool(c["new_untriaged"] or c["worse"] or c["req_weaker"])


def lines(fd, cd, md=None, short=False):
    """Report lines: findings, then requirement changes, then manifest. short: only what got worse, what was fixed
    and requirements that weakened."""
    out = []
    W = lambda tag, s: out.append("%-7s %s" % (tag, s))
    for f in fd["new"]:
        if not (short and f["accepted"]):
            W("new", "%s %s" % (_tag(f), f["line"]))
    for g, f in fd["worse"]:
        W("worse", "%s %s%s" % (_tag(f), f["line"], _nums(g, f)))
    for f in fd["fixed"]:
        W("fixed", "%s %s" % (_tag(f), f["line"]))
    for g, f in fd["now_accepted"]:
        W("accept", "now accepted: %s" % f["line"])
    if not short:
        for g, f in fd["better"]:
            W("better", "%s %s%s" % (_tag(f), f["line"], _nums(g, f)))
        for g, f in fd["changed"]:
            W("changed", "%s %s%s" % (_tag(f), f["line"], _nums(g, f)))
        for g, f in fd["now_untriaged"]:
            W("accept", "no longer accepted: %s" % f["line"])
        for g, f in fd["same"]:      # still there: what a reviewer marks NOT FIXED (accepted warns left out)
            if not f["accepted"]:
                W("still", "%s %s" % (_tag(f), f["line"]))
    for v, s in cd:
        if not short or v in ("removed", "loosened"):
            W({"removed": "REQ-", "loosened": "REQ~", "tightened": "req+", "added": "req+"}.get(v, "req"), "%s%s" % (
                "%s: " % v if v not in ("removed", "added") else "", s))
    for v, s in md or []:
        W("part", s)
    return out


def headline(fd, cd, md=None):
    c = counts(fd, cd)
    s = "%d new (%d untriaged), %d fixed, %d worse, %d better, %d changed, %d same" % (
        c["new"], c["new_untriaged"], c["fixed"], c["worse"], c["better"], c["changed"], len(fd["same"]))
    rem = sum(1 for v, _ in cd if v == "removed")
    loo = sum(1 for v, _ in cd if v == "loosened")
    s += "; requirements: %d removed, %d loosened, %d warns newly accepted, %d other config changes" % (
        rem, loo, len(fd["now_accepted"]), len(cd) - rem - loo)
    if md is not None:
        s += "; manifest: %d changes" % len(md)
    if fd["not_compared"]:
        s += "; not compared (ran in one run only): %s" % ", ".join(fd["not_compared"])
    return s


def short_report(old_rep, new_rep, prev_path, new_path, cap=20):
    """The delta `cad check` prints at the end when it overwrote a report: one headline, then up to `cap` lines."""
    fd, cd = diff_findings(old_rep, new_rep), diff_config(old_rep, new_rep)
    c = counts(fd, cd)
    if not any((c["new"], c["fixed"], c["worse"], c["better"], c["changed"], cd, fd["now_accepted"], fd["now_untriaged"])):
        return ["delta vs the previous report (%s): no change in findings or requirements%s" % (
            old_rep.get("generated", "?"), "; not compared: %s" % ", ".join(fd["not_compared"]) if fd["not_compared"] else "")]
    out = ["delta vs the previous report (%s): %s" % (old_rep.get("generated", "?"), headline(fd, cd))]
    if old_rep.get("blend") and new_rep.get("blend") and old_rep["blend"] != new_rep["blend"]:
        out.append("  (the previous report was of %s)" % old_rep["blend"])
    body = lines(fd, cd, short=True)
    out += ["  " + x for x in body[:cap]]
    more = max(0, len(body) - cap) + c["better"] + c["changed"] + sum(1 for v, _ in cd if v not in ("removed", "loosened"))
    if more > 0:
        out.append("  ... %d more (past the first %d, better, changed, other config): cad diff %s %s" % (more, cap, prev_path, new_path))
    return out


def prev_path(out):
    return (out[:-5] if out.endswith(".json") else out) + ".prev.json"


def load(p):
    with open(p) as f:
        return json.load(f)


def main(argv):
    if not argv or any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0 if argv else 2
    man, pos, cap, it = None, [], 0, iter(argv)
    for a in it:
        if a == "--manifest":
            man = (next(it, ""), next(it, ""))
        elif a == "--max":
            cap = int(next(it, "0") or 0)
        elif a.startswith("--"):
            print("caddiff: unknown flag %s" % a)
            return 2
        else:
            pos.append(a)
    if len(pos) == 1:
        pos.insert(0, prev_path(pos[0]))
    if len(pos) != 2:
        print("caddiff: give OLD.json NEW.json (or NEW.json with a .prev.json next to it)")
        return 2
    try:
        old, new = load(pos[0]), load(pos[1])
    except (OSError, ValueError) as e:
        print("caddiff: %s" % e)
        return 2
    if "checks" not in old or "checks" not in new:
        print("caddiff: %s is not a cadcheck report" % (pos[0] if "checks" not in old else pos[1]))
        return 2
    if man is None:
        cand = tuple(os.path.join(os.path.dirname(os.path.abspath(p)), "manifest.json") for p in pos)
        man = cand if all(os.path.isfile(m) for m in cand) and os.path.realpath(cand[0]) != os.path.realpath(cand[1]) else None
    md = None
    if man:
        try:
            md = diff_manifest(load(man[0]), load(man[1]))
        except (OSError, ValueError) as e:
            print("caddiff: manifest: %s" % e)
            return 2
    fd, cd = diff_findings(old, new), diff_config(old, new)
    print("CADDIFF %s (%s) -> %s (%s)" % (pos[0], old.get("generated", "?"), pos[1], new.get("generated", "?")))
    print("  " + headline(fd, cd, md))
    body = lines(fd, cd, md)
    for x in body[:cap or len(body)]:
        print("  " + x)
    if cap and len(body) > cap:
        print("  ... %d more lines (raise --max)" % (len(body) - cap))
    return 1 if regressed(fd, cd) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
