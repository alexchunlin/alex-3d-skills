"""Dry-run templates/cad-loop.workflow.js with stub agent()/phase()/log() under node.

    python3 -I tools/test_workflow_template.py      # needs node on PATH

Checks it parses, resumes from args.start_attempt, calls plan -> build per subsystem -> finish -> review,
stops when all scores reach the target, and gives each role its model (CONFIG.models; args.models overrides
single roles, null leaves opts.model unset). A stringified, misspelled or empty models arg must throw before
any agent runs.
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
if(got!==want||!out.passed||!out.history.endsWith('#4: 9/9/9')||gotModels!=='WANT_MODELS'){console.log('FAIL',got,out.history,gotModels);process.exit(1)}
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
rc = 0
for par, margs, want in CASES:        # sequential and parallel_builds (V2A1-T1)
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as f:
        f.write(harness.replace("PARALLEL", par).replace("MODELS_ARG", margs)
                .replace("WANT_MODELS", want or "").replace("WANT_ERR", "true" if want is None else "false"))
    rc |= subprocess.call(["node", f.name])
sys.exit(rc)
