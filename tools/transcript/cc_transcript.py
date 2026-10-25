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
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

BLENDER_RE = re.compile(r"(Blender(\.app)?/Contents/MacOS/Blender|\bblender\b\s+-b|\$BLENDER|\bBL\b\s+-b)", re.I)
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
    tr = None if a.cmd == "workflow" else load(a.transcript)
    globals()["cmd_" + a.cmd](tr, a)


if __name__ == "__main__":
    main()
