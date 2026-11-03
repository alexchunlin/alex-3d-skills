# Transcript extractors

`cc_transcript.py` digests Claude Code agent transcripts (`agent-*.jsonl`, ~10 MB each) so you never
read one whole. Standard library only; run with `python3 -I`.

```sh
WF=~/.claude/projects/<project>/<session>/subagents/workflows/wf_XXXX
python3 -I tools/transcript/cc_transcript.py workflow $WF                 # one row per agent: wall, tokens, images, result
python3 -I tools/transcript/cc_transcript.py summary  $WF/agent-ID.jsonl  # time split, long generations, files, failures
python3 -I tools/transcript/cc_transcript.py timeline $WF/agent-ID.jsonl  # every tool call with the model time before it
python3 -I tools/transcript/cc_transcript.py usage    $WF/agent-ID.jsonl  # tokens per API call (cache misses show as cache_r 0)
python3 -I tools/transcript/cc_transcript.py thinking $WF/agent-ID.jsonl --min-s 300   # what the long thinking was about
python3 -I tools/transcript/cc_transcript.py bash     $WF/agent-ID.jsonl --errors
python3 -I tools/transcript/cc_transcript.py images|renders|files $WF/agent-ID.jsonl
python3 -I tools/transcript/cc_transcript.py grep     $WF/agent-ID.jsonl 'tilt sweep'
python3 -I tools/transcript/cc_transcript.py show     $WF/agent-ID.jsonl 43           # full input/output of tool call #43
python3 -I tools/transcript/cc_transcript.py handoffs agent-*.jsonl           # agents whose LAST `cad check` was --only/--quick (cadcheck issue #28)
python3 -I tools/transcript/cc_transcript.py bench    [--attempt v2a7] [--json]       # tools/bench tier 2: doc/source reads, feature use
python3 -I tools/transcript/cc_transcript.py calibrate [--write] [--json]             # chars/token of doc reads, from the usage numbers
```

`bench` reads the agents in `tools/bench/agents.json` (or the transcripts given): skill-doc tokens read before the first
`.py`/`.json` write to the design project (a /tmp probe is not the first edit), cadcheck/cadlib source reads, failed cad
runs, and the cad subcommands, `cad q` commands, `--only` sections, checks.json keys and cadlib calls each agent used.
See `tools/bench/README.md`.
- **Which files a call read** resolves against the skills tree at the agent's tools pin (`agents.json` pins; v1 had none:
  HEAD), so `.`, `/2` (of `2>/dev/null`), `../..` and other non-files drop out, globs and a recursive grep's bare
  directory (`grep -rn x reference SKILL.md`) expand to the pin's files.
- **How much of the result each file gets** is matched by content: every result line goes to the pin file containing it
  (after a grep `path:` or line-number prefix), so a multi-file `cat` that stopped part way (V2R7 call #0: `echo =====`
  failed in zsh after the first file) credits only the file printed, and unrelated output in the same call credits none.
  When nothing matches (another checkout than the pin) the result is split evenly; `read_methods` counts each method.
- **cad uses** count only commands in command position (after `;`, `&&`, `|`, `(`, `$(`, newlines, `VAR=`, `nice`,
  `time`, `do`; including variables set to a cad path), never prose: heredoc bodies written to files and comments are
  dropped first.
- **tokens** are characters / the ratio `calibrate` measured (`tools/bench/tokens.json`): for an API call that made one
  tool call, the next call's context (input + cache write + cache read) minus this call's, minus this call's
  `output_tokens`, is the result's tokens. Thinking stays in that output: on 71 calls with a tiny result and > 1000
  thinking tokens, the context grew by output_tokens + 94 (median), not by output minus thinking. On 29 skill-doc reads
  (>= 2000 chars, >= 90% doc text) the median is 2.25 chars/token (IQR 2.08-2.54, range 1.39-2.66), not 4.

How the numbers are computed:
- **model time** of an API call = previous event (tool result or prompt) to the last streamed block of
  that call. This includes thinking, text and streaming the tool input (a 78 KB `Write` takes ~5 min).
- **tool time** = tool_use timestamp to tool_result timestamp.
- **tokens** come from `message.usage` of the last line of each `requestId` (lines are per content block
  and repeat the usage). `cache_r 0` with a large `cache_w` on a later call means the prompt cache
  expired (5 min TTL) during a long generation and the whole context was re-written.
- **incomplete calls**: a call whose stream ended without its final usage line keeps the streaming-start usage
  (`output_tokens` about 8, no `output_tokens_details`). `summary` warns and estimates the missing tokens from
  `thinkingDurationMs`, at the rate measured on complete calls (88-95 tok/s on the mm-launcher run); `workflow` adds the
  estimate. D2's 12-min call at 0:36 was one (about 70k tokens, FINDINGS A2-T5).
- **images** are the bytes actually sent to the model (the Read tool downsizes PNGs; a 2 MB render
  arrives as ~100-170 KB).
- **Blender runs** are Bash calls whose command invokes the Blender binary.
