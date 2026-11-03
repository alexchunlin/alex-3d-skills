#!/usr/bin/env python3
"""Parameter-perturbation audit (issue #45): which cadcheck findings flip when one params value moves by a print tolerance.

For each selected top-level numeric parameter it builds and checks the project in a scratch copy with the value nudged
-d and +d, runs `cad diff nominal perturbed`, and records the findings that appeared, disappeared or changed status.
A design that passes only at nominal shows up as a new fail (or untriaged warn) one tolerance away. The nominal is built
and checked once; a control (an unchanged rebuild) shows what the check does on its own, so its flips are noise.

    python3 -I tools/bench/perturb.py PROJECT [--build build_assembly.py] [--params-file params.py] [--checks checks.json]
        [--build-args "--out {out}"] [--delta 0.2] [--angle-delta 1.0] [--range NAME=LO:HI ...] [--params REGEX]
        [--limit N] [--only CHECKS | --quick] [-j 2] [--out DIR] [--no-control] [--ints] [--list]

  parameters   top-level assignments in --params-file (default params.py; a build script that holds its own constants
               works too: --params-file build.py) whose value is a number literal: `X = 2.4`, `A, B = 45.0, 112.0`, and
               each element of a flat number tuple, `MM_T = (6.3, 7.5)` -> MM_T[0], MM_T[1]. Skipped: derived values
               (`L = ARM_GAP - 2 * CLR`), conditionals, strings, nested lists, ints (counts; --ints keeps them).
  delta        0.2 mm, or 1.0 deg for an angle (the name has PSI/ANG/DEG/TWIST/THETA/PHI, ends _LO/_HI, or its comment
               says deg; --angles REGEX overrides); --range NAME=LO:HI uses an adjuster's own range as the two values.
  rewrite      the literal's own source span is replaced in the scratch copy (ast offsets): no other text changes.
  scratch      PROJECT is copied to OUT/<tag>/ (no .blend, stl/, renders/, __pycache__, cadcheck*.json). A project
               inside this repo keeps its repo-relative path there, with skills/ and components/ linked, so a build
               script's `HERE/../../skills` import still resolves. `{out}` in --build-args is OUT/<tag>/out.
  flips        new / fixed findings (by cad diff's key: check, objects, kind) and worse / better ones whose status
               changed (warn <-> fail). Same status, other number: `drift` (counted, a few lines kept).
  brittle      a (param, sign) run brings a new fail, a new untriaged warn, a warn -> fail (not a pinned row), or a build
               error (a params.py assert), that the control run does not show. --from DIR rescores a run after a label edit.
  classes      each flip: "pinned row" (a row whose wanted window is no wider than the 2 d band, e.g. "wanted 6.0..6.4":
               it pins the nominal, so it fails by construction; never brittle), "label" (a tools/bench/labels.json locator of any attempt matches it, replay.py's matcher),
               "printability" (a printability locator matches, or check parts/printcheck), "noise (control)" (the
               control run flipped the same key), else "noise candidate".

Writes OUT/perturb.json and OUT/perturb.md (default OUT: /tmp/alex3d-perturb/run-<pid>). Plain python3 -I: drives
`cad build`, `cad check` and `cad diff` as subprocesses; imports caddiff (plain python) for the structured diff; never bpy.
Exit 0 when it ran (brittle parameters are a result, not an error), 2 on bad input or a nominal build/check failure.
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "print-cad-blender" / "scripts"
CAD = os.environ.get("CAD") or str(SCRIPTS / "cad")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import caddiff as D  # noqa: E402  plain python3: the same diff `cad diff` prints

try:
    from replay import _match as loc_match  # noqa: E402  the bench's locator matcher
except Exception:  # pragma: no cover - fall back to check + objects
    loc_match = None

SKIP_RE = r"RGBA|RGB\b|COLOU?R|MASS|DENSITY"   # not geometry: colours, masses (g)
ANGLE_RE = r"(?:^|_)(?:PSI|ANG|ANGLE|DEG|TWIST|THETA|PHI)(?:_|\d|$)|_(?:LO|HI)$"
IGNORE = shutil.ignore_patterns("__pycache__", "*.blend", "*.blend1", "stl", "renders", "cadcheck*.json", "*.pyc")
FLIP_CAP = 12


# ------------------------------------------------------------------ parameters

def _num(node):
    """A number literal (with an optional sign): its value, else None. Bools are not numbers here."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _num(node.operand)
        return None if v is None else (-v if isinstance(node.op, ast.USub) else v)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    return None


def list_params(src: str, ints: bool = False, angles: str = ANGLE_RE, skip: str = SKIP_RE):
    """([param], [(name, why skipped)]) for the top-level assignments of a module source."""
    tree = ast.parse(src)
    lines = src.splitlines()
    params, skipped = [], []

    def comment(lineno):
        ln = lines[lineno - 1]
        return ln.split("#", 1)[1].strip() if "#" in ln else ""

    def add(name, node):
        v = _num(node)
        if v is None:
            skipped.append((name, "derived" if not isinstance(node, (ast.Constant, ast.Tuple, ast.List)) else "non-numeric"))
            return
        if isinstance(v, int) and not ints:
            skipped.append((name, "int"))
            return
        base = name.split("[")[0]
        if skip and re.search(skip, base):
            skipped.append((name, "not geometry"))
            return
        c = comment(node.lineno)
        ang = bool(re.search(angles, base)) or bool(re.search(r"\bdeg\b", c) and not re.search(r"\bmm\b", c))
        params.append({"name": name, "value": v, "angle": ang, "line": node.lineno,
                       "span": (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset), "comment": c[:80]})

    def value_of(name, node):
        if isinstance(node, (ast.Tuple, ast.List)) and node.elts and all(_num(e) is not None for e in node.elts):
            for i, e in enumerate(node.elts):
                add("%s[%d]" % (name, i), e)
        elif isinstance(node, (ast.Tuple, ast.List)):
            skipped.append((name, "nested or mixed"))
        else:
            add(name, node)

    for st in tree.body:
        if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and st.value is not None:
            value_of(st.target.id, st.value)
            continue
        if not isinstance(st, ast.Assign) or len(st.targets) != 1:
            continue
        t, v = st.targets[0], st.value
        if isinstance(t, ast.Name):
            value_of(t.id, v)
        elif isinstance(t, ast.Tuple) and all(isinstance(e, ast.Name) for e in t.elts):
            if isinstance(v, ast.Tuple) and len(v.elts) == len(t.elts):
                for n, e in zip(t.elts, v.elts):
                    value_of(n.id, e)
            else:
                skipped += [(n.id, "derived") for n in t.elts]
    return params, skipped


def rewrite(src: str, span, value) -> str:
    """src with the literal at span (ast line/col, col in UTF-8 bytes) replaced by value."""
    l0, c0, l1, c1 = span
    b = [ln.encode() for ln in src.splitlines(keepends=True)]
    head = b"".join(b[:l0 - 1]) + b[l0 - 1][:c0]
    tail = b[l1 - 1][c1:] + b"".join(b[l1:])
    return (head + _fmt(value).encode() + tail).decode()


def _fmt(v) -> str:
    s = repr(round(float(v), 6))
    return "(%s)" % s if s.startswith("-") else s


# ------------------------------------------------------------------ runs

def stage(project: Path, dest: Path) -> Path:
    """Copy project into dest; returns the copy's path (repo-relative inside dest when project is in this repo)."""
    try:
        rel = project.resolve().relative_to(ROOT)
        inside = True
    except ValueError:
        rel, inside = Path(project.name), False
    pdir = dest / rel
    shutil.copytree(project, pdir, ignore=IGNORE)
    if inside:
        for d in ("skills", "components"):
            if (ROOT / d).exists() and not (dest / d).exists():
                (dest / d).symlink_to(ROOT / d)
    return pdir


def _files(d: Path, suffix: str):
    """Files under d ending in suffix, not following links (the linked skills/ and components/ stay out)."""
    for top, dirs, files in os.walk(d):
        for f in files:
            if f.endswith(suffix):
                yield Path(top) / f


def _newest(d: Path, name: str, since: float):
    c = [p for p in _files(d, name) if p.stat().st_mtime >= since - 1]
    return max(c, key=lambda p: p.stat().st_mtime) if c else None


def _stl_hashes(d: Path) -> dict:
    return {str(p.relative_to(d)): hashlib.sha1(p.read_bytes()).hexdigest()[:12] for p in sorted(_files(d, ".stl"))}


def run_one(a, tag: str, out: Path, edit=None, timeout=3600) -> dict:
    """Build + check one scratch copy. edit = (param, value) or None (nominal / control)."""
    dest = out / tag
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    pdir = stage(a.project, dest)
    r = {"tag": tag, "dir": str(dest)}
    if edit:
        p, v = edit
        pf = pdir / a.params_file
        pf.write_text(rewrite(pf.read_text(), p["span"], v))
        r.update(param=p["name"], value=v)
    bargs = [x.replace("{out}", str(dest / "out")) for x in a.build_args.split()] if a.build_args else []
    t0 = time.time()
    with open(dest / "build.log", "w") as log:
        try:
            rc = subprocess.run([CAD, "build", str(pdir / a.build)] + (["--"] + bargs if bargs else []), cwd=pdir,
                                stdout=log, stderr=subprocess.STDOUT, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    r["build_s"] = round(time.time() - t0, 1)
    blend = _newest(dest, ".blend", t0)
    if rc != 0 or blend is None:
        r["error"] = "build failed (exit %s)%s: %s" % (rc, "" if blend else ", no .blend", _tail(dest / "build.log"))
        return r
    man = _newest(dest, "manifest.json", t0)
    rep = dest / "cadcheck.json"
    extra = (["--only", a.only] if a.only else []) + (["--quick"] if a.quick else [])
    t1 = time.time()
    with open(dest / "check.log", "w") as log:
        try:
            crc = subprocess.run([CAD, "check", str(blend), str(pdir / a.checks), str(rep), "--no-diff"] + extra, cwd=pdir,
                                 stdout=log, stderr=subprocess.STDOUT, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            crc = "timeout"
    r["check_s"] = round(time.time() - t1, 1)
    if not rep.is_file():
        r["error"] = "check wrote no report (exit %s): %s" % (crc, _tail(dest / "check.log"))
        return r
    r.update(report=str(rep), manifest=str(man) if man else None, stls=_stl_hashes(dest))
    return r


def _tail(p: Path, n=2) -> str:
    """The exception line of a failed build (a params assert names the broken rule), else the last n lines."""
    try:
        ls = [l.strip() for l in p.read_text().splitlines() if l.strip()]
    except OSError:
        return ""
    exc = [l for l in ls if re.match(r"\w*(Error|Exception)\b.*?: ", l) and not l.startswith("Error: script failed")]
    return (exc[-1] if exc else " | ".join(ls[-n:]))[:300]


def fkey(f) -> str:
    chk, objs, kind = D.key(f)
    return "%s | %s | %s" % (chk, " ".join(objs), kind)


def diff_one(nom: dict, r: dict, out: Path) -> dict:
    """cad diff nominal -> run (text kept in <tag>/diff.txt), and the structured flips from caddiff."""
    cmd = [CAD, "diff", nom["report"], r["report"]]
    if nom.get("manifest") and r.get("manifest"):
        cmd += ["--manifest", nom["manifest"], r["manifest"]]
    p = subprocess.run(cmd, capture_output=True, text=True)
    (Path(r["dir"]) / "diff.txt").write_text(p.stdout + p.stderr)
    old, new = D.load(nom["report"]), D.load(r["report"])
    fd = D.diff_findings(old, new)
    flips, drift = [], []
    for ch in ("new", "fixed"):
        for f in fd[ch]:
            flips.append({"change": ch, "status": "warn(accepted)" if f["accepted"] else f["status"], "line": f["line"], "key": fkey(f)})
    # a new and a fixed finding on the same check and objects is one finding whose message kind changed ("0.50 mm at
    # pan=-90" -> "0.30 mm just past the limit"): a flip only when the status changed too
    for n in [f for f in flips if f["change"] == "new"]:
        g = next((g for g in flips if g["change"] == "fixed" and g["key"].rsplit(" | ", 1)[0] == n["key"].rsplit(" | ", 1)[0]), None)
        if g is None:
            continue
        flips.remove(g)
        if g["status"] == n["status"]:
            flips.remove(n)
            drift.append("rekeyed %s  [was: %s]" % (n["line"][:90], g["line"][:60]))
        else:
            n.update(change="rekeyed", status="%s->%s" % (g["status"], n["status"]), was=g["line"])
    for ch in ("worse", "better", "changed"):
        for g, f in fd[ch]:
            if g["status"] != f["status"]:
                flips.append({"change": ch, "status": "%s->%s" % (g["status"], f["status"]), "line": f["line"], "key": fkey(f)})
            else:
                drift.append("%s %s" % (ch, f["line"][:110]))
    md = []
    if nom.get("manifest") and r.get("manifest"):
        md = [t for _, t in D.diff_manifest(D.load(nom["manifest"]), D.load(r["manifest"]))]
    changed = sorted(k for k in set(nom.get("stls", {})) | set(r.get("stls", {})) if nom["stls"].get(k) != r["stls"].get(k))
    return {"cad_diff_exit": p.returncode, "flips": flips, "drift_n": len(drift), "drift": drift[:6],
            "not_compared": fd["not_compared"], "manifest": md[:8], "stls_changed": changed}


# ------------------------------------------------------------------ classes

def load_labels(path: Path):
    if not path or not path.is_file():
        return [], []
    d = json.load(open(path))
    lab = [(e, l) for e in d.get("labels", []) for l in (e.get("locators") or [])]
    pf = [(e, l) for e in d.get("printability", []) for l in (e.get("locators") or [])]
    return lab, pf


def _m(loc, line):
    if loc_match is not None:
        try:
            return loc_match(loc, line)
        except re.error:
            return False
    return line.startswith(loc["check"] + ": ") and all(o in line for o in loc.get("objects", []))


PINNED = re.compile(r"wanted (-?[\d.]+)\.\.(-?[\d.]+)")


def pinned(line: str, d: float) -> bool:
    """A row whose wanted window is no wider than the nudge band (2 d): it pins the nominal, so any nudge fails it."""
    m = PINNED.search(line)
    return bool(m) and float(m.group(2)) - float(m.group(1)) <= 2 * d + 1e-6


def classify(flip, labels, pf, control_keys, d):
    hits = sorted({"%s (%s)" % (e.get("id"), e.get("attempt")) for e, l in labels if _m(l, flip["line"])})
    if pinned(flip["line"], d):
        return "pinned row", hits
    if hits:
        return "label", hits
    if any(_m(l, flip["line"]) for _, l in pf) or flip["line"].split(":", 1)[0] in ("parts", "printcheck"):
        return "printability", []
    if flip["key"] in control_keys:
        return "noise (control)", []
    return "noise candidate", []


def bad_flip(f) -> bool:
    if f.get("class") == "pinned row":
        return False
    return (f["change"] == "new" and f["status"] in ("fail", "warn")) or f["status"] == "warn->fail"


# ------------------------------------------------------------------ output

def md_table(res: dict) -> str:
    c = res["cost"]
    out = ["# perturbation audit: %s" % res["project"], "",
           "%d parameters of %d listed (%d skipped as derived / non-numeric / int); delta %g mm, %g deg for angles; "
           "checks: %s. Nominal: %d build(s), %s. Control (unchanged rebuild): %s." % (
               len(res["params"]), res["n_listed"], res["n_skipped"], res["delta"], res["angle_delta"], res["checks_run"],
               res["nominal_builds"], res["nominal"]["summary"], res["control"]["summary"] if res.get("control") else "not run"),
           "", "| param | nominal | delta | -d flips | +d flips | geometry -/+ | brittle |", "|---|---|---|---|---|---|---|"]
    for p in res["params"]:
        cells = []
        for s in ("-", "+"):
            r = p["runs"].get(s, {})
            if r.get("error"):
                cells.append("**build error**: " + r["error"].split(": ", 1)[-1][:110].replace("|", "/"))
                continue
            fl = r.get("flips", [])
            cells.append("; ".join("%s %s %s" % ({"new": "+", "fixed": "-"}.get(f["change"], "~"), f["status"], f["key"][:70])
                                   for f in fl[:4]) + (" (+%d more)" % (len(fl) - 4) if len(fl) > 4 else "") or "none")
        geo = "/".join(("%d stl" % len(p["runs"][s].get("stls_changed", []))) if s in p["runs"] else "-" for s in ("-", "+"))
        out.append("| %s | %g | %s | %s | %s | %s | %s |" % (p["name"], p["value"], p["delta_label"], cells[0], cells[1], geo,
                                                       "**yes**" if p["brittle"] else "no"))
    out += ["", "Flips by class: " + (", ".join("%s %d" % kv for kv in sorted(res["flip_classes"].items())) or "none") + ". "
            "No geometry change at either sign (the value reaches no exported STL): " + (" ".join(res["noop"]) or "none") + ".", ""]
    rows = [(p["name"], s, f) for p in res["params"] for s, r in sorted(p["runs"].items()) for f in r.get("flips", [])]
    if rows:
        out += ["| param | sign | change | status | finding | class | label |", "|---|---|---|---|---|---|---|"]
        for n, s, f in rows[:60]:
            out.append("| %s | %s | %s | %s | %s | %s | %s |" % (n, s, f["change"], f["status"], f["line"][:100].replace("|", "/"),
                                                            f["class"], ", ".join(f.get("labels", [])) or "-"))
    out += ["", "Cost: nominal build %.1f s + check %.1f s; per perturbed rebuild+check %.1f s mean (%d runs, -j %d); total wall "
            "%.0f s. All %d listed parameters x 2 at -j %d: about %.0f min." % (
                c["nominal_build_s"], c["nominal_check_s"], c["mean_run_s"], c["runs"], c["jobs"], c["total_wall_s"],
                res["n_listed"], c["jobs"], c["extrapolated_all_min"]), ""]
    return "\n".join(out)


def _summary(rep_path):
    s = (D.load(rep_path).get("summary") or {})
    return "%s fail, %s warn" % (s.get("fails", "?"), s.get("warns", "?"))


def score(res: dict, labels_path: Path) -> dict:
    """Classes, brittle and no-op flags from the runs (again after a label edit: --from DIR)."""
    labels, pf = load_labels(labels_path)
    ctl_keys = {f["key"] for f in (res.get("control") or {}).get("flips", [])}
    classes = {}
    for p in res["params"]:
        m = re.search(r"([\d.]+) (?:mm|deg)", p["delta_label"])
        d = float(m.group(1)) if m else 0.0      # a --range row: no band, nothing is pinned
        for r in p["runs"].values():
            if r.get("error") and r.get("dir"):
                r["error"] = r["error"].split(": ", 1)[0] + ": " + _tail(Path(r["dir"]) / ("check.log" if "check_s" in r else "build.log"))
            for f in r.get("flips", []):
                f["class"], f["labels"] = classify(f, labels, pf, ctl_keys, d)
                classes[f["class"]] = classes.get(f["class"], 0) + 1
        p["brittle"] = any(bool(r.get("error")) or any(bad_flip(f) and f["key"] not in ctl_keys for f in r.get("flips", []))
                           for r in p["runs"].values())
    res["flip_classes"] = classes
    res["brittle"] = [p["name"] for p in res["params"] if p["brittle"]]
    res["noop"] = [p["name"] for p in res["params"] if all("stls" in r and not r.get("stls_changed") for r in p["runs"].values())]
    res["build_errors"] = ["%s %s" % (p["name"], s) for p in res["params"] for s, r in sorted(p["runs"].items()) if r.get("error")]
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("project", type=Path, nargs="?")
    ap.add_argument("--from", dest="from_dir", type=Path, help="rescore an earlier run's perturb.json (labels, classes), rewrite its .md")
    ap.add_argument("--build", help="build script in PROJECT (default build_assembly.py, else build.py)")
    ap.add_argument("--params-file", default="params.py")
    ap.add_argument("--checks", default="checks.json")
    ap.add_argument("--build-args", default="", help='passed after `--` to the build; {out} = the scratch out dir')
    ap.add_argument("--delta", type=float, default=0.2)
    ap.add_argument("--angle-delta", type=float, default=1.0)
    ap.add_argument("--angles", default=ANGLE_RE, help="regex on the name: these are angles (deg)")
    ap.add_argument("--skip", default=SKIP_RE, help="regex on the name: not geometry, never nudged")
    ap.add_argument("--range", action="append", default=[], metavar="NAME=LO:HI", help="an adjuster's own range")
    ap.add_argument("--params", default="", help="regex: only parameters whose name matches")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("-j", "--jobs", type=int, default=1)
    ap.add_argument("--out", type=Path, default=Path("/tmp/alex3d-perturb/run-%d" % os.getpid()))
    ap.add_argument("--labels", type=Path, default=ROOT / "tools" / "bench" / "labels.json")
    ap.add_argument("--no-control", action="store_true")
    ap.add_argument("--ints", action="store_true")
    ap.add_argument("--list", action="store_true", help="list the parameters and exit (no Blender)")
    ap.add_argument("--timeout", type=int, default=3600)
    a = ap.parse_args(argv)
    if a.from_dir:
        res = score(json.load(open(a.from_dir / "perturb.json")), a.labels)
        (a.from_dir / "perturb.json").write_text(json.dumps(res, indent=1))
        (a.from_dir / "perturb.md").write_text(md_table(res))
        print("perturb: rescored %s: brittle %s, flips %s" % (a.from_dir, " ".join(res["brittle"]) or "none", res["flip_classes"] or "none"))
        return 0
    if a.project is None:
        ap.error("give PROJECT (or --from DIR)")
    a.project = a.project.resolve()
    a.jobs = max(1, min(2, a.jobs))
    if not a.build:
        a.build = next((b for b in ("build_assembly.py", "build.py") if (a.project / b).is_file()), "build_assembly.py")
    for f in (a.build, a.params_file, a.checks):
        if not (a.project / f).is_file():
            print("perturb: %s not found in %s" % (f, a.project))
            return 2
    params, skipped = list_params((a.project / a.params_file).read_text(), a.ints, a.angles, a.skip)
    n_listed = len(params)
    ranges = {}
    for s in a.range:
        try:
            n, lohi = s.split("=", 1)
            lo, hi = (float(x) for x in lohi.split(":"))
            ranges[n] = (lo, hi)
        except ValueError:
            print("perturb: --range wants NAME=LO:HI, not %s" % s)
            return 2
    sel = [p for p in params if not a.params or re.search(a.params, p["name"])]
    if a.limit:
        sel = sel[:a.limit]
    if a.list:
        for p in params:
            print("%-28s %10g  %s  line %d  %s" % (p["name"], p["value"], "deg" if p["angle"] else "mm ", p["line"], p["comment"]))
        print("%d numeric parameters, %d skipped: %s" % (len(params), len(skipped), ", ".join("%s (%s)" % s for s in skipped[:30])
                                                        + (" ..." if len(skipped) > 30 else "")))
        return 0
    if not sel:
        print("perturb: no parameter matches %r" % a.params)
        return 2
    a.out.mkdir(parents=True, exist_ok=True)
    t_all = time.time()
    print("perturb: %d of %d parameters, 2 runs each%s, -j %d -> %s" % (len(sel), n_listed, "" if a.no_control else " + control", a.jobs, a.out), flush=True)
    nom = run_one(a, "nominal", a.out, timeout=a.timeout)
    if nom.get("error"):
        print("perturb: nominal: %s" % nom["error"])
        return 2
    print("  nominal: build %.1f s, check %.1f s, %s" % (nom["build_s"], nom["check_s"], _summary(nom["report"])), flush=True)
    jobs = [] if a.no_control else [("control", None, None)]
    for p in sel:
        if p["name"] in ranges:
            lo, hi = ranges[p["name"]]
            p["delta_label"], vals = "range %g..%g" % (lo, hi), {"-": lo, "+": hi}
        else:
            d = a.angle_delta if p["angle"] else a.delta
            p["delta_label"] = "±%g %s" % (d, "deg" if p["angle"] else "mm")
            vals = {"-": p["value"] - d, "+": p["value"] + d}
        for s, v in vals.items():
            jobs.append(("%s%s" % (re.sub(r"\W", "_", p["name"]), "m" if s == "-" else "p"), p, (s, v)))
    results = {}

    def work(j):
        tag, p, sv = j
        r = run_one(a, tag, a.out, (p, sv[1]) if p else None, a.timeout)
        if not r.get("error"):
            r.update(diff_one(nom, r, a.out))
        return j, r

    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for (tag, p, sv), r in ex.map(work, jobs):
            results[tag] = r
            print("  %-22s %s" % (tag, r.get("error") or "build %.1f s, check %.1f s, %d flips, %d drift, %d stl changed" % (
                r["build_s"], r["check_s"], len(r["flips"]), r["drift_n"], len(r["stls_changed"]))), flush=True)
    ctl = results.get("control")
    out_params = [{"name": p["name"], "value": p["value"], "angle": p["angle"], "line": p["line"], "delta_label": p["delta_label"],
                   "runs": {s: results["%s%s" % (re.sub(r"\W", "_", p["name"]), "m" if s == "-" else "p")] for s in ("-", "+")}}
                  for p in sel]
    pruns = [r for r in results.values() if "check_s" in r and r is not ctl]
    mean = sum(r["build_s"] + r["check_s"] for r in pruns) / len(pruns) if pruns else 0.0
    res = {"tool": "tools/bench/perturb.py", "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "project": str(a.project), "build": a.build, "params_file": a.params_file, "checks": a.checks,
           "checks_run": ("--only " + a.only if a.only else "full") + (" --quick" if a.quick else ""),
           "delta": a.delta, "angle_delta": a.angle_delta, "ranges": ranges, "n_listed": n_listed, "n_skipped": len(skipped),
           "skipped": skipped, "nominal_builds": 1,
           "nominal": {"build_s": nom["build_s"], "check_s": nom["check_s"], "report": nom["report"], "summary": _summary(nom["report"])},
           "control": ({"flips": ctl.get("flips", []), "drift_n": ctl.get("drift_n"), "stls_changed": ctl.get("stls_changed"),
                        "error": ctl.get("error"), "summary": ctl.get("error") or "%d flips, %d drift, %d stl changed" % (
                            len(ctl.get("flips", [])), ctl.get("drift_n", 0), len(ctl.get("stls_changed", [])))} if ctl else None),
           "params": out_params,
           "cost": {"nominal_build_s": nom["build_s"], "nominal_check_s": nom["check_s"], "runs": len(pruns), "jobs": a.jobs,
                    "mean_run_s": round(mean, 1), "total_wall_s": round(time.time() - t_all, 1),
                    "extrapolated_all_min": round((n_listed * 2 * mean / a.jobs + nom["build_s"] + nom["check_s"]) / 60, 1)}}
    score(res, a.labels)
    (a.out / "perturb.json").write_text(json.dumps(res, indent=1))
    (a.out / "perturb.md").write_text(md_table(res))
    classes = res["flip_classes"]
    print("perturb: %d brittle of %d (%s); flips %s; %.0f s -> %s/perturb.{json,md}" % (
        len(res["brittle"]), len(out_params), " ".join(res["brittle"]) or "none", classes or "none", res["cost"]["total_wall_s"], a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
