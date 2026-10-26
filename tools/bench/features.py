#!/usr/bin/env python3
"""Tier 2 join: what each tool feature costs in always-read doc tokens, against how often v2 agents used it.

Inputs: the doc cost at REF (doccost.py), the per-agent telemetry of every v2 (and v1) agent
(`cc_transcript.py bench`, agents from tools/bench/agents.json), and the feature catalog of REF and of each v2 attempt's
pinned tools commit (so a feature added after an attempt is "not available", not "unused").

Features: `cad` subcommands, `cad q` commands, checks.json keys (from the jsonc block of checks-config.md),
cadlib functions (public defs of cadlib/*.py) and the `=EXPR` row values.

Attribution: each always-read doc unit (a bold-lead list item or tool-table row, or the rest of a section) splits its
tokens evenly over the features it names (keys with an underscore by name, others only in backticks or quotes); units
naming none are "general". Tokens are chars / the ratio measured on these transcripts (tools/bench/tokens.json,
`cc_transcript.py calibrate`).

Paid over v2: a session pays a unit's tokens in proportion to how much of the unit's doc it actually read,
min(1, doc tokens it read / the doc's tokens at its pin); a session that never opened the doc pays nothing.

Uses: Bash commands that run the feature, keys in written configs, cadlib calls in written code, plus the shipped v2
code (calls the template wrote) and the feature log (`features._log` entries in the archived v2 manifests). A cadlib
feature that is logged but whose function is never called was re-implemented by hand under its name (shipped
parts/base.py logs drill_to_fit_boss and pcb_pocket itself): "API didn't fit, reimplemented", not unused.

  python3 -I tools/bench/features.py                 # markdown tables (telemetry per attempt, per feature, unused units)
  python3 -I tools/bench/features.py --ref origin/next --json > f.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parents[1]
sys.dont_write_bytecode = True   # no __pycache__ in the checkout
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(ROOT / "tools/transcript"))
import doccost  # noqa: E402
import cc_transcript as cct  # noqa: E402

PCB = "skills/print-cad-blender"
CADLIB_MODS = ("geom", "features", "asm", "export", "render")


def git(*a: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout


def show(ref: str, path: str) -> str:
    return git("show", "%s:%s" % (ref, path))


def catalog(ref: str) -> dict[str, dict]:
    """{feature id: {kind, name, pattern}} at a ref."""
    cat = {}
    wrapper = show(ref, PCB + "/scripts/cad")
    for sub in re.findall(r"^\s+(\w+)\)", wrapper.split('case "$cmd" in')[-1], re.M):
        cat["cad " + sub] = {"kind": "cad subcommand", "name": sub, "pat": r"\bcad %s\b" % re.escape(sub)}
    cadq = show(ref, PCB + "/scripts/cadq.py")
    doc = cadq.split('"""')[1] if '"""' in cadq else ""
    for q in re.findall(r"^  ([a-z]+) ", doc, re.M):
        cat["cad q " + q] = {"kind": "cad q command", "name": q, "pat": r"`%s\b|cad q[^`\n]{0,40}\b%s\b" % (q, q)}
    cfg = show(ref, PCB + "/reference/checks-config.md")
    m = re.search(r"```jsonc\n(.*?)```", cfg, re.S)
    for k in sorted(set(re.findall(r"\"(\w+)\"\s*:", m.group(1) if m else ""))):
        if k.startswith(("PIV_", "PRT_", "BUY_", "FST_", "CAB_")) or len(k) < 3:
            continue
        pat = r"\b%s\b" % k if "_" in k else r"[`\"]%s[`\"]" % k
        cat["key " + k] = {"kind": "checks.json key", "name": k, "pat": pat}
    cat["key =EXPR"] = {"kind": "checks.json key", "name": "=EXPR", "pat": r"=EXPR|\"=[A-Z]"}
    for mod in CADLIB_MODS:
        src = show(ref, "%s/scripts/cadlib/%s.py" % (PCB, mod))
        for f in sorted(set(re.findall(r"^def ([a-z]\w*)\(", src, re.M))):
            cat["%s.%s" % (mod, f)] = {"kind": "cadlib function", "name": f,
                                       "pat": r"\b%s\(|`%s`|\b%s\.%s\b" % (f, f, mod, f)}
    return cat


def used(feature: str, info: dict, row: dict) -> int:
    k = info["kind"]
    if k == "cad subcommand":
        return row["cad_subcommands"].get(info["name"], 0)
    if k == "cad q command":
        return row["cadq_commands"].get(info["name"], 0)
    if k == "checks.json key":
        return row["config_keys"].get(info["name"], 0)
    return row["cadlib_functions"].get(feature, 0)


def config_keys(obj, out: set) -> set:
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            config_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            config_keys(v, out)
    elif isinstance(obj, str) and obj.startswith("="):
        out.add("=EXPR")
    return out


LOG_CALL_RE = re.compile(r"\b(?:F|features)\._log\(\s*[\"'](\w+)[\"']")


def manifest_log() -> dict:
    """{feature name: [v2 attempts whose archived manifest.json logs it]} (cadlib.features._log records)."""
    out = defaultdict(list)
    for d in sorted((ROOT / "examples").glob("mm-launcher-v2a*")):
        try:
            names = {f.get("feature") for f in json.load(open(d / "manifest.json")).get("features", [])}
        except Exception:
            continue
        for n in names:
            out[n].append(d.name.replace("mm-launcher-", ""))
    return dict(out)


def hand_logged(hw_code: Path | None) -> dict:
    """{feature name: `_log("name", ...)` calls in the shipped v2 code}: features built by hand and logged under the
    cadlib name, because the cadlib function didn't fit."""
    out = defaultdict(int)
    if hw_code and hw_code.is_dir():
        for f in hw_code.rglob("*.py"):
            for n in LOG_CALL_RE.findall(f.read_text(errors="replace")):
                out[n] += 1
    return dict(out)


def shipped_use(hw_code: Path | None) -> tuple[dict, dict]:
    """({key: n v2 attempts whose archived designer checks.json has it}, {module.func: calls in the shipped v2 code})."""
    cfg = defaultdict(int)
    for d in sorted((ROOT / "examples").glob("mm-launcher-v2a*")):
        try:
            for k in config_keys(json.load(open(d / "checks.json")), set()):
                cfg[k] += 1
        except Exception:
            pass
    code = defaultdict(int)
    if hw_code and hw_code.is_dir():
        for f in hw_code.rglob("*.py"):
            for m, fn in cct.CADLIB_CALL_RE.findall(f.read_text(errors="replace")):
                code["%s.%s" % (cct.CADLIB_ALIAS.get(m, m), fn)] += 1
    return dict(cfg), dict(code)


def units(rep: dict) -> list[dict]:
    """Always-read doc units: each item, plus each section's text outside its items."""
    out = []
    for d in rep["docs"]:
        if d["class"] != "always":
            continue
        for s in d["sections"]:
            rest = s["text"]
            for i in s["items"]:
                out.append({"doc": d["path"], "role": d["role"], "unit": "%s > %s" % (s["title"][:50], i["title"][:60]),
                            "tokens": i["tokens"], "text": i["text"]})
                rest = rest.replace(i["text"], "", 1)
            out.append({"doc": d["path"], "role": d["role"], "unit": s["title"][:80], "tokens": doccost.tok(len(rest)), "text": rest})
    return [u for u in out if u["tokens"] > 0]


def build(ref: str, agents_file: str, hw_code: Path | None = None) -> dict:
    rep = doccost.report(ref, keep_text=True)
    cat = catalog(ref)
    spec = json.load(open(agents_file))
    pins = spec["pins"]
    avail = {f: [] for f in cat}
    for att, pin in pins.items():
        c = catalog(pin)
        for f in cat:
            if f in c:
                avail[f].append(att)
    root = Path(spec["wf_root"]).expanduser()
    cpt = doccost.CHARS_PER_TOKEN
    tele, missing = [], []
    for g in spec["agents"]:
        f = root / g["path"]
        if not f.exists():
            missing.append(g["name"])
            continue
        tele.append({**g, **cct.bench_digest(cct.load(f), cct.SkillTree.at(pins.get(g["attempt"]) or "HEAD"), cpt)})
    v2 = [t for t in tele if t["attempt"].startswith("v2")]
    sessions = {r: sum(1 for t in v2 if t["role"] == r) for r in ("designer", "reviewer")}

    def read_frac(t: dict, doc: str) -> float:
        """How much of doc (skills/...) session t read: its doc tokens over the doc's tokens at its pin, capped at 1."""
        key = tuple(doc.split("/", 2)[1:])
        full = len(cct.SkillTree.at(pins.get(t["attempt"]) or "HEAD").text(key)) / cpt
        return min(1.0, t["docs_total"].get("%s/%s" % key, 0) / full) if full else 0.0
    docs_always = sorted({d["path"] for d in rep["docs"] if d["class"] == "always"})
    reads = {d: {r: round(sum(read_frac(t, d) for t in v2 if t["role"] == r), 2) for r in ("designer", "reviewer")} for d in docs_always}
    # attribution
    U = units(rep)
    feat_tok = defaultdict(float)
    feat_units = defaultdict(list)
    feat_paid = defaultdict(float)
    for u in U:
        names = [f for f, i in cat.items() if re.search(i["pat"], u["text"])]
        u["features"] = names
        for f in names:
            feat_tok[(f, u["role"])] += u["tokens"] / len(names)
            feat_paid[f] += u["tokens"] / len(names) * reads[u["doc"]].get(u["role"], 0)
            feat_units[f].append(u["unit"])
    use = {f: sum(used(f, i, t) for t in v2) for f, i in cat.items()}
    in_cfg, in_code = shipped_use(hw_code)
    shipped = {f: (in_cfg.get(i["name"], 0) if i["kind"] == "checks.json key" else in_code.get(f, 0) if i["kind"] == "cadlib function" else 0)
               for f, i in cat.items()}
    sess_use = {f: sum(1 for t in v2 if used(f, i, t)) for f, i in cat.items()}
    mlog, hlog = manifest_log(), hand_logged(hw_code)
    feats = []
    for f, i in cat.items():
        roles = sorted(set(r for (ff, r) in feat_tok if ff == f))
        tok = sum(v for (ff, r), v in feat_tok.items() if ff == f)
        a = avail[f]
        is_feat = f.startswith("features.")
        logged = mlog.get(i["name"], []) if is_feat else []
        by_hand = hlog.get(i["name"], 0) if is_feat else 0
        flag = ("not in any v2 pin (new since v2 A7)" if not a else
                "API didn't fit, reimplemented (logged by hand in shipped code, never called)" if use[f] == 0 and shipped[f] == 0 and by_hand else
                "NEVER USED in v2" if use[f] == 0 and shipped[f] == 0 and not logged else
                "only in template/earlier code" if use[f] == 0 else "")
        feats.append({"feature": f, "kind": i["kind"], "always_tokens_per_session": round(tok), "roles": roles,
                      "tokens_paid_v2": round(feat_paid[f]), "uses_v2": use[f], "sessions_using_v2": sess_use[f], "in_shipped_v2": shipped[f],
                      "logged_in_v2_manifests": logged, "hand_logged_in_shipped": by_hand,
                      "available_from": a[0] if a else None, "available_attempts": len(a), "flag": flag,
                      "units": feat_units[f][:6]})
    feats.sort(key=lambda x: (-x["always_tokens_per_session"], -x["uses_v2"]))
    unit_rows = []
    for u in U:
        fs = u["features"]
        av = [f for f in fs if avail[f]]
        fl = {x["feature"]: x["flag"] for x in feats}
        st = ("general" if not fs else
              "reimplemented" if av and all(fl[f].startswith(("API didn't fit", "NEVER")) for f in av) and any(fl[f].startswith("API") for f in av) else
              "unused" if av and all(fl[f].startswith("NEVER") for f in av) else
              "new since v2" if not av else "used")
        unit_rows.append({"doc": u["doc"], "unit": u["unit"], "tokens": u["tokens"], "features": fs, "status": st,
                          "uses_v2": sum(use[f] for f in fs)})
    # per attempt telemetry
    per_att = defaultdict(lambda: defaultdict(float))
    doc_sessions = defaultdict(lambda: defaultdict(int))
    for t in tele:
        a = per_att[t["attempt"]]
        a["agents"] += 1
        for k in ("output_tokens", "doc_tokens_before_edit", "doc_tokens_total", "source_read_calls", "source_read_tokens",
                  "cad_runs", "cad_failed"):
            a[k] += t[k]
        for d, v in t["docs_total"].items():
            a["doc:" + d] += v
            if v > 50:
                doc_sessions[t["role"] + ("/v2" if t["attempt"].startswith("v2") else "/v1")][d] += 1
    return {"ref": rep["ref"], "commit": rep["commit"], "always_tokens_per_session": rep["always_tokens_per_session"],
            "chars_per_token": cpt, "tokens_source": doccost.TOKENS_SOURCE, "v2_doc_reads": reads,
            "v2_sessions": sessions, "missing_transcripts": missing, "features": feats, "units": unit_rows,
            "shipped_sources": {"configs": "examples/mm-launcher-v2a*/checks.json", "code": str(hw_code) if hw_code and hw_code.is_dir() else None},
            "per_attempt": {k: dict(v) for k, v in per_att.items()}, "doc_read_sessions": {k: dict(v) for k, v in doc_sessions.items()},
            "agents": [{k: v for k, v in t.items() if k not in ("path",)} for t in tele]}


def markdown(r: dict) -> str:
    L = []
    w = L.append
    w("Doc cost at %s (%s): always-read %s tokens per session (chars/%.2f, %s). v2 sessions: %s." % (
        r["ref"], r["commit"], ", ".join("%s %d" % kv for kv in r["always_tokens_per_session"].items()), r["chars_per_token"],
        r["tokens_source"], ", ".join("%s %d" % kv for kv in r["v2_sessions"].items())))
    w("\nv2 reads of each always-read doc, in full-read equivalents (sum over sessions of min(1, tokens read / doc tokens at the "
      "session's pin)): " + "; ".join("%s %s" % (d.replace("skills/", ""), ", ".join("%s %.1f" % kv for kv in v.items() if kv[1]))
                                      for d, v in r["v2_doc_reads"].items()))
    if r["missing_transcripts"]:
        w("Missing transcripts: %s" % ", ".join(r["missing_transcripts"]))
    w("\n**Per attempt** (summed over its agents; doc tokens are what agents read, not the static size)\n")
    w("| attempt | agents | output tok | skill-doc tok before 1st edit | skill-doc tok total | source reads (calls / tok) | cad+Blender runs | failed |")
    w("|---|---|---|---|---|---|---|---|")
    for k in sorted(r["per_attempt"], key=lambda x: (x.startswith("v2"), x)):
        a = r["per_attempt"][k]
        w("| %s | %d | %dk | %d | %d | %d / %d | %d | %d |" % (k, a["agents"], a["output_tokens"] / 1000, a["doc_tokens_before_edit"],
                                                              a["doc_tokens_total"], a["source_read_calls"], a["source_read_tokens"],
                                                              a["cad_runs"], a["cad_failed"]))
    src = defaultdict(lambda: [0, 0])
    for t in r["agents"]:
        if t["attempt"].startswith("v2"):
            for f, v in t["source_reads"].items():
                src[f][0] += 1
                src[f][1] += v
    w("\n**Tool and library source read by v2 agents** (a sign the docs did not answer; sessions / tokens): " + ", ".join(
        "%s %d / %d" % (f, n, v) for f, (n, v) in sorted(src.items(), key=lambda x: -x[1][1])[:8]))
    w("\n**Which docs sessions actually read** (sessions with > 50 tokens of the doc)\n")
    for role, d in sorted(r["doc_read_sessions"].items()):
        w("- %s: %s" % (role, ", ".join("%s %d" % (k, v) for k, v in sorted(d.items(), key=lambda x: -x[1]))))
    w("\n**Per feature** (always-read tokens attributed at %s; paid over v2 = each v2 session pays the unit tokens x "
      "min(1, tokens it read of the unit's doc / the doc's tokens at its pin))\n" % r["ref"])
    w("in shipped v2 = attempts whose archived checks.json has the key (of 7), or calls in the shipped v2 code (cadlib); "
      "logged = archived v2 manifests whose feature log names it\n")
    w("| feature | kind | always tok/session | paid over v2 | uses in v2 (calls) | v2 sessions using | in shipped v2 | logged | available from | flag |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for f in r["features"]:
        if f["always_tokens_per_session"] == 0 and not f["flag"].startswith("API"):
            continue
        w("| %s | %s | %d | %d | %d | %d | %d | %s | %s | %s |" % (
            f["feature"], f["kind"], f["always_tokens_per_session"], f["tokens_paid_v2"], f["uses_v2"], f["sessions_using_v2"],
            f["in_shipped_v2"], len(f["logged_in_v2_manifests"]) or "-", f["available_from"] or "-", f["flag"]))
    buckets = defaultdict(int)
    for f in r["features"]:
        b = ("new since v2 A7" if not f["available_attempts"] else "never used in v2" if f["flag"].startswith("NEVER") else
             "reimplemented by hand" if f["flag"].startswith("API") else
             "used in 1-2 v2 sessions" if f["sessions_using_v2"] <= 2 else "used in 3+ v2 sessions")
        buckets[b] += f["always_tokens_per_session"]
    gen = sum(u["tokens"] for u in r["units"] if u["status"] == "general")
    w("\nAlways-read tokens per session by feature use (designer + reviewer docs): " + ", ".join(
        "%s %d" % (k, buckets[k]) for k in ("used in 3+ v2 sessions", "used in 1-2 v2 sessions", "reimplemented by hand", "never used in v2",
                                            "new since v2 A7"))
      + ", general guidance (names no feature) %d" % gen)
    z = [f for f in r["features"] if f["always_tokens_per_session"] == 0 and (f["uses_v2"] or f["in_shipped_v2"])]
    w("\nUsed but not named in the always-read docs (%d): %s" % (len(z), ", ".join("%s %d" % (f["feature"], f["uses_v2"]) for f in z)))
    rh = [f for f in r["features"] if f["flag"].startswith("API")]
    w("\nAPI didn't fit, reimplemented by hand and logged under the cadlib name (%d): %s" % (len(rh), ", ".join(
        "%s (logged in %d v2 manifests, %d hand _log calls in shipped code)" % (f["feature"], len(f["logged_in_v2_manifests"]), f["hand_logged_in_shipped"])
        for f in rh)))
    nd = [f for f in r["features"] if f["always_tokens_per_session"] == 0 and not f["uses_v2"] and not f["in_shipped_v2"]
          and f["available_attempts"] and not f["flag"].startswith("API")]
    w("\nNot named in the always-read docs and never used in v2 (%d): %s" % (len(nd), ", ".join(f["feature"] for f in nd)))
    w("\n**Always-read doc units by status**\n")
    w("| doc | unit | tokens | status | features (uses in v2) |")
    w("|---|---|---|---|---|")
    for u in sorted(r["units"], key=lambda u: ({"unused": 0, "reimplemented": 1, "new since v2": 2, "general": 3, "used": 4}[u["status"]], -u["tokens"])):
        if u["status"] == "used":
            continue
        w("| %s | %s | %d | %s | %s |" % (u["doc"].replace("skills/", ""), u["unit"].replace("|", "/"), u["tokens"], u["status"],
                                        ", ".join(u["features"][:6]) or "-"))
    tot = defaultdict(int)
    for u in r["units"]:
        tot[u["status"]] += u["tokens"]
    w("\nAlways-read tokens by unit status: " + ", ".join("%s %d" % kv for kv in sorted(tot.items())))
    return "\n".join(L)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ref", default="HEAD")
    p.add_argument("--agents", default=str(BENCH / "agents.json"))
    p.add_argument("--hw-code", default="~/code-stuff/mmlauncher/mm-launcher/mm-launch-hw/v2/blender",
                   help="the shipped v2 build sources (read-only), for cadlib calls the agents never typed (template code)")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    r = build(a.ref, a.agents, Path(a.hw_code).expanduser())
    print(json.dumps(r, indent=1) if a.json else markdown(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
