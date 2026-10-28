#!/usr/bin/env python3
"""Fixture test of tools/bench/replay.py's scoring, no Blender (tools/verify.d/bench.sh runs it).

The fixtures (tools/bench/fixtures) hold one attempt's reports and labels that exercise each rule: the check prefix,
an accepted warn, a partial catch, a rows-only label, a crashed run (an error, not a miss), a known true positive, a
printability finding with a region, one false fail, noise warns, and the locator lint. Then it re-runs the same
assertions on two mutants of replay.py (the check prefix ignored; false fails never reported): each must fail them,
or these assertions don't test what they claim to.

  python3 -I tools/bench/test_replay.py      # prints BENCH_FIXTURES ok ... and exits 0
"""
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path

BENCH = Path(__file__).resolve().parent
FX = BENCH / "fixtures"
sys.dont_write_bytecode = True
MUTANTS = {
    "ignore-check-prefix": ('    if not text.startswith(chk + ": "):\n        return False\n', ""),
    "never-report-false-fail": ("        false = [tx for tx in fails if tx not in excused]\n", "        false = []\n"),
}


def load(src: str, name: str):
    spec = importlib.util.spec_from_loader(name, loader=None)
    m = importlib.util.module_from_spec(spec)
    m.__file__ = str(BENCH / "replay.py")
    exec(compile(src, str(BENCH / "replay.py"), "exec"), m.__dict__)
    return m


def checks(R) -> list[str]:
    """Names of the assertions that fail on module R."""
    bad = []

    def want(name, cond):
        if not cond:
            bad.append(name)
    corpus = json.load(open(FX / "corpus.json"))["attempts"]
    lab = json.load(open(FX / "labels.json"))
    runs = R.from_run("fx", corpus["fx"], FX / "run")
    row = R.score("fx", corpus["fx"], lab["labels"], lab["known_true_positives"], runs, lab["printability"])
    pl = {k: v.get("designer") for k, v in row["per_label"].items()}
    plr = {k: v.get("rows") for k, v in row["per_label"].items()}
    want("true positive fails", pl["TP"] == "fail" and "PRT_a x FST_b" in row["per_label"]["TP"]["designer_line"])
    want("check prefix: an interference line does not credit a clearance label", pl["PREFIX"] is None and plr["PREFIX"] is None)
    want("accepted warn counts as fail-or-warn", pl["ACC"] == "accepted")
    want("coverage warn is partial, not caught", pl["PART"] == "partial" and row["caught_partial"] == 1)
    want("rows-only label: not credited in designer scope, credited in rows", pl["ROWS"] is None and plr["ROWS"] == "warn")
    want("crashed run: its label is an error, not a miss", pl["ERR"] == "error" and row["label_errors"] == 1 and "cab" in row["errors"])
    want("unlocatable label is missed", pl["MISS"] is None)
    want("process item is out of the denominator", row["labels"] == 9 and row["labels_excluded"] == ["PROC"])
    want("review row credits in rows scope only", pl["LID"] is None and plr["LID"] == "fail")
    want("counts", (row["caught_fail"], row["caught_fw"], row["caught_fail_rows"], row["caught_fw_rows"]) == (2, 3, 3, 5))
    want("severity weights 3/2/1", (row["weight"], row["w_fail"], row["w_fw"]) == (14, 4, 5) and row["recall_fail_w"] == round(4 / 14, 3))
    want("one false fail, the unlabelled slide fail", row["false_fails"] == 1 and row["false_fail_list"] == ["slide: PRT_z slide-out blocked by ['PRT_y'] at 3 mm"]
         and row["false_fails_rows"] == 1)
    want("known true positive excused, credits nothing", row["known_tp_fails"] == 1)
    want("noise warns and hit share", (row["warns_untriaged"], row["noise_warns"], row["hit_warns"], row["hit_share"]) == (6, 4, 2, 0.333))
    want("printability finding: fail at its region, the ledge elsewhere is noise", row["pf_fail"] == 1 and row["pf_findings"] == 1
         and "z 12.0" in row["pf"]["PF-p"]["designer_line"])
    s = R.summary_row([row], "ALL-v1", lab["printability"])
    want("summary: errors and confirmed print finding", s["errors"] == 1 and s["pf_confirmed"] == ["PF-p"] and s["pf_confirmed_fail"] == 1)
    # lint
    want("lint: real labels and fixture labels clean", not R.lint(json.load(open(BENCH / "labels.json"))) and not R.lint(lab))
    lb = R.lint(json.load(open(FX / "labels_bad.json")))
    want("lint: top-level |, check '*', no object, pinned number", len(lb) == 4 and all(any(i in x for x in lb) for i in ("BAR", "STAR", "NOOBJ", "PIN"))
         and any("top-level |" in x for x in lb) and any("pins a measured number" in x for x in lb) and any("no object name" in x for x in lb))
    # table shows errors, labels sha, run subset; compare refuses other labels and errors
    meta = {"commit": "aaaaaaa00", "labels_file_sha": "sha1", "when": "t"}
    r1 = {**meta, **row, "runs_subset": ["designer"]}
    r2 = {**meta, **row, "commit": "bbbbbbb00", "labels_file_sha": "sha2", "runs_subset": ["designer"]}
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "r.jsonl"
        f.write_text(json.dumps(r1) + "\n" + json.dumps(r2) + "\n")
        o = io.StringIO()
        R.table(f, None, out=o)
        t = o.getvalue()
        want("table: labels sha, errors, run subset, a warning on mixed labels", "WARNING" in t and "labels sha1" in t and "| designer | 1 |" in t)
        o = io.StringIO()
        want("compare refuses different labels", R.compare(f, "aaaaaaa", "bbbbbbb", out=o) == 2 and "labels differ" in o.getvalue())
        r2["labels_file_sha"] = "sha1"
        f.write_text(json.dumps({**r1, "errors": {}}) + "\n" + json.dumps(r2) + "\n")
        o = io.StringIO()
        want("compare refuses a run with errors", R.compare(f, "aaaaaaa", "bbbbbbb", out=o) == 2 and "run errors" in o.getvalue())
        want("score lists print-confirmed failures", row["pf_must_fail"] == ["PF-p"])
        ok_row = {**r1, "errors": {}}
        lost = {**ok_row, "commit": "bbbbbbb00", "pf": {"PF-p": {"designer": "warn"}}}
        f.write_text(json.dumps(ok_row) + "\n" + json.dumps({**ok_row, "commit": "bbbbbbb00"}) + "\n")
        o = io.StringIO()
        want("compare passes an unchanged row", R.compare(f, "aaaaaaa", "bbbbbbb", out=o) == 0)
        f.write_text(json.dumps(ok_row) + "\n" + json.dumps(lost) + "\n")
        o = io.StringIO()
        want("compare: a print-confirmed failure that no longer fails is worse", R.compare(f, "aaaaaaa", "bbbbbbb", out=o) == 1
             and "PF-p: a real print failed there" in o.getvalue())
        try:
            R._verify_meta(Path(td), None)
            want("--from-verify without meta.json refuses", False)
        except SystemExit:
            pass
    return bad


def main() -> int:
    src = (BENCH / "replay.py").read_text()
    bad = checks(load(src, "replay_under_test"))
    if bad:
        print("BENCH_FIXTURES FAIL: " + "; ".join(bad))
        return 1
    killed = []
    for name, (old, new) in MUTANTS.items():
        if src.count(old) != 1:
            print("BENCH_FIXTURES FAIL: mutant %s no longer applies (replay.py changed): update MUTANTS" % name)
            return 1
        mb = checks(load(src.replace(old, new), "replay_mutant"))
        if not mb:
            print("BENCH_FIXTURES FAIL: mutant %s survives: the assertions do not test it" % name)
            return 1
        killed.append("%s (%d assertions fail: %s)" % (name, len(mb), "; ".join(mb)))
    print("BENCH_FIXTURES ok; mutants killed: " + " | ".join(killed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
