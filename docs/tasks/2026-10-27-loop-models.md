# Task: choose the model per role in the design loop

Branch `feat/loop-models`, worktree `.claude/worktrees/loop-models`. PR target `next` (the coordinator opens it).

## Why
On 2026-10-27 the pan-tilt assembly task (`tools/bench/mates_task_v2` on feat/mate-connectors) was run with three models, using the
same prompt and scorer (24 interface, pose and clearance rows):

| model | rows right | active min | $/run |
|---|---|---|---|
| Opus 5.5 | 24, 24, 24 | 5.8–6.7 | 0.94–1.21 |
| Sonnet 5.5 | 24, 24 | 5.3–5.6 | 0.53–0.65 |
| Haiku 5.5 | 24, 23 | 15–17 | about 0.42 |

Sonnet matched Opus at about half the cost. Haiku was slower, made more errors, and its savings were small because it used 5–7x the
tokens. The user's decision: builders run on Sonnet 5.5, and planning, finishing and review stay on the session's model (Opus),
where the judgment calls are.

## Build
1. `templates/cad-loop.workflow.js`: add `CONFIG.models = {plan, build, finish, review}`, with defaults
   `{plan: null, build: 'sonnet', finish: null, review: null}`. `null` means the workflow's default model. Pass each one to its
   `agent()` call. Check the Workflow script API for the exact option name and allowed values: load the `workflow-authoring`
   skill and read its agent() options. Don't guess. If agent() can't take a model, stop and report that instead.
2. Update `tools/test_workflow_template.py` so the dry run asserts the model each role is given, including an override through
   `args`.
3. Add a short line to the README row for the template (and to the header comment) saying how to set models.
4. Run `sh tools/verify_all.sh --changed` (on next). Commit in the repo's style, ending with
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Push the branch to origin. Don't open a PR, don't merge, don't
   touch other worktrees, and don't spawn agents.

Report: the option name you found and where it's documented, the diff summary, the test result, and the commit SHA.
