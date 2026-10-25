"""Dry-run templates/cad-loop.workflow.js with stub agent()/phase()/log() under node.

    python3 -I tools/test_workflow_template.py      # needs node on PATH

Checks it parses, resumes from args.start_attempt, calls plan -> build per subsystem -> finish -> review,
and stops when all scores reach the target.
"""
import os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, "templates", "cad-loop.workflow.js")).read().replace("export const meta", "const meta")
harness = """
const calls=[]; const scores=[[5,6,5],[8,8,7],[9,9,9]]; let r=0
const log=m=>calls.push('log'); const phase=p=>calls.push('phase:'+p)
const ok={fails:0,warns:1,fail_list:[],coverage:[],not_checked:[]}
async function agent(prompt,opts){ calls.push(opts.label)
  if(opts.phase==='Plan') return {plan:'p',work:[{subsystem:'base',changes:[],review_issues:[],acceptance:[]},{subsystem:'launcher',changes:[],review_issues:[],acceptance:[]}],deferred:[]}
  if(opts.phase==='Build') return {subsystem:'s',done:[],not_done:[],check:ok}
  if(opts.phase==='Finish') return {summary:'',addressed:[],deferred:[],printed_parts:['a'],check:ok,render_dir:''}
  const [f,m,a]=scores[r++]; return {functionality:f,manufacturability:m,aesthetics:a,anchors:{},issues:[{id:'x',tool_catchable:true}],previous_issue_status:[],check_config_disputes:[]}
}
const args={hw:'/tmp/x',start_attempt:2,history:[{n:1,f:5,m:6,a:5}]}
const out = await (async()=>{ %s })()
const want='plan #2|build #2 base|build #2 launcher|finish #2|review #2'
const got=calls.filter(c=>!c.startsWith('phase')&&c!=='log').slice(0,5).join('|')
if(got!==want||!out.passed||!out.history.endsWith('#4: 9/9/9')){console.log('FAIL',got,out.history);process.exit(1)}
console.log('OK', out.history)
""" % src
with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as f:
    f.write(harness)
sys.exit(subprocess.call(["node", f.name]))
