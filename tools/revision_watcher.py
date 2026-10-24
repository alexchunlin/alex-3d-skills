#!/usr/bin/env python3
"""Watch the CAD-loop workflow journal; after each completed review #N (N>=2),
launch an Orca Claude session in this repo with "Revision run for attempt N".
Waits until no other agent is working in this workspace to avoid concurrent commits."""
import json, subprocess, sys, time, pathlib, datetime

JOURNAL = pathlib.Path(sys.argv[1])
REPO = pathlib.Path(__file__).resolve().parent.parent
STATE = REPO / ".watcher" / "state.json"
LOG = REPO / ".watcher" / "watcher.log"
WT = "id:a3e13da0-f00d-4f5c-99cc-af1e90d84738::" + str(REPO)
ORCA = "/Applications/Orca.app/Contents/Resources/bin/orca"
DEADLINE = time.time() + 16 * 3600

STATE.parent.mkdir(exist_ok=True)
state = json.loads(STATE.read_text()) if STATE.exists() else {"launched": []}

def log(msg):
    with LOG.open("a") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")

def reviews_done():
    labels, done = {}, []
    for line in JOURNAL.read_text().splitlines():
        try: e = json.loads(line)
        except Exception: continue
        if e.get("type") == "started": labels[e["key"]] = e.get("label", "")
        elif e.get("type") == "result":
            lab = labels.get(e["key"], "")
            if lab.startswith("review #"): done.append(int(lab.split("#")[1]))
    return sorted(done)

def workspace_busy():
    try:
        d = json.loads(subprocess.run([ORCA, "worktree", "ps", "--json"], capture_output=True, text=True, timeout=60).stdout)
        for w in d["result"]["worktrees"]:
            if w.get("path") == str(REPO):
                return any(a.get("state") == "working" for a in w.get("agents", []))
    except Exception as ex:
        log(f"ps failed: {ex}")
    return True  # unknown -> assume busy

log(f"watcher started, journal={JOURNAL}")
while time.time() < DEADLINE:
    pending = [n for n in reviews_done() if n >= 2 and n not in state["launched"]]
    if pending and not workspace_busy():
        n = pending[0]
        prompt = (f"Revision run for attempt {n}. Follow the 'Revision runs' section of docs/HARVEST_BRIEF.md: "
                  f"read docs/STATUS.md and docs/FINDINGS.md, ingest only attempt {n}'s new data (journal entries for design #{n}/review #{n}, "
                  f"their agent-*.jsonl transcripts, renders/attempt-{n}/), add findings, improve and re-verify the skills/tools, update STATUS, commit.")
        r = subprocess.run([ORCA, "agent", "launch", "--agent", "claude", "--worktree", WT, "--prompt", prompt, "--json"],
                           capture_output=True, text=True, timeout=120)
        log(f"launched revision run for attempt {n}: rc={r.returncode} out={r.stdout[:300]!r} err={r.stderr[:300]!r}")
        state["launched"].append(n); STATE.write_text(json.dumps(state))
    if 8 in reviews_done() and 8 in state["launched"]:
        log("all 8 attempts handled; exiting"); break
    time.sleep(60)
log("watcher exiting")
