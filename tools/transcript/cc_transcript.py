#!/usr/bin/env python3
"""Extract a compact, structured digest from a Claude Code agent transcript (JSONL).

Never read a 10 MB transcript whole. Run this instead:

    python3 -I cc_transcript.py summary  agent-XXXX.jsonl          # one-screen digest
    python3 -I cc_transcript.py timeline agent-XXXX.jsonl          # every API call / tool call with gaps
    python3 -I cc_transcript.py bash     agent-XXXX.jsonl [--errors]
    python3 -I cc_transcript.py files    agent-XXXX.jsonl          # Write/Edit/heredoc writes + sizes
    python3 -I cc_transcript.py images   agent-XXXX.jsonl          # images read: count, bytes, repeats
    python3 -I cc_transcript.py renders  agent-XXXX.jsonl          # PNGs saved by Blender, repeats
    python3 -I cc_transcript.py usage    agent-XXXX.jsonl          # tokens per API call
    python3 -I cc_transcript.py json     agent-XXXX.jsonl > d.json # everything, machine-readable
    python3 -I cc_transcript.py show     agent-XXXX.jsonl <tool_use_id|index> # full input+output of one call
    python3 -I cc_transcript.py thinking agent-XXXX.jsonl [--min-s 120] [--chars 1500]  # what long thinking was about
    python3 -I cc_transcript.py grep     agent-XXXX.jsonl PATTERN    # regex over thinking/text/tool io
    python3 -I cc_transcript.py workflow <wf_dir>                    # one row per agent + journal results
    python3 -I cc_transcript.py bench [--attempt v2a7] [--json]      # tools/bench tier 2 telemetry (tools/bench/agents.json)
    python3 -I cc_transcript.py calibrate [--write]                  # chars/token of doc reads from the usage numbers

Standard library only. Works on transcripts that are still being written (a
partial last line is ignored).

Transcript facts this relies on (Claude Code 2.1.x, verified on the mm-launcher run):
- one `assistant` line per content block; blocks of one API call share
  `message.id`/`requestId` and repeat `message.usage` (take the last).
- `thinkingDurationMs` sits on thinking-block lines.
- tool results are `user` lines whose `message.content` holds `tool_result`
  blocks keyed by `tool_use_id`; image results carry base64 `source.data`.
"""
from __future__ import annotations

import argparse
import base64
import os
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

# the print-cad-blender wrapper too (`cad build|check|q|sheet`, `$CAD ...`): v2 agents never call Blender directly, so
# the v2 A1 summaries showed "blender runs 0" for agents that ran dozens of checks (FINDINGS V2A1-T7)
BLENDER_RE = re.compile(r"(Blender(\.app)?/Contents/MacOS/Blender|\bblender\b\s+-b|\$BLENDER|\bBL\b\s+-b|"
                        r"(?:/scripts/cad|\$\{?\w+\}?|(?:^|[\s;&|(])cad)\s+(?:build\s+\S+\.py|(?:check|q)\s+\S+\.blend|sheet\s))", re.I)
SAVED_RE = re.compile(r"Saved:\s*'([^']+\.(?:png|jpg|jpeg|exr))'", re.I)
WROTE_RE = re.compile(r"(?:wrote|saved|render(?:ed)?)\s*[:=]?\s*(\S+\.(?:png|jpg|jpeg))", re.I)
HEREDOC_RE = re.compile(r"cat\s+>\s*(\S+)\s+<<\s*'?(\w+)'?\n(.*?)\n\2", re.S)
TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\)|^\w*Error: |^Error: ", re.M)
ERR_LINE_RE = re.compile(r"^(?:\w+Error|Error|RuntimeError|AttributeError|TypeError|KeyError|NameError|ValueError|IndexError|ZeroDivisionError)[:\s].*$", re.M)


def ts(s: str | None) -> float | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def fmt_t(t: float | None, t0: float) -> str:
    if t is None:
        return "   ?   "
    s = int(t - t0)
    return f"{s // 3600:d}:{s // 60 % 60:02d}:{s % 60:02d}"


@dataclass
class ToolCall:
    idx: int
    id: str
    name: str
    input: dict
    t_call: float | None = None
    t_result: float | None = None
    request_id: str | None = None
    is_error: bool = False
    result_text: str = ""
    result_chars: int = 0
    images: list = field(default_factory=list)  # [{"bytes": n, "media_type": ...}]

    @property
    def run_s(self) -> float | None:
        if self.t_call is None or self.t_result is None:
            return None
        return self.t_result - self.t_call

    def brief(self, n: int = 110) -> str:
        i = self.input
        if self.name == "Bash":
            s = i.get("description") or i.get("command", "")
        elif self.name in ("Read", "Write", "Edit", "NotebookEdit"):
            s = i.get("file_path", "")
            if self.name == "Write":
                s += f"  ({len(i.get('content', '')):,} chars)"
            if self.name == "Edit":
                s += f"  (-{len(i.get('old_string', '')):,} +{len(i.get('new_string', '')):,})"
        elif self.name == "Grep":
            s = f"{i.get('pattern')} in {i.get('path', '.')}"
        else:
            s = json.dumps(i)[:n]
        s = s.replace("\n", " ")
        return s if len(s) <= n else s[: n - 1] + "…"


@dataclass
class ApiCall:
    request_id: str
    t_first: float | None
    t_last: float | None
    model: str | None = None
    usage: dict = field(default_factory=dict)
    thinking_ms: int = 0
    text_chars: int = 0
    thinking_chars: int = 0
    tool_ids: list = field(default_factory=list)
    tool_input_chars: int = 0
    gap_before_s: float | None = None  # previous event (tool result / prompt) -> this call's first block
    prev_event_t: float | None = None

    @property
    def gen_s(self) -> float | None:
        """Whole generation: previous event -> last block streamed (thinking + text + tool input)."""
        if self.prev_event_t is None or self.t_last is None:
            return None
        return self.t_last - self.prev_event_t


@dataclass
class Transcript:
    path: str
    agent_id: str | None = None
    label: str | None = None
    t_start: float | None = None
    t_end: float | None = None
    prompt_chars: int = 0
    api_calls: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    final_text: str = ""


def _result_payload(content) -> tuple[str, list]:
    if isinstance(content, str):
        return content, []
    texts, imgs = [], []
    for c in content or []:
        if c.get("type") == "text":
            texts.append(c.get("text", ""))
        elif c.get("type") == "image":
            src = c.get("source", {})
            data = src.get("data", "")
            imgs.append({"bytes": len(data) * 3 // 4, "media_type": src.get("media_type")})
    return "\n".join(texts), imgs


def load(path: str | Path) -> Transcript:
    path = Path(path)
    tr = Transcript(path=str(path))
    meta = path.with_suffix("").with_suffix(".meta.json") if path.suffix == ".jsonl" else None
    meta = Path(str(path)[: -len(".jsonl")] + ".meta.json")
    if meta.exists():
        try:
            tr.label = json.loads(meta.read_text()).get("description")
        except Exception:
            pass
    calls: dict[str, ApiCall] = {}
    tools: dict[str, ToolCall] = {}
    last_event_t: float | None = None
    with open(path, "rb") as fh:
        for raw in fh:
            try:
                d = json.loads(raw)
            except Exception:
                continue  # partial last line of a live transcript
            t = ts(d.get("timestamp"))
            typ = d.get("type")
            if t is not None:
                tr.t_start = t if tr.t_start is None else min(tr.t_start, t)
                tr.t_end = t if tr.t_end is None else max(tr.t_end, t)
            tr.agent_id = tr.agent_id or d.get("agentId")
            if typ == "user":
                content = d.get("message", {}).get("content")
                if isinstance(content, str) or (isinstance(content, list) and not any(
                        isinstance(c, dict) and c.get("type") == "tool_result" for c in content)):
                    if not tr.prompt_chars and not d.get("isMeta"):
                        tr.prompt_chars = len(content) if isinstance(content, str) else len(json.dumps(content))
                    last_event_t = t
                    continue
                for c in content:
                    if not isinstance(c, dict) or c.get("type") != "tool_result":
                        continue
                    tc = tools.get(c.get("tool_use_id"))
                    if tc is None:
                        continue
                    text, imgs = _result_payload(c.get("content"))
                    tc.t_result = t
                    tc.is_error = bool(c.get("is_error"))
                    tc.result_text = text
                    tc.result_chars = len(text)
                    tc.images = imgs
                last_event_t = t
            elif typ == "assistant":
                m = d.get("message", {})
                rid = d.get("requestId") or m.get("id") or d.get("uuid")
                ac = calls.get(rid)
                if ac is None:
                    ac = ApiCall(request_id=rid, t_first=t, t_last=t, model=m.get("model"))
                    if last_event_t is not None and t is not None:
                        ac.gap_before_s = t - last_event_t
                        ac.prev_event_t = last_event_t
                    calls[rid] = ac
                    tr.api_calls.append(ac)
                ac.t_last = t
                if m.get("usage"):
                    ac.usage = m["usage"]
                ac.thinking_ms += int(d.get("thinkingDurationMs") or 0)
                for c in m.get("content", []) or []:
                    ct = c.get("type")
                    if ct == "text":
                        ac.text_chars += len(c.get("text", ""))
                        tr.final_text = c.get("text", "")
                    elif ct == "thinking":
                        ac.thinking_chars += len(c.get("thinking", ""))
                    elif ct == "tool_use":
                        tc = ToolCall(idx=len(tr.tools), id=c["id"], name=c["name"], input=c.get("input", {}),
                                      t_call=t, request_id=rid)
                        tools[c["id"]] = tc
                        tr.tools.append(tc)
                        ac.tool_ids.append(c["id"])
                        ac.tool_input_chars += len(json.dumps(c.get("input", {})))
                last_event_t = t
    return tr


# ---------------------------------------------------------------- analyses

def usage_totals(tr: Transcript) -> dict:
    tot = {"api_calls": len(tr.api_calls), "input": 0, "cache_creation": 0, "cache_read": 0, "output": 0, "thinking": 0}
    for a in tr.api_calls:
        u = a.usage or {}
        tot["input"] += u.get("input_tokens", 0) or 0
        tot["cache_creation"] += u.get("cache_creation_input_tokens", 0) or 0
        tot["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
        tot["output"] += u.get("output_tokens", 0) or 0
        tot["thinking"] += (u.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0
    # Some calls never get their final usage line (stream ended early): usage then holds the streaming-start
    # values (output_tokens ~8, no output_tokens_details). Estimate their thinking from thinkingDurationMs at
    # the rate measured on complete calls of the same transcript (88-95 tok/s on the mm-launcher run, A2-T5).
    inc = incomplete_usage(tr)
    tot["incomplete_calls"] = len(inc)
    tot["est_missing_output"] = sum(e for _, e in inc)
    misses = [a for a in tr.api_calls[1:] if not (a.usage or {}).get("cache_read_input_tokens")
              and ((a.usage or {}).get("cache_creation_input_tokens") or 0) > 20000]
    tot["cache_misses"] = len(misses)
    tot["cache_miss_rewrite_tokens"] = sum(a.usage.get("cache_creation_input_tokens", 0) for a in misses)
    tot["max_context"] = max(((a.usage or {}).get("input_tokens", 0) + (a.usage or {}).get("cache_read_input_tokens", 0)
                              + (a.usage or {}).get("cache_creation_input_tokens", 0) for a in tr.api_calls), default=0)
    return tot


THINK_TOK_PER_S = 92.0  # fallback rate when a transcript has no complete long-thinking call


def incomplete_usage(tr: Transcript) -> list[tuple["ApiCall", int]]:
    """(call, estimated output tokens) for calls whose final usage line is missing and that thought >= 5 s."""
    good = [a for a in tr.api_calls if (a.usage or {}).get("output_tokens_details") and a.thinking_ms > 60000]
    ms = sum(a.thinking_ms for a in good)
    rate = (sum(a.usage["output_tokens_details"].get("thinking_tokens", 0) for a in good) / (ms / 1000)) if ms else THINK_TOK_PER_S
    return [(a, int(rate * a.thinking_ms / 1000)) for a in tr.api_calls
            if not (a.usage or {}).get("output_tokens_details") and a.thinking_ms >= 5000]


def is_blender(tc: ToolCall) -> bool:
    return tc.name == "Bash" and bool(BLENDER_RE.search(tc.input.get("command", "")))


def bash_failed(tc: ToolCall) -> bool:
    if tc.name != "Bash":
        return False
    if tc.is_error:
        return True
    return bool(TRACEBACK_RE.search(tc.result_text))


def error_lines(text: str, k: int = 3) -> list[str]:
    lines = ERR_LINE_RE.findall(text)
    if not lines and "Traceback" in text:
        lines = [text.strip().splitlines()[-1]]
    if not lines and text.startswith("Exit code"):
        lines = [text.strip().splitlines()[0]]
    return [l[:200] for l in lines[-k:]]


def files_written(tr: Transcript) -> list[dict]:
    out = []
    for tc in tr.tools:
        i = tc.input
        if tc.name == "Write":
            out.append({"idx": tc.idx, "t": tc.t_call, "how": "Write", "path": i.get("file_path"),
                        "chars": len(i.get("content", ""))})
        elif tc.name == "Edit":
            out.append({"idx": tc.idx, "t": tc.t_call, "how": "Edit", "path": i.get("file_path"),
                        "chars": len(i.get("new_string", "")), "removed": len(i.get("old_string", ""))})
        elif tc.name == "Bash":
            for m in HEREDOC_RE.finditer(i.get("command", "")):
                out.append({"idx": tc.idx, "t": tc.t_call, "how": "heredoc", "path": m.group(1),
                            "chars": len(m.group(3))})
    return out


def images_read(tr: Transcript) -> list[dict]:
    out = []
    for tc in tr.tools:
        if tc.images:
            p = tc.input.get("file_path", tc.name)
            for im in tc.images:
                out.append({"idx": tc.idx, "t": tc.t_call, "path": p, "bytes": im["bytes"],
                            "media_type": im["media_type"]})
    return out


def renders_saved(tr: Transcript) -> list[dict]:
    out = []
    for tc in tr.tools:
        if tc.name != "Bash":
            continue
        for p in SAVED_RE.findall(tc.result_text):
            out.append({"idx": tc.idx, "t": tc.t_result, "path": p})
    return out


def long_gaps(tr: Transcript, min_s: float = 120) -> list[dict]:
    """API calls whose generation (thinking + output) took >= min_s."""
    out = []
    for a in tr.api_calls:
        if a.gen_s is not None and a.gen_s >= min_s:
            u = a.usage or {}
            names = [next((t.name for t in tr.tools if t.id == i), "?") for i in a.tool_ids]
            first = next((t for t in tr.tools if a.tool_ids and t.id == a.tool_ids[0]), None)
            est = dict((id(c), e) for c, e in incomplete_usage(tr)).get(id(a))
            out.append({"t": a.t_first, "gap_s": round(a.gen_s), "thinking_s": round(a.thinking_ms / 1000),
                        "output_tokens": u.get("output_tokens") if est is None else f"~{est} (est)",
                        "thinking_tokens": (u.get("output_tokens_details") or {}).get("thinking_tokens"),
                        "tool_input_chars": a.tool_input_chars, "tools": names,
                        "what": first.brief(90) if first else f"text {a.text_chars} chars"})
    return out


def digest(tr: Transcript) -> dict:
    t0 = tr.t_start or 0
    from collections import Counter
    tool_counts = Counter(t.name for t in tr.tools)
    bl = [t for t in tr.tools if is_blender(t)]
    bl_fail = [t for t in bl if bash_failed(t)]
    bash_fail = [t for t in tr.tools if bash_failed(t)]
    imgs = images_read(tr)
    img_paths = Counter(i["path"] for i in imgs)
    rend = renders_saved(tr)
    rend_names = Counter(Path(r["path"]).name for r in rend)
    tool_time = sum(t.run_s or 0 for t in tr.tools)
    wall = (tr.t_end or 0) - (tr.t_start or 0)
    gen_time = sum(a.gen_s or 0 for a in tr.api_calls)
    fw = files_written(tr)
    return {
        "path": tr.path, "agent_id": tr.agent_id, "label": tr.label,
        "start": datetime.fromtimestamp(t0).isoformat(timespec="seconds") if tr.t_start else None,
        "wall_min": round(wall / 60, 1),
        "model_time_min": round(gen_time / 60, 1),
        "tool_time_min": round(tool_time / 60, 1),
        "tool_counts": dict(tool_counts),
        "usage": usage_totals(tr),
        "blender_runs": len(bl), "blender_failures": len(bl_fail),
        "blender_time_min": round(sum(t.run_s or 0 for t in bl) / 60, 1),
        "bash_failures": [{"idx": t.idx, "t": fmt_t(t.t_call, t0), "what": t.brief(80), "err": error_lines(t.result_text)}
                          for t in bash_fail],
        "images_read": len(imgs), "image_bytes": sum(i["bytes"] for i in imgs),
        "images_reread": {p: n for p, n in img_paths.items() if n > 1},
        "renders_saved": len(rend), "renders_repeated": {p: n for p, n in rend_names.items() if n > 1},
        "files_written": [{"idx": f["idx"], "t": fmt_t(f["t"], t0), "how": f["how"], "path": f["path"], "chars": f["chars"]}
                          for f in fw],
        "long_gaps": [{**g, "t": fmt_t(g["t"], t0)} for g in long_gaps(tr)],
    }


# ---------------------------------------------------------------- CLI

def _short(p: str | None) -> str:
    if not p:
        return ""
    for pre in ("/Users/alxchunlin/code-stuff/mmlauncher/mm-launcher/mm-launch-hw/", str(Path.home()) + "/"):
        if p.startswith(pre):
            return p[len(pre):]
    return p


def cmd_summary(tr: Transcript, a) -> None:
    d = digest(tr)
    u = d["usage"]
    print(f"# {d['label'] or ''}  agent {d['agent_id']}  start {d['start']}")
    print(f"wall {d['wall_min']} min = model {d['model_time_min']} + tools {d['tool_time_min']} "
          f"(blender {d['blender_time_min']}) ; {u['api_calls']} API calls")
    print(f"tokens: out {u['output']:,} (thinking {u['thinking']:,}) ; cache_read {u['cache_read']:,} ; "
          f"cache_write {u['cache_creation']:,} ; uncached in {u['input']:,} ; peak context {u['max_context']:,}")
    if u["incomplete_calls"]:
        print(f"WARNING: {u['incomplete_calls']} call(s) have no final usage line; out/thinking above are short by "
              f"~{u['est_missing_output']:,} tokens (estimated from thinking time)")
    print(f"prompt-cache misses after a long gap: {u['cache_misses']} (re-wrote {u['cache_miss_rewrite_tokens']:,} tokens)")
    print("tools:", ", ".join(f"{k} {v}" for k, v in sorted(d["tool_counts"].items(), key=lambda x: -x[1])))
    print(f"blender runs {d['blender_runs']} (failed {d['blender_failures']}) ; bash failures {len(d['bash_failures'])}")
    print(f"images read {d['images_read']} ({d['image_bytes'] / 1e6:.1f} MB raw) ; re-read: {d['images_reread'] or '-'}")
    print(f"renders saved {d['renders_saved']} ; same name re-rendered: {d['renders_repeated'] or '-'}")
    print("long generations (>= 120 s from previous event to last streamed block):")
    for g in d["long_gaps"]:
        print(f"  {g['t']}  {g['gap_s']:>5}s (think {g['thinking_s']}s)  out {g['output_tokens']}  think {g['thinking_tokens']}  "
              f"in-chars {g['tool_input_chars']:,}  {'/'.join(g['tools']) or '-'}: {_short(g['what'])}")
    print("files written:")
    for f in d["files_written"]:
        print(f"  {f['t']}  #{f['idx']:<3} {f['how']:<7} {f['chars']:>7,}  {_short(f['path'])}")
    if d["bash_failures"]:
        print("bash failures:")
        for f in d["bash_failures"]:
            print(f"  {f['t']}  #{f['idx']:<3} {_short(f['what'])}\n        {' | '.join(f['err'])}")


def cmd_timeline(tr: Transcript, a) -> None:
    t0 = tr.t_start or 0
    by_id = {t.id: t for t in tr.tools}
    print(" elapsed  gap_s  out_tok  tool        run_s  brief")
    for ac in tr.api_calls:
        u = ac.usage or {}
        gap = f"{ac.gap_before_s:6.0f}" if ac.gap_before_s is not None else "     ?"
        if not ac.tool_ids:
            print(f"{fmt_t(ac.t_first, t0)} {gap} {u.get('output_tokens', 0):>8}  (text {ac.text_chars} chars)")
        for i, tid in enumerate(ac.tool_ids):
            tc = by_id[tid]
            run = f"{tc.run_s:6.1f}" if tc.run_s is not None else "     ?"
            flag = " ERR" if bash_failed(tc) or tc.is_error else ""
            g = gap if i == 0 else "      "
            o = f"{u.get('output_tokens', 0):>8}" if i == 0 else " " * 8
            print(f"{fmt_t(tc.t_call, t0)} {g} {o}  {tc.name:<10} {run}  #{tc.idx} {_short(tc.brief())}{flag}")


def cmd_bash(tr: Transcript, a) -> None:
    t0 = tr.t_start or 0
    for tc in tr.tools:
        if tc.name != "Bash":
            continue
        fail = bash_failed(tc)
        if a.errors and not fail:
            continue
        tag = ("BLENDER " if is_blender(tc) else "") + ("FAIL" if fail else "ok")
        run = f"{tc.run_s:.1f}s" if tc.run_s is not None else "?"
        print(f"--- #{tc.idx} {fmt_t(tc.t_call, t0)} {run} {tag}: {tc.input.get('description', '')}")
        cmd = tc.input.get("command", "")
        print("    $ " + (cmd[:400] + (" …" if len(cmd) > 400 else "")).replace("\n", "\n      "))
        if fail:
            for l in error_lines(tc.result_text, 5):
                print("    ! " + l)


def cmd_files(tr: Transcript, a) -> None:
    t0 = tr.t_start or 0
    for f in files_written(tr):
        print(f"{fmt_t(f['t'], t0)}  #{f['idx']:<3} {f['how']:<7} {f['chars']:>8,}  {f['path']}")


def cmd_images(tr: Transcript, a) -> None:
    t0 = tr.t_start or 0
    from collections import Counter
    imgs = images_read(tr)
    c = Counter(i["path"] for i in imgs)
    for i in imgs:
        print(f"{fmt_t(i['t'], t0)}  #{i['idx']:<3} {i['bytes'] / 1e3:8.0f} KB  {i['path']}" + (f"  (x{c[i['path']]})" if c[i["path"]] > 1 else ""))
    print(f"total {len(imgs)} images, {sum(i['bytes'] for i in imgs) / 1e6:.1f} MB")


def cmd_renders(tr: Transcript, a) -> None:
    t0 = tr.t_start or 0
    from collections import Counter
    r = renders_saved(tr)
    c = Counter(Path(x["path"]).name for x in r)
    for x in r:
        print(f"{fmt_t(x['t'], t0)}  #{x['idx']:<3} {x['path']}" + (f"  (x{c[Path(x['path']).name]})" if c[Path(x['path']).name] > 1 else ""))
    print(f"total {len(r)} renders, {sum(1 for v in c.values() if v > 1)} names rendered more than once")


def cmd_usage(tr: Transcript, a) -> None:
    t0 = tr.t_start or 0
    print(" elapsed   gap_s   in  cache_w  cache_r   out  think  tools")
    for ac in tr.api_calls:
        u = ac.usage or {}
        th = (u.get("output_tokens_details") or {}).get("thinking_tokens", "")
        gap = f"{ac.gap_before_s:6.0f}" if ac.gap_before_s is not None else "     ?"
        names = ",".join(next((t.name for t in tr.tools if t.id == i), "?") for i in ac.tool_ids)
        print(f"{fmt_t(ac.t_first, t0)} {gap} {u.get('input_tokens', 0):>4} {u.get('cache_creation_input_tokens', 0):>8} "
              f"{u.get('cache_read_input_tokens', 0):>8} {u.get('output_tokens', 0):>5} {th!s:>6}  {names}")
    print(usage_totals(tr))


def cmd_show(tr: Transcript, a) -> None:
    key = a.which
    tc = next((t for t in tr.tools if t.id == key or str(t.idx) == key), None)
    if tc is None:
        sys.exit(f"no tool call {key}")
    print(json.dumps({"idx": tc.idx, "name": tc.name, "input": tc.input, "is_error": tc.is_error,
                      "run_s": tc.run_s, "images": tc.images}, indent=1)[: a.max])
    print("--- result ---")
    print(tc.result_text[: a.max])


def cmd_thinking(tr: Transcript, a) -> None:
    t0 = tr.t_start or 0
    want = {c.request_id for c in tr.api_calls if (c.gen_s or 0) >= a.min_s}
    for d in _iter_lines(tr.path):
        if d.get("type") != "assistant" or (d.get("requestId") or d.get("message", {}).get("id")) not in want:
            continue
        for c in d["message"].get("content", []):
            if c.get("type") == "thinking" and c.get("thinking"):
                th = c["thinking"]
                print(f"=== {fmt_t(ts(d.get('timestamp')), t0)}  {len(th):,} chars, {int(d.get('thinkingDurationMs') or 0) / 1000:.0f} s")
                print(th[: a.chars] + (" …" if len(th) > a.chars else ""))


def cmd_grep(tr: Transcript, a) -> None:
    rx = re.compile(a.pattern, re.I)
    t0 = tr.t_start or 0
    for d in _iter_lines(tr.path):
        t = fmt_t(ts(d.get("timestamp")), t0)
        content = d.get("message", {}).get("content") if d.get("type") in ("assistant", "user") else None
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_result":
                body, _ = _result_payload(c.get("content"))
                kind = "result"
            else:
                kind = c.get("type")
                body = c.get("thinking") or c.get("text") or (json.dumps(c.get("input")) if c.get("input") else "")
            for m in rx.finditer(body or ""):
                s0, s1 = max(0, m.start() - a.context), min(len(body), m.end() + a.context)
                print(f"{t} {kind:<9} …{body[s0:s1]}…".replace("\n", " "))


def cmd_workflow(_tr, a) -> None:
    """Per-agent table for a workflow run dir (agent-*.jsonl + *.meta.json + journal.jsonl)."""
    wf = Path(a.transcript)
    results = {}
    j = wf / "journal.jsonl"
    if j.exists():
        for d in _iter_lines(j):
            if d.get("type") == "result":
                results[d.get("agentId")] = d.get("result")
    rows = []
    for f in sorted(wf.glob("agent-*.jsonl")):
        tr = load(f)
        d = digest(tr)
        u = d["usage"]
        r = results.get(tr.agent_id) or {}
        score = "/".join(str(r[k]) for k in ("functionality", "manufacturability", "aesthetics") if k in r)
        rows.append((d["start"] or "", d["label"] or "?", tr.agent_id, d["wall_min"], d["model_time_min"], d["tool_time_min"],
                     u["api_calls"], u["output"] + u["est_missing_output"], u["thinking"] + u["est_missing_output"], u["cache_read"], u["cache_creation"], u["max_context"],
                     d["images_read"], d["blender_runs"], score or ("done" if r else "running/none")))
    print("(out_tok/think_tok include estimates for calls with no final usage line)\nstart                label        agent              wall  model tools calls   out_tok  think_tok   cache_rd  cache_wr  peak_ctx imgs bl  result")
    for r in sorted(rows):
        print(f"{r[0]:<20} {r[1]:<12} {r[2]:<18} {r[3]:>5} {r[4]:>6} {r[5]:>5} {r[6]:>5} {r[7]:>9,} {r[8]:>10,} {r[9]:>10,} {r[10]:>9,} {r[11]:>9,} {r[12]:>4} {r[13]:>3}  {r[14]}")


# ---------------------------------------------------------------- bench: doc reads, source reads, feature use

# a file of either skill, wherever the checkout lives (the v2 loop read a pinned copy, alex-3d-skills-pin)
SKILL_FILE_RE = re.compile(r"skills/(print-cad-blender|cad-design-review)(?:/([\w./*?-]*))?")
# `cad <sub>` through the wrapper (cad, .../scripts/cad, $CAD, "$PCB/scripts/cad"), and the scripts run by hand
CAD_SUBS = ("build", "check", "q", "py", "rows", "bom", "sheet", "printcheck", "slice")
CAD_VAR_RE = re.compile(r"\b(\w+)=[\"']?[^\s;\"']*/scripts/cad[\"']?(?=[\s;&|]|$)")
CAD_SCRIPT_RE = re.compile(r"\b(cadcheck|cadq|cadrows|cadbom|printcheck|cadslice)\.py\b")
CAD_SCRIPT_SUB = {"cadcheck": "check", "cadq": "q", "cadrows": "rows", "cadbom": "bom", "printcheck": "printcheck", "cadslice": "slice"}

ONLY_RE = re.compile(r"--only[ =]([\w,]+)")
CADLIB_CALL_RE = re.compile(r"\b(G|F|A|E|R|geom|features|asm|export|render)\.(\w+)\s*\(")
CADLIB_ALIAS = {"G": "geom", "F": "features", "A": "asm", "E": "export", "R": "render"}
# a key written as a dict literal, or a subscript that is appended to or assigned (reading a report doesn't count)
JSON_KEY_RE = re.compile(r"[\"'](\w+)[\"']\s*:|\[\s*[\"'](\w+)[\"']\s*\]\s*(?:\.append|\.extend|\.insert|\.update|=(?!=))")
CONFIG_FILE_RE = re.compile(r"(checks|review_rows|overlay)\w*\.json")
READERS = {"cat", "sed", "head", "tail", "grep", "rg", "awk", "less", "nl", "bat", "egrep"}
PATTERN_FIRST = {"grep", "rg", "egrep", "sed", "awk"}
# words that may stand before the command itself: `nice -n 10 cad check`, `time $CAD q`, `do $CQ q ...`
CMD_PREFIX = {"nice", "time", "env", "command", "exec", "then", "do", "else", "!", "{", "nohup"}
SEG_SPLIT_RE = re.compile(r"\n|;|&&|\|\||\||\$\(|`|\(|\)")
REDIR_RE = re.compile(r"^(?:\d*|&)(?:>>?|<<?)&?")
TMP_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/", "$TMPDIR", "${TMPDIR")
HEREDOC_START_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")
BENCH_DIR = Path(__file__).resolve().parents[1] / "bench"
REPO = Path(__file__).resolve().parents[2]


def chars_per_token() -> tuple[float, str]:
    """The chars/token ratio measured on these transcripts (`calibrate --write` -> tools/bench/tokens.json), else 4."""
    p = BENCH_DIR / "tokens.json"
    try:
        d = json.loads(p.read_text())
        return float(d["chars_per_token"]), "tools/bench/tokens.json (%s, n %s)" % (d.get("measured_on", "?"), d.get("n", "?"))
    except Exception:
        return 4.0, "default 4.0: tools/bench/tokens.json missing (run cc_transcript.py calibrate --write)"


def strip_heredocs(cmd: str) -> str:
    """The command with heredoc bodies removed (header lines kept): a script or note written to a file is not a command.
    Bodies fed to a shell (`sh <<EOF`) are kept, they run."""
    out, lines, i = [], cmd.split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        out.append(ln)
        m = HEREDOC_START_RE.search(ln)
        i += 1
        if m and not re.search(r"\b(?:sh|bash|zsh)\s*(?:-s\s*)?<<", ln):
            tag = m.group(2)
            while i < len(lines) and lines[i].strip() != tag:
                i += 1
            i += 1
    return "\n".join(out)


def _segments(cmd: str) -> list[list[str]]:
    """Token lists of the simple commands in a Bash command (heredoc bodies and comments dropped)."""
    import shlex
    segs = []
    for seg in SEG_SPLIT_RE.split(strip_heredocs(cmd)):
        try:
            toks = shlex.split(seg, comments=True)
        except ValueError:
            toks = seg.split("#", 1)[0].split()
        if toks:
            segs.append(toks)
    return segs


def _command_words(toks: list[str], env: dict) -> list[str]:
    """Tokens from the command word on: VAR= assignments (recorded in env), nice/time/env/... prefixes skipped."""
    i = 0
    while i < len(toks):
        t = toks[i]
        if re.match(r"^\w+=", t):
            k, v = t.split("=", 1)
            env[k] = v
            i += 1
        elif t in CMD_PREFIX:
            i += 1
            if t == "nice" and i < len(toks) and toks[i] == "-n":
                i += 2
            elif t == "nice" and i < len(toks) and re.match(r"^-\d+$", toks[i]):
                i += 1
        elif t == "timeout" and i + 1 < len(toks):
            i += 2
        else:
            break
    return toks[i:]


def cad_calls(cmd: str) -> tuple[list[str], list[str], list[str]]:
    """(cad subcommands, cad q commands, --only sections) the Bash command actually runs: the cad word must stand in
    command position (`cad`, `.../scripts/cad`, `$CAD`, `sh .../cad`, or any variable the command sets to a cad path,
    as v2 builders wrote `Q=.../scripts/cad; $Q q model.blend list ...`). Heredoc bodies written to files, comments and
    prose in quoted strings don't count. `cad q` with no command (its help) counts as a `q` run, not a q command."""
    names = {"CAD"} | set(CAD_VAR_RE.findall(cmd))
    subs, qs, only, env = [], [], [], {}
    for toks in _segments(cmd):
        w = _command_words(toks, env)
        if w and w[0] in ("sh", "bash") and len(w) > 1:
            w = w[1:]
        if not w:
            continue
        var = re.match(r"^\$\{?(\w+)\}?$", w[0])
        if var and "/scripts/cad" in env.get(var.group(1), ""):     # Q=".../scripts/cad q model.blend"; $Q ray ...
            w = env[var.group(1)].split() + w[1:]
            var = None
        head = w[0]
        is_cad = head == "cad" or head.endswith("/scripts/cad") or bool(var and var.group(1) in names)
        if is_cad and len(w) > 1 and w[1] in CAD_SUBS:
            subs.append(w[1])
            if w[1] == "q" and len(w) > 3 and re.match(r"^[a-z]+$", w[3]):
                qs.append(w[3])
            only += [x for i, t in enumerate(w) for x in ((w[i + 1] if t == "--only" and i + 1 < len(w) else
                                                            t[7:] if t.startswith("--only=") else "").split(",")) if x]
        elif not is_cad:
            # a script run by hand under Blender: `Blender -b x.blend --python .../cadcheck.py -- ...`
            for i, t in enumerate(w):
                if t == "--python" and i + 1 < len(w):
                    m = CAD_SCRIPT_RE.search(w[i + 1])
                    if m:
                        subs.append(CAD_SCRIPT_SUB[m.group(1)])
    return subs, qs, only


def _expand(tok: str, env: dict) -> str:
    return re.sub(r"\$\{?(\w+)\}?", lambda m: env.get(m.group(1), m.group(0)), tok)


def _join(cwd: str | None, p: str) -> str:
    return p if p.startswith(("/", "~", "$")) or cwd is None else cwd.rstrip("/") + "/" + p


def bash_reads(cmd: str) -> list[tuple[str, str, bool]]:
    """(path, program, recursive) for each path a Bash command hands to cat/sed/head/grep/...; `cd X` and VAR=/path
    assignments are followed, redirections (`2>/dev/null`, `> out`) and the pattern of grep/sed/awk are dropped. Any
    argument may still be junk (`40` of `head -n 40`); `resolve` keeps only real files of the skill tree."""
    cwd, env, out = None, {}, []
    for toks in _segments(cmd):
        toks = [_expand(t, env) for t in toks]
        w = _command_words(toks, env)
        env = {k: _expand(v, env) for k, v in env.items()}
        if not w:
            continue
        if w[0] == "cd" and len(w) > 1:
            cwd = _join(cwd, w[1]) if not w[1].startswith(("/", "~")) else w[1]
            continue
        prog = w[0].rsplit("/", 1)[-1]
        if prog not in READERS:
            continue
        args, skip = [], False
        for t in w[1:]:
            if skip:
                skip = False
                continue
            if REDIR_RE.match(t):
                skip = REDIR_RE.sub("", t) == ""     # `> file`: the file is the next token
                continue
            if t.startswith("-"):
                continue
            args.append(t)
        if prog in PATTERN_FIRST and args and not any(t in ("-e", "-f") for t in w[1:]):
            args = args[1:]
        rec = prog == "rg" or (prog in ("grep", "egrep") and any(
            t in ("--recursive", "-R") or (re.match(r"^-[A-Za-z]+$", t) and ("r" in t or "R" in t)) for t in w[1:]))
        for t in args:
            out.append((_join(cwd, t), prog, rec))
    return out


class SkillTree:
    """The skills/ tree at a git ref (an agent's tools pin): file sizes, and file text on demand for content matching."""
    _cache: dict = {}

    def __init__(self, ref: str):
        self.ref = ref
        self.files, self.dirs = {}, set()
        try:
            out = subprocess.run(["git", "-C", str(REPO), "ls-tree", "-r", "-l", ref, "--", "skills"],
                                 capture_output=True, text=True, check=True).stdout
        except Exception:
            out = ""
        for ln in out.splitlines():
            meta, path = ln.split("\t", 1)
            parts = path.split("/")
            if len(parts) < 3 or "__pycache__" in parts:
                continue
            self.files[(parts[1], "/".join(parts[2:]))] = int(meta.split()[3])
            for k in range(2, len(parts)):
                self.dirs.add((parts[1], "/".join(parts[2:k])))
        self._text, self._lines = {}, {}

    @classmethod
    def at(cls, ref: str) -> "SkillTree":
        if ref not in cls._cache:
            cls._cache[ref] = cls(ref)
        return cls._cache[ref]

    def text(self, key: tuple) -> str:
        if key not in self._text:
            r = subprocess.run(["git", "-C", str(REPO), "show", "%s:skills/%s/%s" % (self.ref, key[0], key[1])],
                               capture_output=True, text=True)
            self._text[key] = r.stdout if r.returncode == 0 else ""
        return self._text[key]

    def lines(self, key: tuple) -> set:
        if key not in self._lines:
            self._lines[key] = {l.strip() for l in self.text(key).splitlines() if l.strip()}
        return self._lines[key]

    def resolve(self, path: str, recursive: bool = False) -> list[tuple]:
        """Skill files (skill, rel) a path names: the file, a glob's matches, or (recursive) every file under a
        directory. Paths that aren't real at this ref give nothing (`.`, `/2` of `2>/dev/null`, `../..`, `head -n 40`)."""
        import fnmatch
        import posixpath
        m = SKILL_FILE_RE.search(posixpath.normpath(path or ""))
        if not m:
            return []
        skill, rel = m.group(1), posixpath.normpath(m.group(2) or ".")
        rel = "" if rel == "." else rel
        if rel.startswith(".."):
            return []
        if any(c in rel for c in "*?"):
            return sorted(k for k in self.files if k[0] == skill and fnmatch.fnmatch(k[1], rel))
        if (skill, rel) in self.files:
            return [(skill, rel)]
        if (skill, rel) in self.dirs and recursive:
            return sorted(k for k in self.files if k[0] == skill and (not rel or k[1].startswith(rel + "/")))
        return []


def kind_of(key: tuple) -> str:
    return "doc" if key[1].endswith(".md") else "source"


LINENO_RE = re.compile(r"^\s*\d+(?:[:\t-]|→)")


def attribute(tc: "ToolCall", keys: list, tree: SkillTree) -> tuple[dict, str]:
    """({file: result chars that came from it}, method). A Read result is its file's. Otherwise each result line goes
    to the file whose text has it (after a grep `path:` / line-number prefix), blank lines to the file of the line
    before: a multi-file `cat` that stopped part way (V2R7 call #0: `echo =====` failed in zsh after the first file)
    credits only what was printed, and other output in the same call (wc, git log) credits no file. When no line
    matches (the agent read another checkout than the pin), the result is split evenly ('even')."""
    if tc.name == "Read" and len(keys) == 1:
        return {keys[0]: tc.result_chars}, "read"
    got = {k: 0 for k in keys}
    prev = None
    for ln in tc.result_text.splitlines():
        s = ln.strip()
        if not s:
            if prev is not None:
                got[prev] += 1
            continue
        hit = None
        pm = re.match(r"^(\S+?\.\w+):(?:\d+[:-])?", ln)
        if pm:
            hit = next((k for k in keys if pm.group(1) == k[1] or pm.group(1).endswith("/" + k[1])), None)
            if hit:
                s = ln[pm.end():].strip()
        if hit is None:
            s2 = LINENO_RE.sub("", ln, count=1).strip()
            for cand in ([prev] if prev else []) + keys:
                if s in tree.lines(cand) or (s2 and s2 in tree.lines(cand)):
                    hit = cand
                    break
        if hit is not None:
            got[hit] += len(ln) + 1
        prev = hit
    if sum(got.values()) == 0 and tc.result_chars:
        return {k: tc.result_chars / len(keys) for k in keys}, "even"
    return got, "content"


def _design_write(path: str, cmd: str | None = None) -> bool:
    """A write to the design project: not a temp-dir probe and not into a skills checkout. Heredoc paths are expanded
    with the command's own VAR= assignments and its last `cd` before the heredoc."""
    p = path or ""
    if cmd is not None:
        pos = cmd.find(p)
        env, cwd = {}, None
        for toks in _segments(cmd[:pos] if pos > 0 else ""):
            toks = [_expand(t, env) for t in toks]
            w = _command_words(toks, env)
            if w and w[0] == "cd" and len(w) > 1:
                cwd = _join(cwd, w[1]) if not w[1].startswith(("/", "~")) else w[1]
        p = _join(cwd, _expand(p, env))
    if p.startswith(TMP_PREFIXES) or "/tmp/" in p[:12]:
        return False
    if re.search(r"skills/(print-cad-blender|cad-design-review)/|alex-3d-skills", p):
        return False
    return True


def first_design_edit(tr: Transcript) -> int | None:
    """Index of the first .py/.json write to the design project (a /tmp probe script is not the first edit)."""
    for tc in tr.tools:
        i = tc.input
        if tc.name in ("Write", "Edit"):
            p = i.get("file_path", "")
            if re.search(r"\.(py|json)$", p) and _design_write(p):
                return tc.idx
        elif tc.name == "Bash":
            cmd = i.get("command", "")
            for m in HEREDOC_RE.finditer(cmd):
                if re.search(r"\.(py|json)$", m.group(1)) and _design_write(m.group(1), cmd):
                    return tc.idx
    return None


def _written(tc: ToolCall) -> list[tuple[str, str]]:
    """(path or '<bash>', text) the call wrote or executed: Write content, Edit new_string, heredocs, the Bash command."""
    i = tc.input
    if tc.name == "Write":
        return [(i.get("file_path", ""), i.get("content", ""))]
    if tc.name == "Edit":
        return [(i.get("file_path", ""), i.get("new_string", ""))]
    if tc.name == "Bash":
        cmd = i.get("command", "")
        return [(m.group(1), m.group(3)) for m in HEREDOC_RE.finditer(cmd)] + [("<bash>", cmd)]
    return []


def reads_of(tc: ToolCall, tree: SkillTree) -> list[tuple]:
    """Skill files a call read (resolved at the agent's pin)."""
    if tc.name == "Read":
        return tree.resolve(tc.input.get("file_path", ""))
    if tc.name == "Grep":
        return tree.resolve(tc.input.get("path", ""), recursive=True)
    if tc.name == "Bash":
        keys = []
        for p, prog, rec in bash_reads(tc.input.get("command", "")):
            keys += [k for k in tree.resolve(p, rec) if k not in keys]
        return keys
    return []


def bench_digest(tr: Transcript, tree: SkillTree | None = None, cpt: float | None = None) -> dict:
    """Per-agent cost telemetry for tools/bench: skill doc tokens read before the first design edit (by file), tool and
    library source reads (doc gaps), failed cad/Blender runs, and the cad subcommands, cad q commands, --only sections,
    config keys and cadlib functions the agent used. Reads resolve against the skills tree at the agent's tools pin
    (tree; HEAD when it had none) and result characters are credited per file by content (`attribute`). Tokens are
    characters / cpt, the ratio measured by `calibrate` (tools/bench/tokens.json)."""
    from collections import Counter, defaultdict
    tree = tree or SkillTree.at("HEAD")
    cpt = cpt or chars_per_token()[0]
    first_edit = first_design_edit(tr)
    docs_before, docs_all, src = defaultdict(float), defaultdict(float), defaultdict(float)
    src_calls, methods, reads_log = [], Counter(), []
    for tc in tr.tools:
        keys = reads_of(tc, tree)
        if not keys:
            continue
        got, how = attribute(tc, keys, tree)
        methods[how] += 1
        methods["files_not_in_result"] += sum(1 for v in got.values() if not v)
        for k, ch in got.items():
            if not ch:
                continue
            key = "%s/%s" % k
            tok = ch / cpt
            if len(reads_log) < 80:
                reads_log.append({"idx": tc.idx, "file": key, "chars": int(ch), "method": how})
            if kind_of(k) == "doc":
                docs_all[key] += tok
                if first_edit is None or tc.idx < first_edit:
                    docs_before[key] += tok
            else:
                src[key] += tok
                src_calls.append(tc.idx)
    cad_sub, cadq, only, keys, funcs = Counter(), Counter(), Counter(), Counter(), Counter()
    cad_runs, cad_failed = 0, []
    for tc in tr.tools:
        if tc.name == "Bash":
            cmd = tc.input.get("command", "")
            subs, qs, onl = cad_calls(cmd)
            for s in set(subs):
                cad_sub[s] += 1
            for q in set(qs):
                cadq[q] += 1
            for o in set(onl):
                only[o] += 1
            if subs or is_blender(tc):
                cad_runs += 1
                if bash_failed(tc) or "BUILD FAILED" in tc.result_text:
                    cad_failed.append({"idx": tc.idx, "what": tc.brief(80), "err": error_lines(tc.result_text, 2)})
        seen_k, seen_f = set(), set()
        for path, text in _written(tc):
            if CONFIG_FILE_RE.search(path) or (path == "<bash>" and CONFIG_FILE_RE.search(text)):
                seen_k |= {a or b for a, b in JSON_KEY_RE.findall(text)}
                if re.search(r":\s*\"=", text):
                    seen_k.add("=EXPR")
            if path.endswith(".py") or path == "<bash>":
                seen_f |= {"%s.%s" % (CADLIB_ALIAS.get(m, m), f) for m, f in CADLIB_CALL_RE.findall(text)}
        keys.update(seen_k)
        funcs.update(seen_f)
    r1 = lambda d: {k: int(round(v)) for k, v in sorted(d.items(), key=lambda x: -x[1])}
    u = usage_totals(tr)
    return {"agent_id": tr.agent_id, "label": tr.label, "wall_min": round(((tr.t_end or 0) - (tr.t_start or 0)) / 60, 1),
            "output_tokens": u["output"] + u["est_missing_output"], "tool_calls": len(tr.tools),
            "tools_ref": tree.ref, "chars_per_token": cpt, "first_edit_idx": first_edit,
            "doc_tokens_before_edit": int(round(sum(docs_before.values()))), "docs_before_edit": r1(docs_before),
            "doc_tokens_total": int(round(sum(docs_all.values()))), "docs_total": r1(docs_all),
            "source_read_calls": len(set(src_calls)), "source_read_tokens": int(round(sum(src.values()))), "source_reads": r1(src),
            "read_methods": dict(methods), "reads": reads_log,
            "cad_runs": cad_runs, "cad_failed": len(cad_failed), "cad_failed_list": cad_failed[:12],
            "cad_subcommands": dict(cad_sub), "cadq_commands": dict(cadq), "only_sections": dict(only),
            "config_keys": dict(keys), "cadlib_functions": dict(funcs)}


def bench_targets(a) -> tuple[list[dict], dict]:
    """[{name, attempt, role, file, pin}] from --agents (or the transcripts given), and the agents spec."""
    targets, spec = [], {"pins": {}}
    if getattr(a, "transcript", None):
        for t in a.transcript:
            p = Path(t).expanduser()
            for f in (sorted(p.glob("agent-*.jsonl")) if p.is_dir() else [p]):
                targets.append({"name": f.stem, "attempt": None, "role": None, "file": f, "pin": None})
    else:
        spec = json.load(open(a.agents))
        root = Path(spec["wf_root"]).expanduser()
        for g in spec["agents"]:
            if getattr(a, "attempt", None) and g["attempt"] not in a.attempt.split(","):
                continue
            targets.append({**g, "file": root / g["path"], "pin": spec.get("pins", {}).get(g["attempt"])})
    return targets, spec


def cmd_bench(_tr, a) -> None:
    """Per-agent bench telemetry for the agents in tools/bench/agents.json (or the transcripts / workflow dirs given)."""
    targets, _ = bench_targets(a)
    cpt, src = chars_per_token()
    rows = []
    for t in targets:
        if not Path(t["file"]).exists():
            rows.append({k: v for k, v in t.items() if k not in ("file", "path")} | {"missing": str(t["file"])})
            continue
        d = bench_digest(load(t["file"]), SkillTree.at(t["pin"] or "HEAD"), cpt)
        rows.append({k: v for k, v in t.items() if k not in ("file", "path")} | d)
    if a.json:
        print(json.dumps(rows, indent=1))
        return
    print("tokens = chars / %.2f (%s); reads resolved at each attempt's tools pin (v1: HEAD), credited by content" % (cpt, src))
    print("agent        attempt role      wall  out_tok  doc_tok<edit  doc_tok  src_reads(tok)  cad runs/failed  subcommands")
    for r in rows:
        if "missing" in r:
            print("%-12s %-7s MISSING %s" % (r["name"], r.get("attempt"), r["missing"]))
            continue
        print("%-12s %-7s %-8s %5.1f %8d %13d %8d %5d (%6d) %8d/%-6d  %s" % (
            r["name"], r.get("attempt") or "-", r.get("role") or "-", r["wall_min"], r["output_tokens"], r["doc_tokens_before_edit"],
            r["doc_tokens_total"], r["source_read_calls"], r["source_read_tokens"], r["cad_runs"], r["cad_failed"],
            " ".join("%s:%d" % kv for kv in sorted(r["cad_subcommands"].items()))))


def _ctx(u: dict) -> int:
    return sum((u or {}).get(k, 0) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))


def calibration(targets: list[dict], min_chars: int = 2000, min_doc_share: float = 0.9) -> dict:
    """Chars per token of skill-doc tool results, from the usage the API reported. For an API call that made exactly one
    tool call, the next call's context (input + cache write + cache read) minus this call's is this call's output plus
    the tool result: result tokens = delta - output_tokens. Thinking tokens count in that output: on calls with a tiny
    result, delta equals output_tokens including thinking (within the tool loop the thinking blocks stay in context).
    Only calls whose result is >= min_chars and >= min_doc_share skill-doc text (by content) are used; calls without
    their final usage line (incomplete) are skipped."""
    import statistics
    samples = []
    for t in targets:
        if not Path(t["file"]).exists():
            continue
        tr = load(t["file"])
        tree = SkillTree.at(t.get("pin") or "HEAD")
        inc = {id(ac) for ac, _ in incomplete_usage(tr)}
        tools = {tc.id: tc for tc in tr.tools}
        for i, ac in enumerate(tr.api_calls[:-1]):
            nx = tr.api_calls[i + 1]
            if len(ac.tool_ids) != 1 or id(ac) in inc or id(nx) in inc or not ac.usage or not nx.usage:
                continue
            tc = tools.get(ac.tool_ids[0])
            if tc is None or tc.result_chars < min_chars or tc.images:
                continue
            keys = [k for k in reads_of(tc, tree) if kind_of(k) == "doc"]
            if not keys:
                continue
            got, how = attribute(tc, keys, tree)
            doc = sum(got.values())
            if how == "even" or doc < min_doc_share * tc.result_chars:
                continue
            res_tok = _ctx(nx.usage) - _ctx(ac.usage) - (ac.usage.get("output_tokens") or 0)
            if res_tok <= 0:
                continue
            samples.append({"agent": t["name"], "idx": tc.idx, "tool": tc.name, "chars": tc.result_chars, "tokens": res_tok,
                            "ratio": round(tc.result_chars / res_tok, 3), "files": ["%s/%s" % k for k, v in got.items() if v]})
    r = sorted(s["ratio"] for s in samples)
    if not r:
        return {"n": 0}
    q = statistics.quantiles(r, n=4) if len(r) >= 4 else [r[0], statistics.median(r), r[-1]]
    pooled = sum(s["chars"] for s in samples) / sum(s["tokens"] for s in samples)
    return {"chars_per_token": round(statistics.median(r), 2), "pooled": round(pooled, 2), "iqr": [round(q[0], 2), round(q[2], 2)],
            "range": [r[0], r[-1]], "n": len(r), "method": "median of per-call ratios, result chars / result tokens from the API usage of consecutive calls",
            "rule": "result tokens = next call (input + cache_creation + cache_read) - this call's - this call's output_tokens "
                    "(thinking included: it stays in context within the tool loop)",
            "filter": "single-tool API calls, complete usage, result >= %d chars, >= %d%% of it skill-doc text by content" % (min_chars, 100 * min_doc_share),
            "measured_on": "%d agents of tools/bench/agents.json" % len({s["agent"] for s in samples}), "samples": samples}


def cmd_calibrate(_tr, a) -> None:
    """Measure chars/token on skill-doc reads from the transcripts' own usage numbers (tools/bench/tokens.json)."""
    targets, _ = bench_targets(a)
    c = calibration(targets)
    if not c["n"]:
        print("calibrate: no usable samples")
        return
    print("chars/token on skill-doc tool results: median %.2f, IQR %.2f-%.2f, range %.2f-%.2f, pooled %.2f, n %d (%s)" % (
        c["chars_per_token"], c["iqr"][0], c["iqr"][1], c["range"][0], c["range"][1], c["pooled"], c["n"], c["measured_on"]))
    print("rule: " + c["rule"])
    print("filter: " + c["filter"])
    # thinking check: calls with a tiny result and much thinking; delta vs output with and without thinking
    if a.json:
        print(json.dumps(c, indent=1))
    if a.write:
        out = {k: v for k, v in c.items() if k != "samples"}
        out["samples_head"] = c["samples"][:10]
        (BENCH_DIR / "tokens.json").write_text(json.dumps(out, indent=1) + "\n")
        print("wrote %s" % (BENCH_DIR / "tokens.json"))


def _iter_lines(path):
    with open(path, "rb") as fh:
        for raw in fh:
            try:
                yield json.loads(raw)
            except Exception:
                continue


def cmd_json(tr: Transcript, a) -> None:
    print(json.dumps(digest(tr), indent=1))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bench", help="per-agent doc/source reads, failed cad runs and feature use (tools/bench)")
    b.add_argument("transcript", nargs="*", help="agent-*.jsonl or workflow dirs; default: the agents in --agents")
    b.add_argument("--agents", default=str(Path(__file__).resolve().parents[1] / "bench" / "agents.json"))
    b.add_argument("--attempt", help="comma list of attempts from --agents (a1, v2a3, ...)")
    b.add_argument("--json", action="store_true")
    c = sub.add_parser("calibrate", help="chars/token of skill-doc reads from the transcripts' usage (tools/bench/tokens.json)")
    c.add_argument("transcript", nargs="*", help="agent-*.jsonl or workflow dirs; default: the agents in --agents")
    c.add_argument("--agents", default=str(Path(__file__).resolve().parents[1] / "bench" / "agents.json"))
    c.add_argument("--attempt", help="comma list of attempts from --agents")
    c.add_argument("--json", action="store_true", help="also print every sample")
    c.add_argument("--write", action="store_true", help="save the ratio to tools/bench/tokens.json (doccost, bench and features use it)")
    for name in ("summary", "timeline", "bash", "files", "images", "renders", "usage", "json", "show", "thinking", "grep",
                 "workflow"):
        s = sub.add_parser(name)
        s.add_argument("transcript", help="agent-*.jsonl (or a workflow run dir for `workflow`)")
        if name == "thinking":
            s.add_argument("--min-s", type=float, default=120)
            s.add_argument("--chars", type=int, default=1500)
        if name == "grep":
            s.add_argument("pattern")
            s.add_argument("--context", type=int, default=120)
        if name == "bash":
            s.add_argument("--errors", action="store_true", help="only failed commands")
        if name == "show":
            s.add_argument("which", help="tool_use id or index (#N in other views)")
            s.add_argument("--max", type=int, default=6000)
    a = p.parse_args(argv)
    tr = None if a.cmd in ("workflow", "bench", "calibrate") else load(a.transcript)
    globals()["cmd_" + a.cmd](tr, a)


if __name__ == "__main__":
    main()
