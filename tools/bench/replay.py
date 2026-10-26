#!/usr/bin/env python3
"""Replay bench: score a tools commit against what the reviewers found on the 10 archived designs.

No LLM. For each archived attempt (tools/bench/corpus.json) it makes the cad runs tools/verify_all.sh makes (same
configs, overlays, --only sets, CAD_LAYER_CHECK), with the `cad` of the chosen commit, and scores the reports against
tools/bench/labels.json (the issues each reviewer raised, plus the 4 v2 post-freeze support misses):

  recall_fail   labelled issues some run reports as a fail
  recall_fw     ... as a fail or a warn (accepted warns count: the tool said it, the config dismissed it)
  false_fails   fails that match no label and no known true positive
  warn_load     untriaged warns per labelled issue (what a designer has to triage)
  runtime_s     wall time of the cad runs

Each is given twice: "designer" scope (the designer's own config plus the always-on tools: layer check, printcheck,
cad bom) and "rows" scope (also the reviewer's rows as overlays). One JSON row per (commit, attempt) and one summary
row are appended to the results file, so commits can be compared (`replay.py table`).

  python3 -I tools/bench/replay.py                         # HEAD's tools, all 10 attempts, about 15 min
  python3 -I tools/bench/replay.py --commit origin/next    # another commit's skills/ (git archive into the scratch dir)
  python3 -I tools/bench/replay.py --attempts v2a6,v2a7 -j 2
  python3 -I tools/bench/replay.py --from-verify /tmp/alex3d-verify/latest   # score a verify_all run, no Blender
  python3 -I tools/bench/replay.py table [--results F]     # one line per (commit, attempt) from the results file

Scratch: /tmp/alex3d-bench/run-<pid> (latest: /tmp/alex3d-bench/latest), as verify_all does under /tmp/alex3d-verify.
Plain python3, standard library; it never runs a slicer.
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
        err = None
        if not out.exists() or out.stat().st_size == 0:
            err = "no output (exit %d): %s" % (p.returncode, (p.stderr or p.stdout).strip().splitlines()[-1:] or "")
        res[r["id"]] = {"out": str(out), "runtime_s": rt, "rc": p.returncode, "error": err}
        print("  %-5s %-11s %6.1fs rc=%d%s" % (name, r["id"], rt, p.returncode, ("  ERROR " + err) if err else ""), flush=True)
    return res


def from_run(name: str, spec: dict, rdir: Path) -> dict:
    """The outputs of an earlier bench run dir (/tmp/alex3d-bench/run-<pid>): rescore after a label edit, no Blender."""
    res = {}
    for r in spec["runs"]:
        p = rdir / name / (r["id"] + (".txt" if r["type"] == "bom" else ".json"))
        rt = None
        if p.suffix == ".json" and p.exists():
            try:
                rt = json.load(open(p)).get("summary", {}).get("runtime_s")
            except Exception:
                pass
        res[r["id"]] = {"out": str(p) if p.exists() else None, "runtime_s": rt, "rc": None,
                        "error": None if p.exists() else "not in that run dir"}
    return res


def from_verify(name: str, spec: dict, vdir: Path) -> dict:
    res = {}
    for r in spec["runs"]:
        vo = r.get("verify_out")
        p = vdir / vo if vo else None
        if p and p.exists():
            rt = None
            if p.suffix == ".json":
                try:
                    rt = json.load(open(p)).get("summary", {}).get("runtime_s")
                except Exception:
                    pass
            res[r["id"]] = {"out": str(p), "runtime_s": rt, "rc": None, "error": None}
        else:
            res[r["id"]] = {"out": None, "runtime_s": None, "rc": None,
                            "error": "not in this verify run" if vo else "bench-only run (verify_all has no such run)"}
    return res


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


def _match(loc: dict, text: str) -> bool:
    chk = loc.get("check")
    if chk and chk != "*" and not text.startswith(chk + ": "):
        return False
    return re.search(loc["match"], text) is not None


def score(name: str, spec: dict, labels: list, known: list, runs: dict) -> dict:
    kinds = {r["id"]: r["kind"] for r in spec["runs"]}
    types = {r["id"]: r for r in spec["runs"]}
    items = {"designer": {}, "rows": {}}      # scope -> text -> best status
    errors = {}
    for rid, rr in runs.items():
        if rr.get("error") or not rr.get("out"):
            errors[rid] = rr.get("error") or "no output"
            continue
        try:
            its = items_of(types[rid], rr["out"])
        except Exception as e:  # an older commit's report without a field
            errors[rid] = "unreadable report: %s" % e
            continue
        for st, tx in its:
            for scope in (("designer", "rows") if kinds[rid] == "designer" else ("rows",)):
                cur = items[scope].get(tx)
                if STATUS_RANK[st] > STATUS_RANK[cur]:
                    items[scope][tx] = st
    row = {"attempt": name, "labels": len(labels),
           "labels_tool_catchable": sum(1 for l in labels if l.get("tool_catchable")),
           "per_label": {}, "errors": errors}
    for scope in ("designer", "rows"):
        its = items[scope]
        caught = {}
        for l in labels:
            best = None
            for loc in l.get("locators") or []:
                for tx, st in its.items():
                    if _match(loc, tx) and STATUS_RANK[st] > STATUS_RANK[best]:
                        best = st
            caught[l["id"]] = best
            row["per_label"].setdefault(l["id"], {})[scope] = best
        nf = sum(1 for v in caught.values() if v == "fail")
        nfw = sum(1 for v in caught.values() if v in ("fail", "warn", "accepted"))
        tc = [l["id"] for l in labels if l.get("tool_catchable")]
        nfw_tc = sum(1 for i in tc if caught[i] in ("fail", "warn", "accepted"))
        fails = [tx for tx, st in its.items() if st == "fail"]
        lab_locs = [loc for l in labels for loc in (l.get("locators") or [])]
        unl = [tx for tx in fails if not any(_match(loc, tx) for loc in lab_locs)]
        ktp = [tx for tx in unl if any(_match(k, tx) for k in known)]
        false = [tx for tx in unl if tx not in ktp]
        warns = [tx for tx, st in its.items() if st == "warn"]
        sfx = "" if scope == "designer" else "_rows"
        n = len(labels) or 1
        row.update({
            "caught_fail" + sfx: nf, "caught_fw" + sfx: nfw, "caught_fw_catchable" + sfx: nfw_tc,
            "recall_fw_catchable" + sfx: round(nfw_tc / (len(tc) or 1), 3),
            "caught_accepted_only" + sfx: sum(1 for v in caught.values() if v == "accepted"),
            "recall_fail" + sfx: round(nf / n, 3), "recall_fw" + sfx: round(nfw / n, 3),
            "fails" + sfx: len(fails), "false_fails" + sfx: len(false), "known_tp_fails" + sfx: len(ktp),
            "warns_untriaged" + sfx: len(warns), "warns_accepted" + sfx: sum(1 for st in its.values() if st == "accepted"),
            "warn_load" + sfx: round(len(warns) / n, 2),
            "false_fail_list" + sfx: false[:40],
        })
    rts = [rr["runtime_s"] for rr in runs.values() if rr.get("runtime_s") is not None]
    row["runtime_s"] = round(sum(rts), 1) if rts else None
    row["runtime_by_run"] = {k: v.get("runtime_s") for k, v in runs.items()}
    return row


def summary_row(rows: list[dict]) -> dict:
    s = {"attempt": "ALL", "attempts": [r["attempt"] for r in rows]}
    for k in ("labels", "labels_tool_catchable", "caught_fail", "caught_fw", "caught_accepted_only", "fails", "false_fails",
              "known_tp_fails", "warns_untriaged", "warns_accepted", "caught_fail_rows", "caught_fw_rows", "fails_rows",
              "caught_fw_catchable", "caught_fw_catchable_rows",
              "false_fails_rows", "known_tp_fails_rows", "warns_untriaged_rows"):
        s[k] = sum(r.get(k, 0) for r in rows)
    n = s["labels"] or 1
    s.update({"recall_fail": round(s["caught_fail"] / n, 3), "recall_fw": round(s["caught_fw"] / n, 3),
              "recall_fail_rows": round(s["caught_fail_rows"] / n, 3), "recall_fw_rows": round(s["caught_fw_rows"] / n, 3),
              "recall_fw_catchable": round(s["caught_fw_catchable"] / (s["labels_tool_catchable"] or 1), 3),
              "recall_fw_catchable_rows": round(s["caught_fw_catchable_rows"] / (s["labels_tool_catchable"] or 1), 3),
              "warn_load": round(s["warns_untriaged"] / n, 2), "warn_load_rows": round(s["warns_untriaged_rows"] / n, 2)})
    s["runtime_s"] = round(sum(r["runtime_s"] or 0 for r in rows), 1)
    s["errors"] = sum(len(r["errors"]) for r in rows)
    return s


# ------------------------------------------------------------------ table

def table(results: Path, commit: str | None, out=sys.stdout) -> None:
    rows = [json.loads(l) for l in open(results) if l.strip()]
    if commit:
        rows = [r for r in rows if r["commit"].startswith(commit) or r.get("ref") == commit]
    print("| commit | attempt | labels (catchable) | fail | fail+warn | f+w of catchable | +rows fail | +rows f+w | false fails | known TP fails | untriaged warns | warn load | runtime s |", file=out)
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|", file=out)
    for r in rows:
        print("| %s%s | %s | %d (%d) | %d (%.0f%%) | %d (%.0f%%) | %d | %d | %d | %d | %d | %d | %.2f | %s |" % (
            r["commit"][:7], "*" if r.get("dirty") else "", r["attempt"], r["labels"], r["labels_tool_catchable"], r["caught_fail"],
            100 * r["recall_fail"], r["caught_fw"], 100 * r["recall_fw"], r.get("caught_fw_catchable", 0), r["caught_fail_rows"],
            r["caught_fw_rows"], r["false_fails"],
            r["known_tp_fails"], r["warns_untriaged"], r["warn_load"], r["runtime_s"] if r["runtime_s"] is not None else "-"), file=out)


# ------------------------------------------------------------------ main

def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["table"]:
        p = argparse.ArgumentParser(prog="replay.py table")
        p.add_argument("--results", default=str(BENCH / "results/replay.jsonl"))
        p.add_argument("--commit")
        a = p.parse_args(argv[1:])
        table(Path(a.results), a.commit)
        return 0
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--commit", default="HEAD", help="tools commit (its skills/ is used; corpus, labels and blends come from this checkout)")
    p.add_argument("--attempts", help="comma list (a1,a2,a3,v2a1..v2a7); default all")
    p.add_argument("--runs", help="comma list of run ids to make (designer,layer,...); default all")
    p.add_argument("--from-verify", help="score a verify_all run dir (/tmp/alex3d-verify/latest) instead of running cad")
    p.add_argument("--from-run", help="rescore an earlier bench scratch dir (/tmp/alex3d-bench/latest) instead of running cad")
    p.add_argument("--labels", default=str(BENCH / "labels.json"))
    p.add_argument("--corpus", default=str(BENCH / "corpus.json"))
    p.add_argument("--results", default=str(BENCH / "results/replay.jsonl"), help="JSONL file the rows are appended to")
    p.add_argument("--no-append", action="store_true", help="print rows, append nothing")
    p.add_argument("-j", type=int, default=1, help="attempts in parallel (runtime_s then includes contention)")
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args(argv)

    corpus = json.load(open(a.corpus))["attempts"]
    lab = json.load(open(a.labels))
    names = a.attempts.split(",") if a.attempts else list(corpus)
    bad = [n for n in names if n not in corpus]
    if bad:
        raise SystemExit("unknown attempts: %s" % bad)
    only_runs = set(a.runs.split(",")) if a.runs else None

    scratch = SCRATCH_BASE / ("run-%d" % os.getpid())
    if a.from_verify:
        vdir = Path(a.from_verify).resolve()
        info = {"ref": "verify:" + str(vdir), "commit": git("rev-parse", "--short=9", "HEAD"), "subject": None,
                "branch": git("rev-parse", "--abbrev-ref", "HEAD"), "from_verify": str(vdir), "skills_tree": git("rev-parse", "--short=9", "HEAD:skills")}
        runs = {n: from_verify(n, corpus[n], vdir) for n in names}
    elif a.from_run:
        rdir = Path(a.from_run).resolve()
        info = {"ref": "run:" + str(rdir), "commit": git("rev-parse", "--short=9", "HEAD"), "subject": None,
                "branch": git("rev-parse", "--abbrev-ref", "HEAD"), "from_run": str(rdir), "skills_tree": git("rev-parse", "--short=9", "HEAD:skills")}
        if (rdir / "bench_meta.json").exists():   # the tools commit that made those reports
            info.update({k: v for k, v in json.load(open(rdir / "bench_meta.json")).items() if k in ("commit", "subject", "dirty", "skills_tree")})
        runs = {n: from_run(n, corpus[n], rdir) for n in names}
    else:
        shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True)
        latest = SCRATCH_BASE / "latest"
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(scratch)
        cad, info = tools_for(a.commit, scratch)
        print("bench: tools %s (%s) -> %s" % (info["commit"], info["ref"], scratch), flush=True)
        (scratch / "bench_meta.json").write_text(json.dumps(info))
        with cf.ThreadPoolExecutor(max_workers=max(1, a.j)) as ex:
            futs = {n: ex.submit(run_attempt, n, corpus[n], cad, scratch, only_runs) for n in names}
            runs = {n: f.result() for n, f in futs.items()}
    when = dt.datetime.now().isoformat(timespec="seconds")
    rows = []
    for n in names:
        L = [l for l in lab["labels"] if l["attempt"] == n]
        K = [k for k in lab.get("known_true_positives", []) if k["attempt"] == n]
        r = score(n, corpus[n], L, K, runs[n])
        if only_runs:
            r["runs_subset"] = sorted(only_runs)
        rows.append(r)
    allrow = summary_row(rows)
    meta = {"when": when, **info, "labels_file_sha": _sha(Path(a.labels)), "scratch": None if (a.from_verify or a.from_run) else str(scratch)}
    out_rows = [{**meta, **r} for r in rows + [allrow]]
    if not a.no_append:
        Path(a.results).parent.mkdir(parents=True, exist_ok=True)
        with open(a.results, "a") as f:
            for r in out_rows:
                f.write(json.dumps(r) + "\n")
    if not a.quiet:
        for r in out_rows:
            print("%-5s labels %2d  fail %2d  f+w %2d  | +rows fail %2d f+w %2d | false fails %d (rows %d)  known-TP %d  "
                  "untriaged warns %3d (load %.2f)  %s s%s" % (
                      r["attempt"], r["labels"], r["caught_fail"], r["caught_fw"], r["caught_fail_rows"], r["caught_fw_rows"],
                      r["false_fails"], r["false_fails_rows"], r["known_tp_fails"], r["warns_untriaged"], r["warn_load"],
                      r["runtime_s"], ("  errors: %s" % r["errors"]) if r["errors"] else ""))
    print("BENCH recall_fail %.3f recall_fw %.3f recall_fw_rows %.3f false_fails %d warn_load %.2f -> %s" % (
        allrow["recall_fail"], allrow["recall_fw"], allrow["recall_fw_rows"], allrow["false_fails"], allrow["warn_load"],
        "(not appended)" if a.no_append else a.results))
    return 0


def _sha(p: Path) -> str:
    import hashlib
    return hashlib.sha1(p.read_bytes()).hexdigest()[:10]


if __name__ == "__main__":
    sys.exit(main())
