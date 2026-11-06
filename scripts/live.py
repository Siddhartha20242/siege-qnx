#!/usr/bin/env python3
"""Live dashboard: run Siege scenarios on QNX and watch them in a browser.

    scripts/live.py                    # boots the image in QEMU, serves http://127.0.0.1:8766
    scripts/live.py --profile prio     # default hardening profile in the page
    scripts/live.py --simulate         # no emulator: simulated data, for testing the page only

Pick a scenario and a profile and press Run. Press Compare to run the same
attack under two profiles and overlay them: the clearest way to see what a
hardening profile changes. Play demo runs a scripted sequence. The page shows
a status tile, per-second latency against the deadline, the attack window,
supervisor and outage events, a plain-language verdict, and the raw QNX serial
console. If the emulator dies, the dashboard says so and boots a new one.
Scenarios and profiles come from siege.json, so your own appear in the menus.
"""
import argparse, json, os, queue, re, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import siegelib

ap = argparse.ArgumentParser()
ap.add_argument("--config", default=os.path.join(here, "..", "siege.json"))
ap.add_argument("--image", default=os.path.join(here, "..", "build", "siege.ifs"))
ap.add_argument("--profile", default="none")
ap.add_argument("--dur", type=int, default=8, help="seconds per run")
ap.add_argument("--port", type=int, default=8766)
ap.add_argument("--simulate", action="store_true", help="simulated data, no emulator (page testing only)")
args = ap.parse_args()

cfg = json.load(open(args.config))
SCEN = {s["label"]: s for s in cfg["scenarios"]}
PROFILES = list(cfg["profiles"])
DEADLINE = cfg.get("deadline_ms", 20)

# The scripted sequence: (scenario, [profiles run one after another and overlaid]).
DEMO = [("baseline (no attacker)", ["none"]),
        ("cpu hog   @prio 20", ["none", "budget"]),
        ("workflood @prio 30", ["none", "isolate", "prio"]),
        ("kill detector, no supervisor", ["none"]),
        ("kill detector, supervised", ["none"])]
DEMO = [(s, [p for p in ps if p in PROFILES]) for s, ps in DEMO if s in SCEN]

# ---- event hub -------------------------------------------------------------------------------
cond = threading.Condition()
events, run_start_idx = [], 0
busy = False
jobs = queue.Queue()


def emit(ev):
    global run_start_idx
    with cond:
        if ev["type"] == "start" and ev.get("first_of_group", True):
            run_start_idx = len(events)
        events.append(ev)
        cond.notify_all()


SAMPLE = re.compile(r"SUMMARY t=(\d+) frames=(\d+) late=(\d+) lost=(\d+) stalls=(\d+) p50_us=(\d+) p99_us=(\d+) max_us=(\d+)")
FINAL = re.compile(r"FINAL t=(\d+) frames=(\d+) late=(\d+) lost=(\d+) stalls=(\d+) p50_us=(\d+) p99_us=(\d+) max_us=(\d+)"
                   r"(?: outages=(\d+) outage_frames=(\d+) max_gap_ms=(\d+) abandoned=(\d))?(?: checked=(\d+) wrong=(\d+))?")


def handle_line(line):
    """Turn one console line into dashboard events."""
    if line.startswith("PRIO ") or not line.strip():
        return
    emit({"type": "console", "line": line})
    m = SAMPLE.search(line)
    if m:
        t, fr, late, lost, st, p50, p99, mx = map(int, m.groups())
        emit({"type": "sample", "t": t, "frames": fr, "late": late, "lost": lost, "p50": p50, "p99": p99, "max": mx})
    elif line.startswith("OUTAGE"):
        emit({"type": "event", "kind": "bad", "text": line})
    elif line.startswith("SUP"):
        emit({"type": "event", "kind": "info", "text": line})
    elif line.startswith("ATK mode"):
        emit({"type": "event", "kind": "warn", "text": line})
    else:
        m = FINAL.search(line)
        if m:
            g = [int(x) if x is not None else 0 for x in m.groups()]
            emit({"type": "final", "frames": g[1], "late": g[2], "lost": g[3], "p50": g[5], "p99": g[6], "max": g[7],
                  "outages": g[8], "gap": g[10], "abandoned": g[11], "checked": g[12], "wrong": g[13]})
        elif line.startswith("RESULT"):
            emit({"type": "result", "pass": "PASS" in line, "text": line})


def start_event(label, profile, dur, group, first):
    sc = SCEN[label]
    kill = sc.get("env", {}).get("KILL_AT")
    emit({"type": "start", "scenario": label, "profile": profile, "dur": dur, "deadline": DEADLINE,
          "group": group, "first_of_group": first,
          "attack_at": 1 if sc.get("attacker") else None, "kill_at": kill,
          "attacker": sc.get("attacker", ""), "atk_prio": sc.get("prio", 10),
          "supervised": str(sc.get("env", {}).get("SUPERVISE", "")) == "1"})


# ---- runners -----------------------------------------------------------------------------------
class RealRunner:
    def __init__(self):
        from qnxconsole import Console
        emit({"type": "booting"})
        self.c = Console(args.image)
        self.c.run("pipeline.sh 3 >/dev/null", 60)               # warm the emulator

    def alive(self):
        return self.c.qemu.poll() is None

    def run(self, label, profile, dur, group, first):
        sc = SCEN[label]
        c = self.c
        start_event(label, profile, dur, group, first)
        c.seq += 1
        marker = f"END{c.seq}"
        c.sock.send((siegelib.build_command(cfg, sc, profile, dur) + f'; echo EN""D{c.seq}\n').encode())
        mark, shown, end = len(c.buf), 0, time.time() + dur * 6 + 40
        while time.time() < end:
            if not self.alive():
                raise RuntimeError("the emulator exited")
            c._pump()
            lines = c.buf[mark:].split("\n")[:-1]
            while shown < len(lines):
                line = lines[shown].rstrip("\r")
                shown += 1
                if re.match(rf"^{marker}", line):
                    return
                if 'EN""D' in line:
                    continue
                handle_line(line)
        emit({"type": "result", "pass": False, "text": "RESULT FAIL (no result within the time limit)"})

    def close(self):
        self.c.close()


class FakeRunner:
    """Simulated data so the page can be tested without an emulator. Not measurements."""

    def alive(self):
        return True

    def run(self, label, profile, dur, group, first):
        sc = SCEN[label]
        atk, prio = sc.get("attacker", ""), sc.get("prio", 10)
        kill = sc.get("env", {}).get("KILL_AT")
        sup = str(sc.get("env", {}).get("SUPERVISE", "")) == "1"
        start_event(label, profile, dur, group, first)
        handle_line(f"RUN profile={profile} atk={atk or 'none'} atk_prio={prio} dur={dur}")

        def sample(t, p50=1500, p99=3000, late=0, lost=0, frames=50):
            handle_line(f"SUMMARY t={t} frames={frames} late={late} lost={lost} stalls=0 p50_us={p50} p99_us={p99} max_us={p99}")

        starved = atk == "cpu" and prio >= 20 and profile == "none"
        flooded = atk == "workflood" and profile in ("none", "isolate", "budget")
        for t in range(1, dur):
            time.sleep(1)
            if starved and t >= 2:
                continue
            if flooded and t >= 2:
                sample(t, 2000, 9000, 0, 30, 20)
                if t == 3:
                    handle_line("OUTAGE ms=340 frames=17")
                continue
            if kill and t >= int(kill) + 1 and not sup:
                continue
            if kill and sup and t == int(kill) + 1:
                handle_line("SUP fault injected: killed detector")
                handle_line("SUP restart=1 death_to_ready_ms=5 injected=1")
                sample(t, 1600, 41000, 0, 1, 49)
                continue
            sample(t)
        time.sleep(1)
        if starved:
            sample(dur - 1, 2500000, 4950000, 200, 0, 250)
            handle_line(f"FINAL t={dur-1} frames=250 late=200 lost=0 stalls=0 p50_us=2500000 p99_us=4950000 max_us=4990000 outages=0 outage_frames=0 max_gap_ms=4990 abandoned=0")
            handle_line("RESULT FAIL late_pm=800 tol_pm=20 max_gap_ms=4990 recovery_ms=500")
        elif flooded:
            handle_line(f"FINAL t={dur-1} frames=90 late=0 lost=40 stalls=3 p50_us=2100 p99_us=9000 max_us=15000 outages=10 outage_frames=140 max_gap_ms=640 abandoned=0")
            handle_line("RESULT FAIL late_pm=440 tol_pm=20 max_gap_ms=640 recovery_ms=500")
        elif kill and not sup:
            handle_line(f"FINAL t={dur-1} frames=100 late=0 lost=0 stalls=30 p50_us=1500 p99_us=3000 max_us=3200 outages=0 outage_frames=0 max_gap_ms=20 abandoned=1")
            handle_line("RESULT FAIL late_pm=0 tol_pm=20 max_gap_ms=20 recovery_ms=500")
        else:
            gap = 41 if kill else 22
            handle_line(f"FINAL t={dur-1} frames=300 late=0 lost={1 if kill else 0} stalls=0 p50_us=1600 p99_us=3000 max_us=3400 outages=0 outage_frames=0 max_gap_ms={gap} abandoned=0")
            handle_line(f"RESULT PASS late_pm=0 tol_pm=20 max_gap_ms={gap} recovery_ms=500")

    def close(self):
        pass


def make_runner():
    return FakeRunner() if args.simulate else RealRunner()


def worker(runner):
    """Run queued jobs one at a time. If the emulator dies, say so and boot a new one."""
    global busy
    emit({"type": "ready", "scenarios": list(SCEN), "profiles": PROFILES, "profile": args.profile,
          "deadline": DEADLINE, "simulated": args.simulate, "dur": args.dur,
          "demo": [{"scenario": s, "profiles": ps} for s, ps in DEMO]})
    while True:
        job = jobs.get()
        if job is None:
            break
        busy = True
        try:
            for i, (label, profile, group) in enumerate(job):
                try:
                    runner.run(label, profile, args.dur, group, i == 0 or not group)
                except Exception as e:                       # emulator died, or a console error
                    emit({"type": "error", "text": f"{e}. Restarting the emulator."})
                    try:
                        runner.close()
                    except Exception:
                        pass
                    runner = make_runner()
                    emit({"type": "error", "text": "The emulator was restarted. Run the scenario again."})
                    break
                time.sleep(1.5)
        finally:
            busy = False
            emit({"type": "idle"})


# ---- web page ------------------------------------------------------------------------------------
PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Siege live</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--fg:#1c2330;--mute:#5d6778;--line:#dfe3ea;--ok:#1a7f37;--bad:#cf222e;--warn:#bf8700;--idle:#6e7781;--accent:#2563eb}
@media(prefers-color-scheme:dark){:root{--bg:#0e1218;--card:#161b24;--fg:#e6e9ef;--mute:#9aa4b5;--line:#2a313d;--ok:#3fb950;--bad:#ff6b6b;--warn:#e3b341;--idle:#8b949e;--accent:#6ea8ff}}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}
main{max-width:1080px;margin:0 auto;padding:18px 16px 40px}
header{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:14px}
h1{font-size:22px;margin:0;flex:1 1 auto} .sub{color:var(--mute);font-size:13px}
.banner{border-radius:6px;padding:3px 10px;font-size:12px;font-weight:700;display:none;color:#000}
#sim{background:var(--warn)} #conn{background:var(--bad);color:#fff} #err{background:var(--bad);color:#fff;display:none;margin-bottom:10px;padding:8px 12px;border-radius:8px}
.controls{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px;align-items:center}
select,button{font:inherit;padding:8px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg)}
button{cursor:pointer;font-weight:600} button.primary{background:var(--accent);border-color:var(--accent);color:#fff} button:disabled{opacity:.5;cursor:default}
.grid{display:grid;grid-template-columns:240px 1fr;gap:12px} @media(max-width:760px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
#tile{display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;min-height:150px;color:#fff;background:var(--idle);border:none}
#tile .st{font-size:34px;font-weight:800;letter-spacing:.5px} #tile .sc{font-size:13px;opacity:.95;margin-top:6px}
#tile.ok{background:var(--ok)} #tile.bad{background:var(--bad)} #tile.warn{background:var(--warn);color:#000}
#chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px} .chip{border-radius:999px;padding:2px 10px;font-size:12px;font-weight:700;color:#fff;background:var(--idle)}
.chip.ok{background:var(--ok);color:#fff} .chip.bad{background:var(--bad);color:#fff}
canvas{width:100%;height:270px;display:block} #legend{font-size:12px;color:var(--mute);margin:0 0 6px;min-height:16px}
.metrics{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.m{flex:1 1 110px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 12px}
.m b{display:block;font-size:19px}.m span{font-size:12px;color:var(--mute)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px} @media(max-width:760px){.two{grid-template-columns:1fr}}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.6px;color:var(--mute);margin:0 0 8px}
#events{max-height:210px;overflow:auto;font-size:13px} #events div{padding:3px 0;border-bottom:1px solid var(--line)}
.bad{color:var(--bad)} .warn{color:var(--warn)} .info{color:var(--accent)} .ok{color:var(--ok)}
#console{background:#0b0e13;color:#cbd5e1;font:12px/1.4 ui-monospace,Menlo,monospace;border-radius:8px;padding:10px;height:210px;overflow:auto;white-space:pre-wrap}
#verdict{margin-top:10px;font-size:14px}
</style></head><body><main>
<header><h1>Siege <span class="sub">live on QNX 8.0 (QEMU)</span></h1>
 <span class="banner" id="sim">SIMULATED DATA</span><span class="banner" id="conn">reconnecting...</span></header>
<div id="err"></div>
<div class="controls">
 <select id="scen" aria-label="scenario"></select><select id="prof" aria-label="profile"></select>
 <button class="primary" id="run">Run</button>
 <span class="sub">or compare with</span><select id="prof2" aria-label="compare with"></select><button id="cmp">Compare</button>
 <button id="demo">Play demo</button><span class="sub" id="note"></span>
</div>
<div class="grid">
 <div class="card" id="tile"><div class="st">IDLE</div><div class="sc">pick a scenario and press Run</div></div>
 <div class="card"><h2>p99 frame latency per second (log scale) against the deadline</h2><div id="legend"></div><canvas id="chart"></canvas></div>
</div>
<div id="chips"></div>
<div class="metrics">
 <div class="m"><b id="m-frames">-</b><span>frames</span></div><div class="m"><b id="m-late">-</b><span>late</span></div>
 <div class="m"><b id="m-lost">-</b><span>lost</span></div><div class="m"><b id="m-p50">-</b><span>p50</span></div>
 <div class="m"><b id="m-p99">-</b><span>p99</span></div><div class="m"><b id="m-gap">-</b><span>longest silence</span></div>
</div>
<div class="card" id="verdict" style="display:none"></div>
<div class="two">
 <div class="card"><h2>Events</h2><div id="events"></div></div>
 <div class="card"><h2>QNX console</h2><div id="console"></div></div>
</div>
<script>
const $=id=>document.getElementById(id);
let S={runs:[],cur:null,group:null,running:false,lastSample:0,deadline:20,demo:[],stallLogged:false,run:null};
const fmt=us=>us==null?'-':us<1000?us+' us':us<1e6?(us/1000).toFixed(us<1e4?1:0)+' ms':(us/1e6).toFixed(1)+' s';
function tile(cls,st,sc){const t=$('tile');t.className='card '+cls;t.querySelector('.st').textContent=st;t.querySelector('.sc').textContent=sc}
function resetAll(){S.runs=[];S.cur=null;S.lastSample=Date.now();$('events').innerHTML='';$('console').textContent='';$('chips').innerHTML='';
 ['frames','late','lost','p50','p99','gap'].forEach(k=>$('m-'+k).textContent='-');$('verdict').style.display='none'}
function addEvent(kind,text){const d=document.createElement('div');d.className=kind;d.textContent=text;$('events').prepend(d)}
function chips(){$('chips').innerHTML='';S.runs.forEach(r=>{const c=document.createElement('span');
 c.className='chip '+(r.result?(r.result.pass?'ok':'bad'):'');c.textContent=r.profile+': '+(r.result?(r.result.pass?'PASS':'FAIL'):'running');$('chips').appendChild(c)});
 $('legend').textContent=S.runs.length>1?'bars, left to right at each second: '+S.runs.map(r=>r.profile).join(' | '):''}
function explain(f,pass,run){
 if(pass)return 'PASS: the pipeline met its deadlines'+(run.kill_at&&run.supervised?'; the supervisor restarted the detector and the controller saw a '+f.gap+' ms gap.':'.');
 if(f.abandoned)return 'FAIL: the pipeline went silent and never recovered; no frames arrived for over 3 s.';
 if(f.gap>1000)return 'FAIL: the pipeline was starved for about '+(f.gap/1000).toFixed(1)+' s. '+f.late+' of '+f.frames+' frames were late.';
 if(f.outages>0)return 'FAIL: '+f.outages+' silences (longest '+f.gap+' ms) and frames never delivered, even though the attacker uses little CPU. The damage is in the shared service queue.';
 if(f.checked&&f.wrong>f.checked*0.05)return 'FAIL: '+f.wrong+' of '+f.checked+' detections were wrong.';
 return 'FAIL: '+f.late+' late and '+f.lost+' lost frames out of '+f.frames+'.'}
function handle(ev){
 switch(ev.type){
 case 'ready':{const sc=$('scen'),pf=$('prof'),p2=$('prof2');sc.innerHTML='';pf.innerHTML='';p2.innerHTML='';
  ev.scenarios.forEach(s=>{const o=document.createElement('option');o.textContent=s.trim();o.value=s;sc.appendChild(o)});
  ev.profiles.forEach(p=>{[pf,p2].forEach(sel=>{const o=document.createElement('option');o.value=o.textContent=p;sel.appendChild(o)})});
  pf.value=ev.profile;p2.value=ev.profiles.includes('prio')?'prio':ev.profiles[ev.profiles.length-1];
  S.deadline=ev.deadline;S.demo=ev.demo;if(ev.simulated)$('sim').style.display='block';$('note').textContent='deadline '+ev.deadline+' ms';
  tile('', 'IDLE','pick a scenario and press Run');break}
 case 'booting':tile('warn','BOOTING','starting QNX in QEMU');break;
 case 'start':{if(!(ev.group&&ev.group===S.group))resetAll();
  S.group=ev.group||null;S.run=ev;S.running=true;S.stallLogged=false;S.deadline=ev.deadline;
  const r={profile:ev.profile,samples:[],final:null,result:null};S.runs.push(r);S.cur=r;
  $('scen').value=ev.scenario;$('prof').value=ev.profile;$('err').style.display='none';
  tile('warn','RUNNING',ev.scenario.trim()+' / '+ev.profile);$('run').disabled=$('cmp').disabled=$('demo').disabled=true;
  addEvent('info','--- '+ev.profile+' ---');
  if(ev.attacker)addEvent('warn','t=1 s: attacker "'+ev.attacker+'" starts at priority '+ev.atk_prio);
  if(ev.kill_at)addEvent('warn','t='+ev.kill_at+' s: the detector will be killed'+(ev.supervised?' (a supervisor is watching it)':' (no supervisor)'));
  chips();break}
 case 'sample':if(!S.cur)break;S.cur.samples.push(ev);S.lastSample=Date.now();
  $('m-frames').textContent=ev.frames;$('m-late').textContent=ev.late;$('m-lost').textContent=ev.lost;
  $('m-p50').textContent=fmt(ev.p50);$('m-p99').textContent=fmt(ev.p99);
  if(S.running){const bad=ev.p99>S.deadline*1000||ev.lost>0;tile(bad?'bad':'ok',bad?'RED':'GREEN',S.run.scenario.trim()+' / '+S.run.profile)}break;
 case 'event':addEvent(ev.kind,ev.text);break;
 case 'console':{const c=$('console');c.textContent+=ev.line+'\n';c.scrollTop=c.scrollHeight;break}
 case 'final':if(!S.cur)break;S.cur.final=ev;$('m-frames').textContent=ev.frames;$('m-late').textContent=ev.late;$('m-lost').textContent=ev.lost;
  $('m-p50').textContent=fmt(ev.p50);$('m-p99').textContent=fmt(ev.p99);$('m-gap').textContent=ev.gap+' ms';break;
 case 'result':{if(!S.cur)break;S.cur.result=ev;S.running=false;tile(ev.pass?'ok':'bad',ev.pass?'PASS':'FAIL',S.run.scenario.trim()+' / '+S.run.profile);chips();
  const v=$('verdict');v.style.display='block';v.className='card '+(ev.pass?'ok':'bad');
  let t=S.cur.final?explain(S.cur.final,ev.pass,S.run):ev.text;
  if(S.runs.length>1&&S.runs.every(r=>r.result))t='Same attack, '+S.runs.length+' configurations: '+S.runs.map(r=>r.profile+' '+(r.result.pass?'PASS':'FAIL')).join(', ')+'. Last run: '+t;
  v.textContent=t;break}
 case 'error':$('err').style.display='block';$('err').textContent=ev.text;S.running=false;tile('bad','ERROR','see the message above');break;
 case 'idle':S.running=false;$('run').disabled=$('cmp').disabled=$('demo').disabled=false;break}
 draw()}
function draw(){
 const cv=$('chart'),dpr=window.devicePixelRatio||1,w=cv.clientWidth,h=cv.clientHeight;cv.width=w*dpr;cv.height=h*dpr;
 const g=cv.getContext('2d');g.scale(dpr,dpr);g.clearRect(0,0,w,h);
 const cs=getComputedStyle(document.body),mute=cs.getPropertyValue('--mute'),line=cs.getPropertyValue('--line'),
  ok=cs.getPropertyValue('--ok'),bad=cs.getPropertyValue('--bad'),warn=cs.getPropertyValue('--warn');
 const L=48,R=10,T=14,B=26,pw=w-L-R,ph=h-T-B,dur=S.run?S.run.dur:8,y=ms=>T+ph*(1-(Math.log10(Math.max(ms,1))/4));
 g.font='11px system-ui';g.fillStyle=mute;g.strokeStyle=line;
 [[1,'1 ms'],[10,'10 ms'],[100,'100 ms'],[1000,'1 s'],[10000,'10 s']].forEach(([v,l])=>{g.beginPath();g.moveTo(L,y(v));g.lineTo(w-R,y(v));g.stroke();g.fillText(l,4,y(v)+4)});
 const x=t=>L+pw*Math.min(t,dur)/dur;
 for(let t=0;t<=dur;t++){g.fillText(t+'s',x(t)-8,h-8)}
 if(S.run&&S.run.attack_at!=null){g.fillStyle=warn;g.globalAlpha=.13;g.fillRect(x(S.run.attack_at),T,x(dur)-x(S.run.attack_at),ph);g.globalAlpha=1;
  g.fillStyle=warn;g.fillText('attack',x(S.run.attack_at)+4,T+11)}
 if(S.run&&S.run.kill_at){const k=+S.run.kill_at;g.strokeStyle=bad;g.setLineDash([4,3]);g.beginPath();g.moveTo(x(k),T);g.lineTo(x(k),T+ph);g.stroke();g.setLineDash([]);
  g.fillStyle=bad;g.fillText('detector killed',x(k)+4,T+11)}
 g.strokeStyle=warn;g.lineWidth=2;g.setLineDash([6,4]);g.beginPath();g.moveTo(L,y(S.deadline));g.lineTo(w-R,y(S.deadline));g.stroke();g.setLineDash([]);g.lineWidth=1;
 g.fillStyle=warn;g.fillText('deadline '+S.deadline+' ms',L+6,y(S.deadline)-5);
 const n=Math.max(1,S.runs.length),slot=pw/dur*.78,bw=Math.max(5,slot/n-2);
 S.runs.forEach((r,i)=>{r.samples.forEach(s=>{const v=s.p99/1000,late=v>S.deadline||s.lost>0;g.fillStyle=late?bad:ok;
  const yy=y(v),bx=x(s.t)-slot/2+i*(slot/n)+1;g.fillRect(bx,yy,bw,T+ph-yy);
  if(n>1){g.fillStyle='rgba(255,255,255,.85)';g.font='bold 10px system-ui';g.fillText(r.profile[0].toUpperCase(),bx+bw/2-3,T+ph-3);g.font='11px system-ui'}})});
 if(S.running&&Date.now()-S.lastSample>2200&&S.cur&&S.cur.samples.length){g.fillStyle=bad;g.font='bold 13px system-ui';g.fillText('no data from the pipeline: it is not reporting',L+8,T+ph/2)}
}
setInterval(()=>{if(S.running){draw();if(Date.now()-S.lastSample>2200&&S.cur&&S.cur.samples.length){tile('bad','STALLED','no frames reported for '+((Date.now()-S.lastSample)/1000).toFixed(0)+' s');
  if(!S.stallLogged){S.stallLogged=true;addEvent('bad','the pipeline stopped reporting: it is starved or dead')}}}},500);
window.addEventListener('resize',draw);
const post=jobs=>fetch('/run',{method:'POST',body:JSON.stringify({jobs})}).then(r=>{if(r.status===409)addEvent('warn','busy: wait for the current run to finish')});
$('run').onclick=()=>post([{scenario:$('scen').value,profile:$('prof').value}]);
$('cmp').onclick=()=>{const g='cmp-'+Date.now();post([{scenario:$('scen').value,profile:$('prof').value,group:g},{scenario:$('scen').value,profile:$('prof2').value,group:g}])};
$('demo').onclick=()=>{const jobs=[];(S.demo||[]).forEach((d,i)=>d.profiles.forEach(p=>jobs.push({scenario:d.scenario,profile:p,group:'demo-'+i})));post(jobs)};
const UPTO=new URLSearchParams(location.search).get('upto');let seenSamples=0,cut=false;   // ?upto=N: replay only the first N samples (for frame-by-frame captures)
const es=new EventSource('/events');es.onmessage=m=>{$('conn').style.display='none';const ev=JSON.parse(m.data);
 if(UPTO!==null&&ev.type==='sample'&&++seenSamples>+UPTO)cut=true;if(cut&&ev.type!=='ready')return;handle(ev)};
es.onerror=()=>{$('conn').style.display='block'};
if(location.search.includes('static'))setTimeout(()=>{es.close();draw()},1500);   // for screenshots: stop listening once the replay is in
</script></main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                with cond:
                    ready = [i for i, e in enumerate(events) if e["type"] == "ready"]
                    first = [events[ready[-1]]] if ready else []
                    tail = events[run_start_idx:] if run_start_idx < len(events) and events[run_start_idx]["type"] == "start" else []
                    snapshot = first + tail
                    idx = len(events)
                for e in snapshot:
                    self.wfile.write(f"data: {json.dumps(e)}\n\n".encode())
                self.wfile.flush()
                while True:
                    with cond:
                        while idx >= len(events):
                            if not cond.wait(timeout=15):
                                break
                        batch, idx = events[idx:], len(events)
                    if not batch:
                        self.wfile.write(b": keepalive\n\n")
                    for e in batch:
                        self.wfile.write(f"data: {json.dumps(e)}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        job = [(j["scenario"], j["profile"], j.get("group")) for j in req.get("jobs", [])
               if j["scenario"] in SCEN and j["profile"] in PROFILES]
        ok = bool(job) and not busy
        if ok:
            jobs.put(job)
        self.send_response(200 if ok else 409)
        self.end_headers()


def main():
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Siege live: http://127.0.0.1:{args.port}  ({'SIMULATED data' if args.simulate else 'booting QNX...'})", flush=True)
    runner = None
    try:
        runner = make_runner()
        worker(runner)
    except KeyboardInterrupt:
        pass
    finally:
        if runner:
            runner.close()
        server.shutdown()


if __name__ == "__main__":
    main()
