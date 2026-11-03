export const meta = {
  name: 'cad-design-loop',
  description: 'Design/review loop for a printable Blender assembly: plan, build per subsystem, finish, independent review; resumable from attempt N',
  whenToUse: 'Iterating a cadlib/Blender printable assembly against a design brief until review scores reach the target',
  phases: [
    { title: 'Plan', detail: 'designer plans the attempt, updates checks.json, writes progress.md' },
    { title: 'Build', detail: 'one fresh agent per subsystem: edit, build, cad check, fix fails' },
    { title: 'Finish', detail: 'final renders, BOM, design log, evidence summary' },
    { title: 'Review', detail: 'independent reviewer with cad-design-review' },
  ],
}

// ---------------------------------------------------------------------------------------------
// Template. Copy it, edit CONFIG (or pass it as args), and run it with the Workflow tool.
// Why this shape (evidence in alex-3d-skills/docs/FINDINGS.md):
//  - Attempt 1 = one 64 min designer agent: 32 min of upfront thinking plus a single 78 KB Write
//    before the first build, 522k peak context, 19M cache-read tokens (A1-T1, T4, T5). Here each
//    subsystem is a fresh agent with a small context and a short generation.
//  - A killed designer lost 44 min with nothing on disk (A1-T9). Every agent here appends to
//    renders/attempt-N/progress.md and resumes from it. The loop resumes from args.start_attempt.
//  - The designer reported checks_passed=true on partial checks (A1-F14). Schemas here ask for the
//    cadcheck fail/warn counts and coverage, not a boolean.
//  - v2 A1 (the first loop run with this shape): 4 sequential builders took 136.6 of 187.5 min, and each one re-read
//    the same skill, brief and tool source (V2A1-T1). parallel_builds runs them at once, each into its own
//    model.blend, and leaves params.py and checks.json to the planner and the finisher. Off by default until
//    a run has proven it.
//  - Models per role (CONFIG.models, merged per role from args.models): builders run on Sonnet, plan, finish and review
//    on the session's model (null). On the pan-tilt mates task Sonnet got 24/24 rows like Opus at about half the cost;
//    Haiku was slower, missed a row and used 5-7x the tokens. Each value goes to agent()'s opts.model, which the
//    workflow-authoring skill types only as a string and lists no values for; 'sonnet', 'opus' and 'haiku' are the
//    names the Agent tool accepts in this environment (a live Workflow run on 2026-10-27
//    confirmed 'sonnet' -> claude-sonnet-5-5 and an args.models 'haiku' -> claude-haiku-5-5). Bad roles or values throw.
//    Changing a role's model invalidates the resumeFromRunId cache from that role's first agent() call onward.
// No filesystem access in workflow scripts, so state crosses runs through args and files on disk.
// To resume a killed run with cached agents, use Workflow({scriptPath, resumeFromRunId}).
// ---------------------------------------------------------------------------------------------

const CONFIG = Object.assign({
  hw: '/ABS/PATH/project-hw',                 // project root: DESIGN_BRIEF.md, blender/, stl/, renders/
  skills: '~/code-stuff/alex-3d-skills',     // this repo
  subsystems: ['base', 'pan_stage', 'launcher', 'feeder'],   // = parts/<name>.py modules, in build order
  max_attempts: 8,
  target: 9,
  start_attempt: 1,                          // resume: set to the next attempt number
  history: [],                               // resume: [{n, f, m, a}] from earlier runs
  render_budget: 12,                         // preview renders per build agent
  stop_after: 0,                             // >0: stop after this attempt's review
  parallel_builds: false,                    // true: builders run at once; the planner owns params.py (V2A1-T1)
  models: {},                                // per role; see MODELS below
}, typeof args === 'object' && args ? args : {})
// Per-role agent() model; null = the workflow's default (the session model). args.models overrides single roles.
const MODELS = Object.assign({ plan: null, build: 'sonnet', finish: null, review: null }, CONFIG.models)
{
  const m = CONFIG.models, roles = ['plan', 'build', 'finish', 'review']
  const plain = typeof m === 'object' && m !== null && !Array.isArray(m) && Object.prototype.toString.call(m) === '[object Object]'   // not a prototype test: args may come from another JS realm
  if (!plain) throw new Error(`cad-loop: args.models must be an object like {build: 'sonnet'}, got ${JSON.stringify(m)} (${Array.isArray(m) ? 'array' : typeof m})`)
  for (const [k, v] of Object.entries(m)) {
    if (!roles.includes(k)) throw new Error(`cad-loop: args.models has unknown role "${k}"; roles are ${roles.join(', ')}`)
    if (v !== null && (typeof v !== 'string' || !v.trim())) throw new Error(`cad-loop: args.models.${k} must be null (session model) or a model name like 'sonnet', got ${JSON.stringify(v)}`)
  }
}
CONFIG.models = MODELS
const withModel = (role, opts) => MODELS[role] ? { ...opts, model: MODELS[role] } : opts

const HW = CONFIG.hw
const PCB = `${CONFIG.skills}/skills/print-cad-blender`
const REV = `${CONFIG.skills}/skills/cad-design-review`
const CAD = `${PCB}/scripts/cad`
const dir = n => `${HW}/renders/attempt-${n}`

const CHECK_SUMMARY = {
  type: 'object',
  properties: {
    fails: { type: 'integer' }, warns: { type: 'integer' },
    fail_list: { type: 'array', items: { type: 'string' } },
    coverage: { type: 'array', items: { type: 'string' } },
    not_checked: { type: 'array', items: { type: 'string' } },
    run_only: { type: 'array', items: { type: 'string' }, description: "the report's run.only, plus 'quick' when run.quick is true; [] for a full run" },
  },
  required: ['fails', 'warns', 'fail_list', 'coverage', 'not_checked'],
}

const PLAN_SCHEMA = {
  type: 'object',
  properties: {
    plan: { type: 'string', description: 'What this attempt changes and why (<= 200 words)' },
    work: {
      type: 'array', description: 'One entry per subsystem that needs work this attempt, in build order',
      items: {
        type: 'object',
        properties: {
          subsystem: { type: 'string' },
          changes: { type: 'array', items: { type: 'string' }, description: 'Concrete edits with dimensions' },
          review_issues: { type: 'array', items: { type: 'string' }, description: 'Review issues this subsystem closes' },
          acceptance: { type: 'array', items: { type: 'string' }, description: 'cadcheck rows or cad q measurements that prove it' },
        },
        required: ['subsystem', 'changes', 'review_issues', 'acceptance'],
      },
    },
    deferred: { type: 'array', items: { type: 'string' }, description: 'Review issues not addressed, with the reason' },
  },
  required: ['plan', 'work', 'deferred'],
}

const BUILD_SCHEMA = {
  type: 'object',
  properties: {
    subsystem: { type: 'string' },
    done: { type: 'array', items: { type: 'string' } },
    not_done: { type: 'array', items: { type: 'string' } },
    check: CHECK_SUMMARY,
  },
  required: ['subsystem', 'done', 'not_done', 'check'],
}

const FINISH_SCHEMA = {
  type: 'object',
  properties: {
    summary: { type: 'string' },
    addressed: { type: 'array', items: { type: 'string' } },
    deferred: { type: 'array', items: { type: 'string' } },
    printed_parts: { type: 'array', items: { type: 'string' } },
    check: CHECK_SUMMARY,
    render_dir: { type: 'string' },
  },
  required: ['summary', 'addressed', 'deferred', 'printed_parts', 'check', 'render_dir'],
}

const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    functionality: { type: 'integer', minimum: 1, maximum: 10 },
    manufacturability: { type: 'integer', minimum: 1, maximum: 10 },
    aesthetics: { type: 'integer', minimum: 1, maximum: 10 },
    anchors: { type: 'object', properties: { functionality: { type: 'string' }, manufacturability: { type: 'string' }, aesthetics: { type: 'string' } }, required: ['functionality', 'manufacturability', 'aesthetics'] },
    issues: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string', description: 'stable id, e.g. A2-03; reuse the previous id for a recurring issue' },
          metric: { type: 'string', enum: ['functionality', 'manufacturability', 'aesthetics'] },
          severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
          subsystem: { type: 'string' },
          problem: { type: 'string' },
          evidence: { type: 'string', description: 'cadcheck row, cad q JSON line, or render path' },
          fix: { type: 'string' },
          tool_catchable: { type: 'boolean', description: 'could cadcheck/cadq have caught this before review?' },
        },
        required: ['id', 'metric', 'severity', 'subsystem', 'problem', 'evidence', 'fix', 'tool_catchable'],
      },
    },
    previous_issue_status: {
      type: 'array',
      items: { type: 'object', properties: { id: { type: 'string' }, status: { type: 'string', enum: ['FIXED', 'PARTIAL', 'NOT FIXED'] }, evidence: { type: 'string' } }, required: ['id', 'status', 'evidence'] },
    },
    check_config_disputes: { type: 'array', items: { type: 'string' } },
  },
  required: ['functionality', 'manufacturability', 'aesthetics', 'anchors', 'issues', 'previous_issue_status', 'check_config_disputes'],
}

const common = n => `
Project: ${HW} (brief: ${HW}/DESIGN_BRIEF.md). Attempt ${n}. Skill: read ${PCB}/SKILL.md and follow its conventions;
cadlib API in ${PCB}/reference/api.md; check config in ${PCB}/reference/checks-config.md; purchased-part data in
${CONFIG.skills}/components/components.json (use it instead of re-deriving dimensions from the PNGs).
Tools: ${CAD} build|check|q|py|rows|bom|sheet (Blender starts in under 1 s; run checks freely). Read reports with
${CAD} rows cadcheck.json REGEX (or manifest.json), not json.load snippets (V2A3-T1). Answer tool questions from the
reference docs before opening cadlib/cadcheck source (V2A1-T2: builders spent minutes in the source on bench merges,
section syntax and screw_hole). If a tool misbehaves, work around it and note it in progress.md under "## Tool issues".
Progress file: ${dir(n)}/progress.md. Read it first; if your step is already marked done there, return its recorded result.
After each build+check, append one line: "<time-free step label> | <what changed> | cadcheck <fails>F/<warns>W".
Keep each generation short: edit one module, rebuild, check, repeat. Use the Edit tool for code changes.
Don't run git commit.`

const planPrompt = (n, history, reviewPath) => `
You plan design attempt ${n} of up to ${CONFIG.max_attempts}. Scores so far (F/M/A): ${history || 'none'}.
${common(n)}
${reviewPath
    ? `Latest review: ${reviewPath} (and review.json beside it). Plan fixes for every blocker and major; minors where cheap. Don't regress what it praised.`
    : `First attempt: write the architecture plan (world frame, subsystems = parts/ modules, joints with ranges, load path, payload path, assembly order) to ${HW}/DESIGN_LOG.md, then scaffold from ${PCB}/templates/project/ into ${HW}/blender/.`}
Before returning: update ${HW}/blender/checks.json so every review issue that is geometric has a check that would catch it
(drop_tests, distances, payload_fit, sightlines, slide_out with expect "blocked", fits, assembly_order; the reviewer's
review/review_rows.json, if any, can be merged as is). Every adjuster joint gets drop and distances rows at both ends of
its travel, with any spring at full deflection (V2A1-F1, V2A2-F1). Write payload sizes and gaps as "=EXPR" over params.py at
the declared extremes ("min": "=MM_T[1] + TAPE_T"), not as typed nominals (V2A3-F1). A gap the payload passes through
along an arc or a chute is a ray row with "sweep" over the whole passage, not one station: v2 A4's nip rows sat at BDC and
passed while the entry arc was 7.50 (V2A4-F1). A clearance to a toleranced purchased part is a "stacks" row with
"between" (the limit is the measured gap): v2 A5's band stack typed 3.0 while a detent tab sat 0.322 off the band (V2A5-F1).
A new part goes in the assembly_order step where it physically goes in (not the bench whose cable it carries), and a step
the BOM does at an angle ("drop in at +30", "nose up 20") gets its "pose": the insertion check then tests it. v2 A6 put the
bus splice, seated in the pan hub under the groove cap, in the feeder's bench step, and it was the one major (V2A6-F1).
Cable routes that meet across a joint meet on its axis (V2A6-F2). Mark the assembly step that brings power "powered": true;
a step that needs a servo-held joint moved before it (its "pose", or a screw reachable only at a joint limit) says how in
"pose_how", or better, is reordered or the screw moved: v2 A7's groove cap went on at tilt 45, six steps after the tilt
servo and before the battery, and it was the one major (V2A7-F1). Each lead is its own route, beside the others in a
shared channel, with one OD straight out of a plug or splice (V2A7-F2).
If the plan changes a shared params.py value (a profile constant, an interface), try it first: copy ${HW}/blender to
/tmp, make the change there, cad build, and cad check --only drop,distances,sightlines; plan around what fails. v2 A5's
planner predicted PSI_C 45 analytically, the params builder then hit 14 drop fails, and the launcher builder spent 30 min
redesigning the profile (V2A5-T2). Run the new rows on the CURRENT model.blend before
any geometry changes: each must fail there, or it would not have caught the issue. Record the count in progress.md (v2
A2's planner did this unprompted: 12 F on the attempt-1 model, 0 F at hand-off). Write the plan to ${dir(n)}/progress.md
under "## Plan".${CONFIG.parallel_builds ? `
Builders run in parallel this attempt and may not edit params.py or checks.json, so make every params.py change (IF_*
interfaces, shared dimensions) yourself now, and give each work[] entry only its own parts/<name>.py edits.` : ''}
Done when every blocker/major appears in some work[].review_issues or in deferred with a reason.`

const buildPrompt = (n, w) => `
You build subsystem "${w.subsystem}" for attempt ${n}.
${common(n)}
Changes to make: ${JSON.stringify(w.changes)}
Review issues this closes: ${JSON.stringify(w.review_issues)}
Acceptance (prove each with a cadcheck row or a cad q line): ${JSON.stringify(w.acceptance)}
${CONFIG.parallel_builds
    ? `Other subsystems are being built at the same time. Edit only ${HW}/blender/parts/${w.subsystem}.py. Don't edit params.py or
checks.json: put new check rows in ${HW}/blender/checks.d/${w.subsystem}.json (same schema), and list any params.py change you
need in not_done. Loop: edit, ${CAD} build ${HW}/blender/build_assembly.py -- --out /tmp/cadloop-${w.subsystem},
${CAD} check /tmp/cadloop-${w.subsystem}/model.blend ${HW}/blender/checks.json /tmp/cadloop-${w.subsystem}/cadcheck.json --overlay ${HW}/blender/checks.d/${w.subsystem}.json,
until no fail involves this subsystem's objects.`
    : `Edit ${HW}/blender/parts/${w.subsystem}.py (and params.py if needed). Loop: edit, ${CAD} build ${HW}/blender/build_assembly.py,
${CAD} check ${HW}/blender/model.blend ${HW}/blender/checks.json, until no fail involves this subsystem's objects.`}
Fix or accept every warn on this subsystem's objects: an accepted warn goes under accepted_warns with a reason (V2A1-F5).
Fails that belong to another subsystem: list them in not_done, don't fix them here.
Render at most ${CONFIG.render_budget} previews (960 px); prefer cad q measurements over images.
Return the final cadcheck summary numbers.`

const finishPrompt = (n, plan, builds) => `
You finish attempt ${n}.
${common(n)}
Plan: ${plan.plan}
Subsystem results: ${JSON.stringify(builds.map(b => b && { s: b.subsystem, not_done: b.not_done, fails: b.check.fails }))}
${CONFIG.parallel_builds ? `0. Merge ${HW}/blender/checks.d/*.json into checks.json, apply the params.py requests in the builders' not_done,
   and rebuild the shared ${HW}/blender/model.blend.
` : ''}1. Fix remaining cadcheck fails that span subsystems, or list them in deferred. Finish with 0 untriaged warns: fix each
   one or add it to accepted_warns with a reason (V2A1-F5: 3 of R1's issues were warns left in a 34-warn list).
2. Final renders: CAD_RENDER_FINAL=1 ${CAD} build ${HW}/blender/build_assembly.py -- --render --out-renders ${dir(n)}
   plus the sections the brief asks for (${CAD} q ... section), and ${CAD} sheet ${HW}/stl ${dir(n)}/stl_sheet.png.
3. Copy the final FULL cadcheck.json to ${dir(n)}/cadcheck.json (a report with run.only or run.quick is partial: re-run without --only/--quick, never hand off on it). Then prove "supports: no" on the exported STLs:
   ${CAD} printcheck ${HW}/stl --manifest ${HW}/blender/manifest.json --out ${dir(n)}/printcheck.json --render ${dir(n)}/printcheck
   must show 0 fails (re-orient, chamfer or split the part, or mark it supports: "yes" and say where), and
   ${CAD} slice ${HW}/stl --out ${dir(n)} (the only way a slicer may run) reports time, filament and where the slicer adds
   support; if it says no slicer is usable, quote that line and printcheck is the evidence (FINDINGS "v2 post-freeze").
4. Update ${HW}/BOM_AND_ASSEMBLY.md (assembly steps must match checks.json assembly_order) and append "Attempt ${n}" to ${HW}/DESIGN_LOG.md.
   Then run ${CAD} bom ${HW}/BOM_AND_ASSEMBLY.md ${HW}/blender/manifest.json and fix every BAD row (V2A3-F5, F6).
   Every claim cites a cadcheck row or cad q line; quote coverage and not_checked (${CAD} rows cadcheck.json --summary).
   Every BOM step that puts a part "in", "into" or "under" something has its part in that step of assembly_order, and
   checks.insertion lists it with a free direction (V2A6-F1). A step the BOM does at a joint angle is in
   assembly.held_poses with "pose_how" or after the "powered" step (V2A7-F1). Before writing a motion, timing or
   service claim (index positions, "adjust without disassembly", "comes off at tilt 45"), add the matching
   index_tests / service / slide_out entry to checks.json and re-run cad check (FINDINGS A2-F2, A2-F6). "Removable" is a
   slide_out over the whole path, until the part is clear of the machine (A3-F3; v2 A7's cap row stopped at 40, V2R7 A7-03). Every printed spring or snap arm gets a flexures entry (A3-F2).
Fill check.run_only from the report run (${CAD} rows cadcheck.json --summary prints it); it must be [].
Return the evidence summary from ${dir(n)}/cadcheck.json, not your opinion of it.`

const reviewPrompt = (n, prevReviewPath) => `
Review attempt ${n} of ${HW}. Follow ${REV}/SKILL.md exactly (rubric ${REV}/rubric.md, checklist ${REV}/checklist.md).
Work on a copy of the .blend under /tmp. Write extra renders to ${dir(n)}/review/ (budget 12), your review to
${dir(n)}/review.md and the structured result to ${dir(n)}/review.json.
${prevReviewPath ? `Previous review: ${prevReviewPath}. Re-measure every previous issue and keep its id if it recurs.` : 'First review: number issues A' + n + '-01, A' + n + '-02, ...'}
Append each measurement to ${dir(n)}/review/notes.md as you go. If it exists when you start, you were restarted: read it and
don't redo those measurements (A3-T4).
Mark tool_catchable=true when cadcheck, cad q or cad bom could have flagged the issue before review.
Report at most 10 blocker/major issues and at most 8 minor ones (most impactful first). Fold related symptoms into one
issue with one fix, so the next attempt converges instead of chasing a long tail.
Put every check row you add in ${dir(n)}/review/review_rows.json and run it with --overlay (V2A1-T6); the next planner merges it.
For every motion, timing or service claim in the BOM, check that checks.json has an index_tests / service / slide_out
entry that matches the documented values. If it is missing, add it to review_rows.json and run it (A2-F2).`

const attempts = []
let history = CONFIG.history.map(h => `#${h.n}: ${h.f}/${h.m}/${h.a}`).join(', ')
let prevReview = CONFIG.start_attempt > 1 ? `${dir(CONFIG.start_attempt - 1)}/review.md` : null
let passed = false

for (let n = CONFIG.start_attempt; n <= CONFIG.max_attempts && !passed; n++) {
  phase('Plan')
  const plan = await agent(planPrompt(n, history, prevReview), withModel('plan', { label: `plan #${n}`, phase: 'Plan', schema: PLAN_SCHEMA }))
  if (!plan) { log(`attempt ${n}: planner returned nothing; stopping`); break }
  log(`attempt ${n}: ${plan.work.length} subsystems to change, ${plan.deferred.length} deferred`)

  phase('Build')
  const runBuild = w => agent(buildPrompt(n, w), withModel('build', { label: `build #${n} ${w.subsystem}`, phase: 'Build', schema: BUILD_SCHEMA }))
  const builds = []
  if (CONFIG.parallel_builds) {         // each builder writes its own /tmp model.blend; the finisher merges
    builds.push(...await parallel(plan.work.map(w => () => runBuild(w))))
  } else {
    for (const w of plan.work) builds.push(await runBuild(w))   // sequential: one shared model.blend
  }
  builds.forEach((b, i) => { if (b) log(`attempt ${n} ${plan.work[i].subsystem}: cadcheck ${b.check.fails}F/${b.check.warns}W`) })

  phase('Finish')
  const design = await agent(finishPrompt(n, plan, builds), withModel('finish', { label: `finish #${n}`, phase: 'Finish', schema: FINISH_SCHEMA }))
  if (!design) { log(`attempt ${n}: finisher returned nothing; stopping`); break }
  log(`attempt ${n} designed: ${design.printed_parts.length} printed parts, cadcheck ${design.check.fails}F/${design.check.warns}W`)

  if ((design.check.run_only || []).length) {   // a partial check is not a hand-off (issue #28): no review, not passed
    log(`attempt ${n}: finisher handed off a partial check (only=${design.check.run_only.join(',')}); not reviewed`)
    attempts.push({ n, plan, design, review: null }); passed = false; break
  }

  phase('Review')
  const review = await agent(reviewPrompt(n, prevReview), withModel('review', { label: `review #${n}`, phase: 'Review', schema: REVIEW_SCHEMA }))
  attempts.push({ n, plan, design, review })
  if (!review) { log(`attempt ${n}: reviewer returned nothing; stopping`); break }
  const { functionality: f, manufacturability: m, aesthetics: a } = review
  const catchable = review.issues.filter(i => i.tool_catchable).length
  log(`attempt ${n}: F${f} M${m} A${a}; ${review.issues.length} issues, ${catchable} tool-catchable; resume with start_attempt=${n + 1}`)
  history = (history ? history + ', ' : '') + `#${n}: ${f}/${m}/${a}`
  passed = f >= CONFIG.target && m >= CONFIG.target && a >= CONFIG.target
  prevReview = `${dir(n)}/review.md`
  if (CONFIG.stop_after && n >= CONFIG.stop_after) { log(`stopping after attempt ${n} (stop_after)`); break }
}

return {
  passed,
  history,
  attempts: attempts.map(x => ({
    n: x.n,
    scores: x.review ? { f: x.review.functionality, m: x.review.manufacturability, a: x.review.aesthetics } : null,
    check: x.design.check,
    deferred: x.design.deferred,
    open_issues: x.review ? x.review.issues.slice(0, 10) : [],
  })),
}
