"""Dry-run templates/cad-loop.workflow.js with stub agent()/phase()/log() under node.

    python3 -I tools/test_workflow_template.py      # needs node on PATH

Checks it parses, resumes from args.start_attempt, calls plan -> build per subsystem -> finish -> review,
stops when all scores reach the target, and gives each role its model (CONFIG.models; args.models overrides
single roles, null leaves opts.model unset). A stringified, misspelled or empty models arg must throw before
any agent runs.

Recurrence and snapshots (#41, #42): a second dry run plants an id that stays PARTIAL in two reviews in a row and
checks that only the next planner is told to escalate it, that every earlier review.md reaches the planner with the
newest marked, that a missing escalation is logged, that args.misses resumes a streak, that `best` is the highest
F+M+A with ties to the latest (and counts args.history), that the finisher snapshots into attempt-N/snapshot/, and that
builders and the finisher are told to fix text-only mismatches in any file. A third run hands off a partial check at
attempt 3 (PR #50): it is not reviewed and adds nothing to best or misses.
"""
import os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, "templates", "cad-loop.workflow.js")).read().replace("export const meta", "const meta")
harness = """
const calls=[]; const scores=[[5,6,5],[8,8,7],[9,9,9]]; let r=0
const log=m=>calls.push('log'); const phase=p=>calls.push('phase:'+p)
const parallel=async fs=>Promise.all(fs.map(f=>f()))
const ok={fails:0,warns:1,fail_list:[],coverage:[],not_checked:[]}
const models={}
async function agent(prompt,opts){ calls.push(opts.label)
  if('model' in opts && !opts.model){console.log('FAIL empty model on',opts.label);process.exit(1)}
  const mod=opts.model||'-'; if((models[opts.phase]??mod)!==mod){console.log('FAIL mixed models in',opts.phase);process.exit(1)}
  models[opts.phase]=mod
  if(opts.phase==='Plan') return {plan:'p',work:[{subsystem:'base',changes:[],review_issues:[],acceptance:[]},{subsystem:'launcher',changes:[],review_issues:[],acceptance:[]}],deferred:[]}
  if(opts.phase==='Build') return {subsystem:'s',done:[],not_done:[],check:ok}
  if(opts.phase==='Finish') return {summary:'',addressed:[],deferred:[],printed_parts:['a'],check:ok,render_dir:''}
  const [f,m,a]=scores[r++]; return {functionality:f,manufacturability:m,aesthetics:a,anchors:{},issues:[{id:'x',tool_catchable:true}],previous_issue_status:[],check_config_disputes:[]}
}
const args={hw:'/tmp/x',start_attempt:2,history:[{n:1,f:5,m:6,a:5}],parallel_builds:PARALLEL,MODELS_ARG}
let out
try { out = await (async()=>{ %s })() } catch(e) {
  if(WANT_ERR && e.message.startsWith('cad-loop: args.models') && !calls.length){console.log('OK throws:', e.message);process.exit(0)}
  console.log('FAIL threw', e.message);process.exit(1)
}
if(WANT_ERR){console.log('FAIL no error for models arg', JSON.stringify(args.models));process.exit(1)}
const want='plan #2|build #2 base|build #2 launcher|finish #2|review #2'
const got=calls.filter(c=>!c.startsWith('phase')&&c!=='log').slice(0,5).join('|')
const gotModels=['Plan','Build','Finish','Review'].map(p=>models[p]).join('|')
if(got!==want||!out.passed||!out.history.endsWith('#4: 9/9/9')||out.best!==4||gotModels!=='WANT_MODELS'){console.log('FAIL',got,out.history,gotModels);process.exit(1)}
console.log('OK', out.history, gotModels)
""" % src
# (parallel_builds, args.models, models seen by plan|build|finish|review; '-' = opts.model unset; None = must throw)
CASES = [
    ("false", "", "-|sonnet|-|-"),                                   # defaults: builders on Sonnet (2026-10-27 mates runs)
    ("true", "models:{review:'opus'}", "-|sonnet|-|opus"),           # override one role, the others keep their defaults
    ("false", "models:{build:null,plan:'haiku'}", "haiku|-|-|-"),    # null = the workflow's default model
    ("false", "models:'{\"review\":\"opus\"}'", None),               # stringified JSON (PR #13 review)
    ("false", "models:{builder:'opus'}", None),                       # misspelled role
    ("false", "models:{build:''}", None),                             # empty string
    ("false", "models:['sonnet']", None),                             # array
]
# #42 recurrence, snapshot and best; #41 text-only line. One run of 4 attempts from start_attempt 1.
recur = """
const logs=[], prompts={}
const log=m=>logs.push(m); const phase=()=>{}; const parallel=async fs=>Promise.all(fs.map(f=>f()))
const ok={fails:0,warns:0,fail_list:[],coverage:[],not_checked:[]}
const P=id=>({id,status:'PARTIAL',evidence:''}), F=id=>({id,status:'FIXED',evidence:''})
// R1 raises A1-03, R2 and R3 find it PARTIAL (two misses), so plan #4 must escalate it; B1 is PARTIAL once then FIXED;
// Z resumes from args.misses {Z:1} and is PARTIAL in R1, so plan #2 already escalates it.
const reviews=[[6,6,6,[P('Z')]],[8,8,7,[P('A1-03'),P('B1')]],[7,7,7,[P('A1-03'),F('B1')]],[8,7,8,[F('A1-03')]]]; let r=0
async function agent(prompt,opts){ prompts[opts.label]=prompt
  if(opts.phase==='Plan') return {plan:'p',work:[{subsystem:'base',changes:[],review_issues:[],acceptance:[]}],deferred:[],
    escalations: opts.label==='plan #2' ? [{id:'Z',tried:['t'],approach:'defer',why:'w'}] : []}
  if(opts.phase==='Build') return {subsystem:'base',done:[],not_done:[],check:ok}
  if(opts.phase==='Finish') return {summary:'',addressed:[],deferred:[],printed_parts:['a'],render_dir:'',
    check: opts.label==='finish #'+PARTIAL_AT ? {...ok,run_only:['quick']} : ok}
  const [f,m,a,st]=reviews[r++]; return {functionality:f,manufacturability:m,aesthetics:a,anchors:{},issues:[],previous_issue_status:st,check_config_disputes:[]}
}
const args={hw:'/tmp/x',max_attempts:4,misses:{Z:1},history:HISTORY}
const out = await (async()=>{ %s })()
const bad=[]; const t=(c,msg)=>{ if(!c) bad.push(msg) }
if(PARTIAL_AT){   // PR #50: a partial check stops before review, so it adds no score to best and no misses
  t(!('review #'+PARTIAL_AT in prompts), 'partial attempt was reviewed')
  t(out.best===WANT_BEST, 'best counted the partial attempt: '+out.best)
  t(JSON.stringify(out.misses)==='{"A1-03":1,"B1":1}', 'misses after the partial: '+JSON.stringify(out.misses))
  if(bad.length){console.log('FAIL partial:', bad.join('; '));process.exit(1)}
  console.log('OK partial at #'+PARTIAL_AT+': best', out.best, JSON.stringify(out.misses)); process.exit(0)
}
const esc=l=>(prompts[l].match(/PARTIAL\\/NOT FIXED in the last two reviews: ([^.]*)\\./)||[])[1]||''
t(!/last two reviews/.test(prompts['plan #1']), 'plan #1 has no escalation')
t(esc('plan #2')==='Z', 'plan #2 escalates the resumed Z: '+esc('plan #2'))
t(esc('plan #3')==='', 'plan #3 escalates nothing after one miss: '+esc('plan #3'))
t(esc('plan #4')==='A1-03', 'plan #4 escalates A1-03 only: '+esc('plan #4'))
t(prompts['plan #4'].includes('/tmp/x/renders/attempt-1/review.md, /tmp/x/renders/attempt-2/review.md, /tmp/x/renders/attempt-3/review.md (latest)'), 'plan #4 lists every review, newest marked')
t(!prompts['plan #3'].includes('attempt-3/review.md'), 'plan #3 lists no future review')
t(logs.some(m=>/attempt 4: WARNING planner wrote no escalation for A1-03/.test(m)), 'missing escalation is logged')
t(!logs.some(m=>/attempt 2: WARNING/.test(m)), 'no warning when the escalation is there')
t(out.best===WANT_BEST, 'best '+out.best)
t(logs.some(m=>m.startsWith('best attempt: #'+WANT_BEST+' ')&&m.includes('/tmp/x/renders/attempt-'+WANT_BEST+'/snapshot/')), 'best log line names the snapshot')
t(JSON.stringify(out.misses)==='{}', 'misses cleared after FIXED: '+JSON.stringify(out.misses))
t(prompts['finish #2'].includes('/tmp/x/renders/attempt-2/snapshot/')&&/copy \\(don't move\\)/.test(prompts['finish #2']), 'finisher snapshots the attempt')
t(/text-only mismatch/.test(prompts['build #2 base'])&&/text-only mismatch/.test(prompts['finish #2']), 'text-only line in build and finish')
if(bad.length){console.log('FAIL recurrence:', bad.join('; '));process.exit(1)}
console.log('OK recurrence: best', out.best)
""" % src
rc = 0
# (args.history, best, attempt whose finisher hands off a partial check or 0): ties to the latest (#2 and #4 both
# 23); an earlier run's 9/9/8 beats this run; a partial attempt 3 ends the loop with #2 best and R2's misses
for hist, best, partial in (("[]", "4", "0"), ("[{n:0,f:9,m:9,a:8}]", "0", "0"), ("[]", "2", "3")):
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as f:
        f.write(recur.replace("HISTORY", hist).replace("WANT_BEST", best).replace("PARTIAL_AT", partial))
    rc |= subprocess.call(["node", f.name])
for par, margs, want in CASES:        # sequential and parallel_builds (V2A1-T1)
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as f:
        f.write(harness.replace("PARALLEL", par).replace("MODELS_ARG", margs)
                .replace("WANT_MODELS", want or "").replace("WANT_ERR", "true" if want is None else "false"))
    rc |= subprocess.call(["node", f.name])
sys.exit(rc)
