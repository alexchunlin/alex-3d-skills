#!/usr/bin/env python3
"""Replay bench: score a tools commit against what the reviewers found on the 10 archived designs.

No LLM. For each archived attempt (tools/bench/corpus.json) it makes the cad runs tools/verify_all.sh makes (same
configs, overlays, --only sets, CAD_LAYER_CHECK), with the `cad` of the chosen commit, and scores the reports against
tools/bench/labels.json. Three kinds of ground truth, scored apart:

  labels                the issues the reviewers raised: the headline recall (process items are out of the denominator)
  printability          tool findings no reviewer raised (the layer check's support misses), one entry per finding,
                        scored once per finding over the attempts it is on, in their own score
  known_true_positives  planted overlay rows and exploratory review rows: not false fails, credit nothing

Per attempt and scope ("designer": the designer's config plus the always-on tools; "rows": also the reviewer's rows):

  recall_fail / recall_fw     reviewer labels whose best line is a fail / a fail or warn (accepted warns count)
  recall_*_w                  the same, severity-weighted (blocker 3, major 2, minor 1)
  partial                     only a partial locator matched (a coverage warn, a sub-point): not caught
  label_errors                uncaught labels whose check came from a run that crashed: an error, not a miss
  false_fails                 fails that match no locator of a label, printability finding or known true positive
  noise_warns / hit_share     untriaged warns that match no locator / the share that do
  runtime_s                   information only (machine load moves it); never a gate

One JSON row per (commit, attempt), plus ALL-v1, ALL-v2 and ALL rows (v1 was never triaged: keep it apart from v2).

  python3 -I tools/bench/replay.py                         # HEAD's tools, all 10 attempts
  python3 -I tools/bench/replay.py --commit origin/next    # another commit's skills/ (git archive into the scratch dir)
  python3 -I tools/bench/replay.py --attempts v2a6,v2a7 -j 2
  python3 -I tools/bench/replay.py --from-verify /tmp/alex3d-verify/run-<pid>   # a verify_all run (its meta.json names the commit)
  python3 -I tools/bench/replay.py --from-run /tmp/alex3d-bench/run-<pid>       # rescore a bench run (after a label edit)
  python3 -I tools/bench/replay.py table [--results F] [--commit C]
  python3 -I tools/bench/replay.py compare BASE NEW        # gate: refuses rows with other labels, errors or run subsets
  python3 -I tools/bench/replay.py lint                    # locator lint (the smoke test runs it)
  python3 -I tools/bench/replay.py xcheck --from-run DIR   # labels vs verify_all's per-attempt assertions (report only)

Scratch: /tmp/alex3d-bench/run-<pid>, as verify_all does under /tmp/alex3d-verify. Plain python3, standard library;
it never runs a slicer.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = Path(__file__).resolve().parent
SCRATCH_BASE = Path("/tmp/alex3d-bench")
STATUS_RANK = {"fail": 3, "warn": 2, "accepted": 1, None: 0}
CAUGHT_FW = ("fail", "warn", "accepted")
SEV_W = {"blocker": 3, "major": 2, "minor": 1}
# every check a report line can start with: cadcheck's checks (and its stale-model "build" warn), printcheck, cad bom
CHECKS = ("parts", "interference", "clearance", "fasteners", "service", "drop", "index", "slide", "distances", "payload",
          "sightlines", "assembly", "insertion", "stacks", "flexures", "stability", "cables", "build", "printcheck", "bom")
GROUPS = (("ALL-v1", lambda a: not a.startswith("v2")), ("ALL-v2", lambda a: a.startswith("v2")), ("ALL", lambda a: True))


# ------------------------------------------------------------------ tools commit


def git(*a: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *a], check=True, capture_output=True, text=True).stdout.strip()


def tools_for(ref: str, scratch: Path) -> tuple[Path, dict]:
    """The `cad` wrapper of `ref`: the checkout itself when ref is HEAD and skills/ is clean, else a git archive copy."""
    sha = git("rev-parse", "--short=9", ref + "^{commit}")
    head = git("rev-parse", "--short=9", "HEAD")
    info = {"ref": ref, "commit": sha, "subject": git("log", "-1", "--format=%s", sha)[:100],
            "branch": git("rev-parse", "--abbrev-ref", "HEAD") if sha == head else None,
            "skills_tree": git("rev-parse", "--short=9", sha + ":skills")}   # same tree = same tools, whatever the commit
    dirty = git("status", "--porcelain", "--", "skills") if sha == head else ""
    if sha == head and not dirty:
        return ROOT / "skills/print-cad-blender/scripts/cad", info
    if sha == head and dirty:
        info["dirty"] = True   # HEAD with uncommitted skills/ changes: run them, and say so in every row
        return ROOT / "skills/print-cad-blender/scripts/cad", info
    dest = scratch / ("tools-" + sha)
    dest.mkdir(parents=True, exist_ok=True)
    arc = subprocess.run(["git", "-C", str(ROOT), "archive", sha, "skills"], check=True, capture_output=True).stdout
    p = dest / "skills.tar"
    p.write_bytes(arc)
    with tarfile.open(p) as t:
        _extract(t, dest)
    p.unlink()
    return dest / "skills/print-cad-blender/scripts/cad", info


# ------------------------------------------------------------------ runs

def _extract(t: tarfile.TarFile, dest: Path) -> None:
    try:
        t.extractall(dest, filter="data")
    except TypeError:   # Python without extraction filters
        t.extractall(dest)


def run_attempt(name: str, spec: dict, cad: Path, scratch: Path, only_runs: set | None) -> dict:
    """Make every run of one attempt; return {run_id: {"out": path, "runtime_s", "rc", "error"}}."""
    src = ROOT / spec["dir"]
    w = scratch / name
    w.mkdir(parents=True, exist_ok=True)
    blend = w / spec["as"]
    with gzip.open(src / spec["blend"], "rb") as fi, open(blend, "wb") as fo:
        shutil.copyfileobj(fi, fo)
    for f in spec.get("copy", []):
        shutil.copy(src / f, w / f)
    res = {}
    for r in spec["runs"]:
        if only_runs and r["id"] not in only_runs:
            continue
        env = dict(os.environ, **r.get("env", {}))
        if r["type"] == "check":
            out = w / (r["id"] + ".json")
            args = [a.replace("{dir}", str(src)) for a in r.get("args", [])]
            cmd = ["sh", str(cad), "check", str(blend), str(src / r["config"]), str(out), *args]
        elif r["type"] == "printcheck":
            out = w / (r["id"] + ".json")
            stl = w / "stl_x"
            stl.mkdir(exist_ok=True)
            with tarfile.open(src / r["stl_tar"]) as t:
                _extract(t, stl)
            d = next((p.parent for p in sorted(stl.rglob("*.stl"))), stl)
            cmd = ["sh", str(cad), "printcheck", str(d), "--manifest", str(src / r["manifest"]), "--out", str(out)]
        elif r["type"] == "bom":
            out = w / (r["id"] + ".txt")
            cmd = ["sh", str(cad), "bom", str(src / r["bom"]), str(src / r["manifest"])]
        else:
            raise SystemExit("unknown run type %r" % r["type"])
        t0 = time.time()
        p = subprocess.run(cmd, env=env, capture_output=True, text=True)
        rt = round(time.time() - t0, 1)
        if r["type"] == "bom":
            out.write_text(p.stdout)
        (w / (r["id"] + ".log")).write_text(" ".join(cmd) + "\n" + p.stdout[-20000:] + p.stderr[-5000:])
        err = crash_of(r, out, p.returncode, p.stdout + "\n" + p.stderr)
        res[r["id"]] = {"out": str(out), "runtime_s": rt, "rc": p.returncode, "error": err}
        (w / (r["id"] + ".status.json")).write_text(json.dumps({"cmd": cmd, **res[r["id"]]}))
        print("  %-5s %-11s %6.1fs rc=%d%s" % (name, r["id"], rt, p.returncode, ("  ERROR " + err) if err else ""), flush=True)
    return res


def crash_of(run: dict, out: Path, rc: int | None, log: str = "") -> str | None:
    """Why a run's output can't be scored (it crashed), else None. A crash is an error, never a miss: cad check exits 1
    on fails and cad bom on BAD lines, so the exit code alone says nothing; the report must exist and parse."""
    tail = lambda: ((log or "").strip().splitlines()[-1:] or [""])[0][:200]
    if not out.exists() or out.stat().st_size == 0:
        return "no output (exit %s): %s" % (rc, tail())
    if run["type"] == "bom":
        if "Traceback (most recent call last)" in (log or ""):
            return "crashed (exit %s): %s" % (rc, tail())
        return None
    try:
        d = json.load(open(out))
    except Exception as e:
        return "unreadable report (exit %s): %s" % (rc, e)
    if run["type"] == "check" and not isinstance(d.get("summary"), dict):
        return "report has no summary (exit %s)" % rc
    if run["type"] == "printcheck" and not isinstance(d.get("parts"), list):
        return "report has no parts (exit %s)" % rc
    return None



def _status_file(p: Path) -> dict:
    s = p.with_name(p.name.rsplit(".", 1)[0] + ".status.json")
    try:
        return json.load(open(s))
    except Exception:
        return {}


def from_run(name: str, spec: dict, rdir: Path) -> dict:
    """The outputs of an earlier bench run dir (/tmp/alex3d-bench/run-<pid>): rescore after a label edit, no Blender.
    A run that crashed there is an error here too (its .status.json, else the report must exist and parse)."""
    res = {}
    for r in spec["runs"]:
        p = rdir / name / (r["id"] + (".txt" if r["type"] == "bom" else ".json"))
        st = _status_file(p)
        log = ""
        lp = p.with_suffix(".log")
        if lp.exists():
            log = lp.read_text(errors="replace")
        if not p.exists() and not st and not lp.exists():
            res[r["id"]] = {"out": None, "runtime_s": None, "rc": None, "error": "not in that run dir (not run)"}
            continue
        err = st.get("error") if st else crash_of(r, p, None, log)
        rt = st.get("runtime_s")
        if rt is None and p.suffix == ".json" and p.exists():
            try:
                rt = json.load(open(p)).get("summary", {}).get("runtime_s")
            except Exception:
                pass
        res[r["id"]] = {"out": str(p) if p.exists() else None, "runtime_s": rt, "rc": st.get("rc"), "error": err}
    return res


def from_verify(name: str, spec: dict, vdir: Path) -> dict:
    res = {}
    for r in spec["runs"]:
        vo = r.get("verify_out")
        p = vdir / vo if vo else None
        if p and p.exists():
            rt = None
            err = crash_of(r, p, None)
            if p.suffix == ".json" and not err:
                rt = json.load(open(p)).get("summary", {}).get("runtime_s")
            res[r["id"]] = {"out": str(p), "runtime_s": rt, "rc": None, "error": err}
        else:
            res[r["id"]] = {"out": None, "runtime_s": None, "rc": None,
                            "error": "not in this verify run" if vo else "bench-only run (verify_all has no such run)"}
    return res


# ------------------------------------------------------------------ locators

NUMPIN = re.compile(r"(?<![\\\w\[])\d+\\\.(?:\d|\\d)")   # 32\.\d, 8\.099, 0\.9: a measured number, not the defect
LOC_KEYS = {"check", "objects", "kind", "region", "partial"}


def top_level_alt(p: str) -> bool:
    """True when a regex has a `|` outside any group: 'a b|c' is (a b)|c, the bug the review found in four locators."""
    depth, i, cls = 0, 0, False
    while i < len(p):
        c = p[i]
        if c == "\\":
            i += 2
            continue
        if cls:
            cls = c != "]"
        elif c == "[":
            cls = True
            if p[i + 1:i + 2] == "]":
                i += 1
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "|" and depth == 0:
            return True
        i += 1
    return False


def _obj_re(o: str) -> re.Pattern:
    """An object name as a whole token; * and ? and [..] glob over a family (FST_motor_*, PRT_arm_cover_?)."""
    out, i = "", 0
    while i < len(o):
        c = o[i]
        if c == "*":
            out += r"[\w.-]*"
        elif c == "?":
            out += r"\w"
        elif c == "[" and "]" in o[i:]:
            j = o.index("]", i)
            out += o[i:j + 1]
            i = j
        else:
            out += re.escape(c)
        i += 1
    return re.compile(r"(?<![\w-])" + out + r"(?![\w-])")


_CACHE: dict = {}


def compiled(loc: dict) -> tuple:
    k = id(loc)
    if k not in _CACHE:
        _CACHE[k] = (loc, loc["check"], [_obj_re(o) for o in loc["objects"]], re.compile(loc["kind"]),
                     re.compile(loc["region"]) if loc.get("region") else None)
    return _CACHE[k][1:]


def _match(loc: dict, text: str) -> bool:
    """A report line names this defect: its check, every object, the defect kind and (if given) the region."""
    chk, objs, kind, region = compiled(loc)
    if not text.startswith(chk + ": "):
        return False
    return all(o.search(text) for o in objs) and kind.search(text) is not None and (region is None or region.search(text) is not None)


def lint(lab: dict) -> list[str]:
    """Problems with labels.json: loose locators (a bare top-level |, check '*', no object, a pinned measured number),
    bad severities, malformed print evidence. The smoke test fails on any."""
    bad = []

    def locs(where, ls, allow_none=True):
        if ls is None:
            return
        if not isinstance(ls, list) or not ls:
            bad.append("%s: locators must be a non-empty list or null" % where)
            return
        for i, l in enumerate(ls):
            w = "%s locator %d" % (where, i)
            extra = set(l) - LOC_KEYS - {"attempt", "why", "source"}
            if extra:
                bad.append("%s: unknown keys %s" % (w, sorted(extra)))
            if l.get("check") in (None, "", "*") or l.get("check") not in CHECKS:
                bad.append("%s: check %r is not one check (%s)" % (w, l.get("check"), ", ".join(CHECKS)))
            obs = l.get("objects")
            if not isinstance(obs, list) or not obs or not all(isinstance(o, str) and o.strip("*? ") for o in obs):
                bad.append("%s: no object name (objects: the parts, fasteners, cables or named rows the line must name)" % w)
            for key in ("kind", "region"):
                pat = l.get(key)
                if pat is None:
                    if key == "kind":
                        bad.append("%s: no kind regex" % w)
                    continue
                try:
                    re.compile(pat)
                except re.error as e:
                    bad.append("%s: %s does not compile: %s" % (w, key, e))
                    continue
                if top_level_alt(pat):
                    bad.append("%s: %s %r has a top-level | (group the alternatives)" % (w, key, pat))
            if l.get("kind") and NUMPIN.search(l["kind"]):
                bad.append("%s: kind %r pins a measured number (match the defect; put a location in region)" % (w, l["kind"]))
            for o in obs or []:
                if isinstance(o, str) and "|" in o:
                    bad.append("%s: object %r has a |" % (w, o))

    seen = set()
    for l in lab.get("labels", []):
        w = "label %s/%s" % (l.get("attempt"), l.get("id"))
        if (l.get("attempt"), l.get("id")) in seen:
            bad.append("%s: duplicate" % w)
        seen.add((l.get("attempt"), l.get("id")))
        if l.get("severity") not in SEV_W:
            bad.append("%s: severity %r" % (w, l.get("severity")))
        if l.get("credit_scope") not in (None, "rows"):
            bad.append("%s: credit_scope %r (only 'rows')" % (w, l.get("credit_scope")))
        locs(w, l.get("locators"))
    for f in lab.get("printability", []):
        w = "printability %s" % f.get("id")
        if not f.get("attempts"):
            bad.append("%s: no attempts" % w)
        if f.get("severity") not in SEV_W:
            bad.append("%s: severity %r" % (w, f.get("severity")))
        locs(w, f.get("locators"), allow_none=False)
        ev = f.get("print_evidence")
        if f.get("confirmed_by") and not ev:
            bad.append("%s: confirmed_by without print_evidence" % w)
        for i, e in enumerate(ev or []):
            miss = [k for k in ("date", "by", "printed", "result", "observed") if not e.get(k)]
            if miss or e.get("result") not in ("fail", "pass", "partial") or not re.match(r"\d{4}-\d\d-\d\d$", str(e.get("date"))):
                bad.append("%s print_evidence %d: needs date YYYY-MM-DD, by, printed, result fail|pass|partial, observed" % (w, i))
    for i, k in enumerate(lab.get("known_true_positives", [])):
        locs("known_true_positive %d (%s)" % (i, k.get("attempt")), [k])
    return bad


# ------------------------------------------------------------------ scoring

def items_of(run: dict, out: str) -> list[tuple[str, str]]:
    """(status, text) for every fail / warn / accepted warn a run reported. Text is 'check: message'."""
    p = Path(out)
    if run["type"] == "bom":
        txt = p.read_text()
        return [("fail", "bom: " + l.strip()) for l in txt.splitlines() if l.startswith("BAD")] + \
               [("warn", "bom: " + l.strip()) for l in txt.splitlines() if l.startswith("NOT IN BOM")]
    d = json.load(open(p))
    if run["type"] == "printcheck":
        return [(f["status"], "printcheck: %s: %s" % (r["stl"], f["msg"])) for r in d.get("parts", [])
                for f in r.get("findings", []) if f.get("status") in ("fail", "warn")]
    s = d.get("summary", {})
    acc = s.get("accepted_warns") or {}
    return ([("fail", x) for x in s.get("fail_list", [])] + [("warn", x) for x in s.get("warn_list", [])]
            + [("accepted", x) for x in (acc if isinstance(acc, (dict, list)) else [])])


def run_checks(run: dict) -> set:
    """The checks a run can report: printcheck / bom, or cadcheck's (its --only set when given)."""
    if run["type"] in ("printcheck", "bom"):
        return {run["type"]}
    a = run.get("args", [])
    if "--only" in a:
        return set(a[a.index("--only") + 1].split(",")) | {"build"}
    return set(CHECKS) - {"printcheck", "bom"}


def judge(entry: dict, scope: str, its: dict, err_checks: set) -> dict:
    """Best status of one label / finding in one scope, and the line that credited it.
    fail > warn > accepted from full locators; else 'partial' if only a partial locator matched; else 'error' if a
    locator's check came from a run that crashed; else None (missed)."""
    if scope == "designer" and entry.get("credit_scope") == "rows":
        return {"status": None, "note": "rows scope only"}
    best, line, part = None, None, None
    for loc in entry.get("locators") or []:
        for tx, (st, rid) in its.items():
            if not _match(loc, tx):
                continue
            if loc.get("partial"):
                part = part or (tx, rid)
            elif STATUS_RANK[st] > STATUS_RANK[best]:
                best, line = st, (tx, rid)
    if best:
        return {"status": best, "line": line[0], "run": line[1]}
    if part:
        return {"status": "partial", "line": part[0], "run": part[1]}
    if any(loc["check"] in err_checks for loc in entry.get("locators") or []):
        return {"status": "error"}
    return {"status": None}


def score(name: str, spec: dict, labels: list, known: list, runs: dict, pf: list | None = None) -> dict:
    kinds = {r["id"]: r["kind"] for r in spec["runs"]}
    types = {r["id"]: r for r in spec["runs"]}
    items = {"designer": {}, "rows": {}}      # scope -> text -> (best status, run id)
    errors, err_checks = {}, {"designer": set(), "rows": set()}
    for rid, rr in runs.items():
        scopes = ("designer", "rows") if kinds[rid] == "designer" else ("rows",)
        err = rr.get("error") or (None if rr.get("out") else "no output")
        its = []
        if not err:
            try:
                its = items_of(types[rid], rr["out"])
            except Exception as e:  # an older commit's report without a field
                err = "unreadable report: %s" % e
        if err:
            if not err.startswith(("bench-only run", "not in that run dir (not run)")):
                errors[rid] = err
                for sc in scopes:
                    err_checks[sc] |= run_checks(types[rid])
            continue
        for st, tx in its:
            for sc in scopes:
                cur = items[sc].get(tx)
                if cur is None or STATUS_RANK[st] > STATUS_RANK[cur[0]]:
                    items[sc][tx] = (st, rid)
    pf = [f for f in (pf or []) if name in f.get("attempts", [])]
    counted = [l for l in labels if not l.get("process")]
    row = {"attempt": name, "group": "v2" if name.startswith("v2") else "v1", "labels": len(counted),
           "labels_excluded": [l["id"] for l in labels if l.get("process")],
           "labels_tool_catchable": sum(1 for l in counted if l.get("tool_catchable")),
           "weight": sum(SEV_W[l["severity"]] for l in counted), "per_label": {}, "pf": {}, "errors": errors}
    every_loc = [loc for l in labels for loc in (l.get("locators") or [])] + [loc for f in pf for loc in f["locators"]]
    for scope in ("designer", "rows"):
        its = items[scope]
        sfx = "" if scope == "designer" else "_rows"
        J = {}
        for l in labels:
            j = judge(l, scope, its, err_checks[scope])
            J[l["id"]] = j
            pl = row["per_label"].setdefault(l["id"], {})
            pl[scope] = j["status"]
            if j.get("line"):
                pl[scope + "_line"] = j["line"][:300]
                pl[scope + "_run"] = j["run"]
            if j.get("note"):
                pl["note"] = j["note"]
        for f in pf:
            j = judge(f, scope, its, err_checks[scope])
            e = row["pf"].setdefault(f["id"], {})
            e[scope] = j["status"]
            if j.get("line"):
                e[scope + "_line"] = j["line"][:300]
        st = {l["id"]: J[l["id"]]["status"] for l in counted}
        sev = {l["id"]: SEV_W[l["severity"]] for l in counted}
        tc = [l["id"] for l in counted if l.get("tool_catchable")]
        n, W = len(counted) or 1, row["weight"] or 1
        fails = [tx for tx, (s, _) in its.items() if s == "fail"]
        excused = {}
        for tx in fails:
            who = [l["id"] for l in labels for loc in (l.get("locators") or []) if _match(loc, tx)] + \
                  [f["id"] for f in pf for loc in f["locators"] if _match(loc, tx)] + \
                  ["known:" + k["kind"] for k in known if _match(k, tx)]
            if who:
                excused[tx] = sorted(set(who))
        false = [tx for tx in fails if tx not in excused]
        warns = [tx for tx, (s, _) in its.items() if s == "warn"]
        hit = [tx for tx in warns if any(_match(loc, tx) for loc in every_loc) or any(_match(k, tx) for k in known)]
        pfs = [row["pf"][f["id"]][scope] for f in pf]
        row.update({
            "caught_fail" + sfx: sum(1 for v in st.values() if v == "fail"),
            "caught_fw" + sfx: sum(1 for v in st.values() if v in CAUGHT_FW),
            "caught_accepted_only" + sfx: sum(1 for v in st.values() if v == "accepted"),
            "caught_partial" + sfx: sum(1 for v in st.values() if v == "partial"),
            "label_errors" + sfx: sum(1 for v in st.values() if v == "error"),
            "caught_fw_catchable" + sfx: sum(1 for i in tc if st[i] in CAUGHT_FW),
            "w_fail" + sfx: sum(sev[i] for i, v in st.items() if v == "fail"),
            "w_fw" + sfx: sum(sev[i] for i, v in st.items() if v in CAUGHT_FW),
            "fails" + sfx: len(fails), "false_fails" + sfx: len(false),
            "excused_fails" + sfx: {k: v for k, v in list(excused.items())[:60]},
            "known_tp_fails" + sfx: sum(1 for v in excused.values() if all(x.startswith("known:") for x in v)),
            "false_fail_list" + sfx: false[:40],
            "warns_untriaged" + sfx: len(warns), "warns_accepted" + sfx: sum(1 for s, _ in its.values() if s == "accepted"),
            "noise_warns" + sfx: len(warns) - len(hit), "hit_warns" + sfx: len(hit),
            "noise_warn_list" + sfx: [w for w in warns if w not in hit][:60],
            "pf_findings": len(pf),
            "pf_fail" + sfx: sum(1 for v in pfs if v == "fail"), "pf_fw" + sfx: sum(1 for v in pfs if v in CAUGHT_FW),
        })
        row.update(_rates(row, sfx, n, W, len(tc)))
    rts = [rr["runtime_s"] for rr in runs.values() if rr.get("runtime_s") is not None]
    row["runtime_s"] = round(sum(rts), 1) if rts else None   # information only
    row["runtime_by_run"] = {k: v.get("runtime_s") for k, v in runs.items()}
    return row


def _rates(r: dict, sfx: str, n: int, W: int, ntc: int) -> dict:
    w = r["warns_untriaged" + sfx]
    return {"recall_fail" + sfx: round(r["caught_fail" + sfx] / n, 3), "recall_fw" + sfx: round(r["caught_fw" + sfx] / n, 3),
            "recall_fail_w" + sfx: round(r["w_fail" + sfx] / W, 3), "recall_fw_w" + sfx: round(r["w_fw" + sfx] / W, 3),
            "recall_fw_catchable" + sfx: round(r["caught_fw_catchable" + sfx] / (ntc or 1), 3),
            "hit_share" + sfx: round(r["hit_warns" + sfx] / w, 3) if w else None}


PF_WORST = {"error": -1, None: 0, "partial": 0.5, "accepted": 1, "warn": 2, "fail": 3}


def summary_row(rows: list[dict], name: str, pf: list | None = None) -> dict:
    """Sums over the attempts; printability once per finding (its worst status over the attempts it is on)."""
    s = {"attempt": name, "attempts": [r["attempt"] for r in rows]}
    keys = [k for k in rows[0] if isinstance(rows[0][k], int) and not isinstance(rows[0][k], bool)
            and k not in ("pf_findings", "pf_fail", "pf_fw", "pf_fail_rows", "pf_fw_rows")] if rows else []
    for k in keys:
        s[k] = sum(r.get(k, 0) for r in rows)
    s["errors"] = sum(len(r["errors"]) for r in rows)
    s["labels_excluded"] = [i for r in rows for i in r.get("labels_excluded", [])]
    for sfx in ("", "_rows"):
        s.update(_rates(s, sfx, s.get("labels") or 1, s.get("weight") or 1, s.get("labels_tool_catchable") or 0))
    s["noise_warns_per_attempt"] = round(s.get("noise_warns", 0) / (len(rows) or 1), 1)
    fin = {}
    for r in rows:
        for fid, e in r.get("pf", {}).items():
            for sc in ("designer", "rows"):
                cur = fin.setdefault(fid, {}).get(sc, "unset")
                if cur == "unset" or PF_WORST[e.get(sc)] < PF_WORST[cur]:
                    fin[fid][sc] = e.get(sc)
    conf = {f["id"] for f in (pf or []) if f.get("confirmed_by")}
    s["pf"] = fin
    s["pf_findings"] = len(fin)
    for sc, sfx in (("designer", ""), ("rows", "_rows")):
        s["pf_fail" + sfx] = sum(1 for e in fin.values() if e.get(sc) == "fail")
        s["pf_fw" + sfx] = sum(1 for e in fin.values() if e.get(sc) in CAUGHT_FW)
    s["pf_confirmed"] = sorted(f for f in fin if f in conf)
    s["pf_confirmed_fail"] = sum(1 for f in fin if f in conf and fin[f].get("designer") == "fail")
    s["runtime_s"] = round(sum(r["runtime_s"] or 0 for r in rows), 1)   # information only
    return s


# ------------------------------------------------------------------ table / compare

def _pct(a, b):
    return "%d/%d" % (a, b)


def table(results: Path, commit: str | None, out=sys.stdout) -> None:
    rows = [json.loads(l) for l in open(results) if l.strip()]
    if commit:
        rows = [r for r in rows if r["commit"].startswith(commit) or r.get("ref") == commit]
    rows = [r for r in rows if "group" in r or r["attempt"].startswith("ALL")]
    shas = list(dict.fromkeys(r.get("labels_file_sha") for r in rows))
    if len(shas) > 1:
        print("**WARNING: these rows were scored against %d different labels files (%s). Rows under different labels "
              "are not comparable; rescore the older run (--from-run) with the current labels.**\n" % (len(shas), ", ".join(map(str, shas))), file=out)
    for sha in shas:
        R = [r for r in rows if r.get("labels_file_sha") == sha]
        print("labels %s; fail / fail+warn of reviewer labels (sev-w: severity-weighted, blocker 3 major 2 minor 1); "
              "PF: printability findings failed, once per finding" % sha, file=out)
        print("| commit | attempt | runs | errors | labels (catchable) | fail | f+w | partial | sev-w fail | sev-w f+w | +rows fail | +rows f+w "
              "| false fails (rows) | noise warns | hit share | PF fail |", file=out)
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|", file=out)
        for r in R:
            if "recall_fail_w" not in r:
                continue
            hs = r.get("hit_share")
            print("| %s%s | %s | %s | %s | %d (%d) | %d | %d | %d | %.0f%% | %.0f%% | %d | %d | %d (%d) | %d | %s | %s |" % (
                r["commit"][:7], "*" if r.get("dirty") else "", r["attempt"], ",".join(r.get("runs_subset") or []) or "all",
                (r["errors"] if isinstance(r["errors"], int) else len(r["errors"])) or "-", r["labels"], r["labels_tool_catchable"],
                r["caught_fail"], r["caught_fw"], r.get("caught_partial", 0), 100 * r["recall_fail_w"], 100 * r["recall_fw_w"],
                r["caught_fail_rows"], r["caught_fw_rows"], r["false_fails"], r["false_fails_rows"], r["noise_warns"],
                "-" if hs is None else "%.0f%%" % (100 * hs), _pct(r.get("pf_fail", 0), r.get("pf_findings", 0))), file=out)
        print("", file=out)


GATE = (("recall_fail", 1), ("recall_fw", 1), ("recall_fail_w", 1), ("recall_fw_w", 1), ("recall_fw_rows", 1),
        ("pf_fail", 1), ("false_fails", -1), ("false_fails_rows", -1), ("noise_warns", -1))


def compare(results: Path, base: str, new: str, out=sys.stdout) -> int:
    """Gate a change: the latest row of each commit per attempt; refuse different labels, errors or run subsets."""
    rows = [json.loads(l) for l in open(results) if l.strip()]

    def latest(c):
        got = {}
        for r in rows:
            if (r["commit"].startswith(c) or r.get("ref") == c) and "recall_fail_w" in r:
                got[r["attempt"]] = r
        return got
    A, B = latest(base), latest(new)
    if not A or not B:
        print("compare: no rows for %s" % (base if not A else new), file=out)
        return 2
    why = []
    sa, sb = {r.get("labels_file_sha") for r in A.values()}, {r.get("labels_file_sha") for r in B.values()}
    if sa != sb or len(sa) != 1:
        why.append("labels differ (%s vs %s): rescore one run with --from-run" % (sorted(map(str, sa)), sorted(map(str, sb))))
    common = [a for a in A if a in B and (not a.startswith("ALL") or A[a].get("attempts") == B[a].get("attempts"))]
    if not [a for a in common if not a.startswith("ALL")]:
        why.append("no attempt in common")
    for nm, R in ((base, A), (new, B)):
        e = {a: R[a]["errors"] for a in common if not a.startswith("ALL") and R[a]["errors"]}
        if e:
            why.append("%s has run errors: %s" % (nm, e))
    if any(A[a].get("runs_subset") != B[a].get("runs_subset") for a in common):
        why.append("run subsets differ")
    if why:
        print("REFUSED: " + "; ".join(why), file=out)
        return 2
    worse = []
    print("| attempt | " + " | ".join(k for k, _ in GATE) + " |\n|---|" + "---|" * len(GATE), file=out)
    if set(A) != set(B):
        print("(attempts in common only: %s)\n" % ", ".join(common), file=out)
    for a in common:
        cells = []
        for k, sign in GATE:
            x, y = A[a].get(k), B[a].get(k)
            if x is None or y is None:
                cells.append("-")
                continue
            cells.append("%s -> %s" % (x, y) if x != y else str(y))
            if (y - x) * sign < 0:
                worse.append("%s %s %s -> %s" % (a, k, x, y))
        print("| %s | %s |" % (a, " | ".join(cells)), file=out)
    print("\nworse: " + ("; ".join(worse) if worse else "nothing (recall not down, false fails and noise not up)"), file=out)
    return 1 if worse else 0


# ------------------------------------------------------------------ verify_all cross-check (report only)

def verify_literals(path: Path) -> dict:
    """{attempt: [literal]}: the strings verify_all's per-attempt sections (4 .. 4k) assert on report lines (`for pat
    in "..."` lists, `grep -q "..."`, and Python `'...' in f` tests), and the layer-check loop's parts (4n)."""
    import shlex
    txt = path.read_text()
    out: dict = {}
    sec = None
    lines = txt.replace("\\\n", " ").splitlines()   # join continuation lines
    for line in lines:
        m = re.match(r"^# (4[a-z]?) (?:(v2) )?attempt-(\d)", line)
        if m:
            sec = ("v2a" if m.group(2) else "a") + m.group(3)
            continue
        if re.match(r"^# \d", line):
            sec = None
        if not sec:
            continue
        lits = []
        fp = re.search(r"\bfor pat in (.*?); do\b", line)
        if fp:
            try:
                lits += shlex.split(fp.group(1))
            except ValueError:
                pass
        lits += re.findall(r'grep -qF? "([^"$]+)"', line)
        lits += [x.replace('\\"', '"') for x in re.findall(r"'([^']{6,}?)'\s+in\s+(?:f|w|w\[0\])\b", line)]
        lits += re.findall(r'\\"([^"\\]{6,}?)\\"\s+in\s+(?:f|w|w\[0\])\b', line)
        lits += re.findall(r"'([^']{6,}?)'\s+in\s+x\s+for x in\b", line)   # sum('...' in x for x in w): a count, not a filter
        for grp in re.findall(r"for k in \(([^)]*)\)", line):
            lits += [a or b for a, b in re.findall(r"'([^']+)'|\\\"([^\\]+)\\\"", grp)]
        for fmt, vals in re.findall(r"'([^']*%s[^']*)' % v\b.*?for v in \(([^)]*)\)", line):   # '%s mm (...)' % v for v in (..)
            lits += [fmt % v for v in re.findall(r"'([^']*)'", vals)]
        out.setdefault(sec, []).extend(x for x in lits if "%" not in x and len(x) >= 6)
    m = re.search(r'for spec in (.*?); do', txt.replace("\\\n", " "), re.S)
    if m:
        v2want = re.search(r'want="(PRT_base_shell=[^"]+)"', txt)
        for spec in re.findall(r'"([^"]+)"', m.group(1)):
            att, _, want = spec.split(":")
            want = v2want.group(1) if want == "V2" and v2want else want
            for w in want.split(","):
                out.setdefault(att, []).append("parts: %s (" % w.split("=")[0])
    return out


def xcheck(lab: dict, corpus: dict, runs_by_att: dict, verify: Path, out=sys.stdout) -> dict:
    lits = verify_literals(verify)
    res = {"labels_without_assertion": [], "assertions_without_label": [], "assertions_not_in_reports": []}
    for att, spec in corpus.items():
        lines = []
        for r in spec["runs"]:
            rr = runs_by_att.get(att, {}).get(r["id"], {})
            if rr.get("out") and not rr.get("error"):
                try:
                    lines += [tx for _, tx in items_of(r, rr["out"])]
                except Exception:
                    pass
        L = [l for l in lab["labels"] if l["attempt"] == att and l.get("locators")]
        P = [f for f in lab.get("printability", []) if att in f["attempts"]]
        K = [k for k in lab.get("known_true_positives", []) if k["attempt"] == att]
        asserted = set()
        for s in lits.get(att, []):
            hit = [tx for tx in lines if s in tx]
            if not hit:
                res["assertions_not_in_reports"].append((att, s))
                continue
            who = {e["id"] for e in L + P for loc in e["locators"] for tx in hit if _match(loc, tx)}
            if not who and not any(_match(k, tx) for k in K for tx in hit):
                res["assertions_without_label"].append((att, s))
            asserted |= who
        for e in L + P:
            if e["id"] not in asserted and any(_match(loc, tx) for loc in e["locators"] for tx in lines):
                res["labels_without_assertion"].append((att, e["id"]))
    print("verify_all vs labels.json (report only; the two lists are kept by hand)", file=out)
    print("- labels / findings these reports credit but no verify_all assertion pins (%d): %s" % (
        len(res["labels_without_assertion"]), ", ".join("%s %s" % x for x in res["labels_without_assertion"])), file=out)
    print("- verify_all assertions whose report lines match no label, finding or known true positive (%d):" % len(res["assertions_without_label"]), file=out)
    for a, s in res["assertions_without_label"]:
        print("    %s: %s" % (a, s[:110]), file=out)
    print("- verify_all literals not found in these reports (other runs, cad q output, or not a report line) (%d)" % len(res["assertions_not_in_reports"]), file=out)
    return res


# ------------------------------------------------------------------ main

def _verify_meta(vdir: Path, assume: str | None) -> dict:
    m = vdir / "meta.json"
    if m.exists():
        d = json.load(open(m))
        c = d.get("commit") or ""
        return {"commit": c[:9], "skills_tree": (d.get("skills_tree") or "")[:9] or None, "dirty": bool(d.get("dirty")) or None,
                "subject": None, "branch": d.get("branch")}
    if assume:
        return {"commit": git("rev-parse", "--short=9", assume + "^{commit}"), "skills_tree": git("rev-parse", "--short=9", assume + ":skills"),
                "subject": None, "branch": None, "commit_assumed": True}
    raise SystemExit("%s has no meta.json (verify_all writes it from this change on): can't tell which commit made these "
                     "reports. Pass --assume-commit SHA if you know it." % vdir)


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    sub = argv[:1]
    if sub in (["table"], ["compare"]):
        p = argparse.ArgumentParser(prog="replay.py " + sub[0])
        p.add_argument("--results", default=str(BENCH / "results/replay.jsonl"))
        if sub == ["table"]:
            p.add_argument("--commit")
        else:
            p.add_argument("base")
            p.add_argument("new")
        a = p.parse_args(argv[1:])
        if sub == ["table"]:
            table(Path(a.results), a.commit)
            return 0
        return compare(Path(a.results), a.base, a.new)
    if sub == ["lint"]:
        p = argparse.ArgumentParser(prog="replay.py lint")
        p.add_argument("--labels", default=str(BENCH / "labels.json"))
        a = p.parse_args(argv[1:])
        bad = lint(json.load(open(a.labels)))
        for b in bad:
            print("LINT " + b)
        print("lint: %d problems in %s" % (len(bad), a.labels))
        return 1 if bad else 0
    if sub == ["xcheck"]:
        p = argparse.ArgumentParser(prog="replay.py xcheck")
        p.add_argument("--from-run")
        p.add_argument("--from-verify")
        p.add_argument("--labels", default=str(BENCH / "labels.json"))
        p.add_argument("--corpus", default=str(BENCH / "corpus.json"))
        p.add_argument("--verify-script", default=str(ROOT / "tools/verify_all.sh"))
        a = p.parse_args(argv[1:])
        corpus = json.load(open(a.corpus))["attempts"]
        if not (a.from_run or a.from_verify):
            raise SystemExit("xcheck needs --from-run or --from-verify (the report lines to match)")
        d = Path(a.from_run or a.from_verify).resolve()
        runs = {n: (from_run if a.from_run else from_verify)(n, s, d) for n, s in corpus.items()}
        xcheck(json.load(open(a.labels)), corpus, runs, Path(a.verify_script))
        return 0
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--commit", default="HEAD", help="tools commit (its skills/ is used; corpus, labels and blends come from this checkout)")
    p.add_argument("--attempts", help="comma list (a1,a2,a3,v2a1..v2a7); default all")
    p.add_argument("--runs", help="comma list of run ids to make (designer,layer,...); default all")
    p.add_argument("--from-verify", help="score a verify_all run dir (run-<pid>, with its meta.json) instead of running cad")
    p.add_argument("--assume-commit", help="with --from-verify on a dir with no meta.json: the commit that made it")
    p.add_argument("--from-run", help="rescore an earlier bench scratch dir (run-<pid>) instead of running cad")
    p.add_argument("--labels", default=str(BENCH / "labels.json"))
    p.add_argument("--corpus", default=str(BENCH / "corpus.json"))
    p.add_argument("--results", default=str(BENCH / "results/replay.jsonl"), help="JSONL file the rows are appended to")
    p.add_argument("--no-append", action="store_true", help="print rows, append nothing")
    p.add_argument("-j", type=int, default=1, help="attempts in parallel")
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args(argv)

    corpus = json.load(open(a.corpus))["attempts"]
    lab = json.load(open(a.labels))
    problems = lint(lab)
    if problems:
        raise SystemExit("labels.json fails the locator lint (replay.py lint):\n  " + "\n  ".join(problems))
    names = a.attempts.split(",") if a.attempts else list(corpus)
    bad = [n for n in names if n not in corpus]
    if bad:
        raise SystemExit("unknown attempts: %s" % bad)
    only_runs = set(a.runs.split(",")) if a.runs else None

    scratch = SCRATCH_BASE / ("run-%d" % os.getpid())
    if a.from_verify:
        vdir = Path(a.from_verify).resolve()
        info = {"ref": "verify:" + str(vdir), "from_verify": str(vdir), **_verify_meta(vdir, a.assume_commit)}
        runs = {n: from_verify(n, corpus[n], vdir) for n in names}
    elif a.from_run:
        rdir = Path(a.from_run).resolve()
        if not (rdir / "bench_meta.json").exists():
            raise SystemExit("%s has no bench_meta.json: can't tell which commit made those reports" % rdir)
        info = {"ref": "run:" + str(rdir), "from_run": str(rdir), "subject": None, "branch": None}
        info.update({k: v for k, v in json.load(open(rdir / "bench_meta.json")).items() if k in ("commit", "subject", "dirty", "skills_tree", "ref")})
        info["ref"] = "run:%s (%s)" % (rdir.name, info.get("ref"))
        runs = {n: from_run(n, corpus[n], rdir) for n in names}
    else:
        shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True)
        cad, info = tools_for(a.commit, scratch)
        print("bench: tools %s (%s) -> %s" % (info["commit"], info["ref"], scratch), flush=True)
        (scratch / "bench_meta.json").write_text(json.dumps(info))
        with cf.ThreadPoolExecutor(max_workers=max(1, a.j)) as ex:
            futs = {n: ex.submit(run_attempt, n, corpus[n], cad, scratch, only_runs) for n in names}
            runs = {n: f.result() for n, f in futs.items()}
    if only_runs:
        runs = {n: {k: v for k, v in rs.items() if k in only_runs} for n, rs in runs.items()}
    when = dt.datetime.now().isoformat(timespec="seconds")
    rows = []
    for n in names:
        L = [l for l in lab["labels"] if l["attempt"] == n]
        K = [k for k in lab.get("known_true_positives", []) if k["attempt"] == n]
        r = score(n, corpus[n], L, K, runs[n], lab.get("printability", []))
        if only_runs:
            r["runs_subset"] = sorted(only_runs)
        rows.append(r)
    sums = []
    for g, keep in GROUPS:
        sel = [r for r in rows if keep(r["attempt"])]
        if sel and (g != "ALL" or len({r["group"] for r in rows}) > 1):
            sr = summary_row(sel, g, lab.get("printability", []))
            if only_runs:
                sr["runs_subset"] = sorted(only_runs)
            sums.append(sr)
    meta = {"when": when, **info, "labels_file_sha": _sha(Path(a.labels)), "scratch": None if (a.from_verify or a.from_run) else str(scratch)}
    out_rows = [{**meta, **r} for r in rows + sums]
    if not a.no_append:
        Path(a.results).parent.mkdir(parents=True, exist_ok=True)
        with open(a.results, "a") as f:
            for r in out_rows:
                f.write(json.dumps(r) + "\n")
    if not a.quiet:
        for r in out_rows:
            print("%-6s labels %2d  fail %2d  f+w %2d  partial %d  sev-w %3.0f%%/%3.0f%% | +rows fail %2d f+w %2d | false fails %d (rows %d)  "
                  "noise warns %3d  hit share %s  PF fail %d/%d%s" % (
                      r["attempt"], r["labels"], r["caught_fail"], r["caught_fw"], r.get("caught_partial", 0), 100 * r["recall_fail_w"],
                      100 * r["recall_fw_w"], r["caught_fail_rows"], r["caught_fw_rows"], r["false_fails"], r["false_fails_rows"],
                      r["noise_warns"], "-" if r["hit_share"] is None else "%.2f" % r["hit_share"], r.get("pf_fail", 0), r.get("pf_findings", 0),
                      ("  errors: %s" % r["errors"]) if r["errors"] else ""))
    for s in sums:
        print("BENCH %s recall_fail %.3f recall_fw %.3f (sev-w %.3f / %.3f) recall_fw_rows %.3f false_fails %d noise_warns %d "
              "hit_share %s PF fail %d/%d errors %d" % (
                  s["attempt"], s["recall_fail"], s["recall_fw"], s["recall_fail_w"], s["recall_fw_w"], s["recall_fw_rows"], s["false_fails"],
                  s["noise_warns"], "-" if s["hit_share"] is None else "%.3f" % s["hit_share"], s["pf_fail"], s["pf_findings"], s["errors"]))
    print("-> %s" % ("(not appended)" if a.no_append else a.results))
    return 0


def _sha(p: Path) -> str:
    import hashlib
    return hashlib.sha1(p.read_bytes()).hexdigest()[:10]


if __name__ == "__main__":
    sys.exit(main())
