import os, hmac, hashlib, base64, json, sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

DB_PATH = os.getenv("DB_PATH", "/tmp/aayam.db")
SECRET = os.getenv("JWT_SECRET", "change-this-in-render")
app = FastAPI(title="Aayam AI", version="0.4.0")

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def hash_pw(p):
    return hashlib.pbkdf2_hmac("sha256", p.encode(), b"aayam-v04", 120000).hex()

def sign(payload):
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return raw + "." + sig

def unsign(token):
    try:
        raw, sig = token.split(".",1)
        good = hmac.new(SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good): raise ValueError()
        return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw)%4)))
    except Exception: raise HTTPException(401,"Invalid token")

def user_from(auth):
    if not auth or not auth.startswith("Bearer "): raise HTTPException(401,"Authentication required")
    p=unsign(auth[7:])
    with db() as c:
        u=c.execute("select * from users where id=?",(p["id"],)).fetchone()
    if not u: raise HTTPException(401,"User not found")
    return dict(u)

def scope_students(c,u):
    if u["role"]=="student":
        return c.execute("select * from students where user_id=?",(u["id"],)).fetchall()
    if u["role"] in ("hod","faculty") and u["department"]:
        return c.execute("select * from students where department=?",(u["department"],)).fetchall()
    return c.execute("select * from students order by full_name").fetchall()

def init():
    Path(DB_PATH).parent.mkdir(parents=True,exist_ok=True)
    with db() as c:
        c.executescript("""
        create table if not exists users(id integer primary key,email text unique,full_name text,role text,department text,password_hash text);
        create table if not exists students(id integer primary key,user_id integer,enrollment_no text unique,full_name text,email text,department text,program text,semester integer,cgpa real,attendance real,fee_due real);
        create table if not exists applicants(id integer primary key,application_no text unique,full_name text,email text,program text,score real,stage text);
        create table if not exists timetable(id integer primary key,course_code text,course_title text,faculty text,room text,program text,semester integer,section text,weekday integer,start_time text,end_time text);
        create table if not exists audit(id integer primary key,user_id integer,action text,entity text,detail text,created_at text);
        """)
        if c.execute("select count(*) n from users").fetchone()["n"]==0:
            users=[
              ("admin@aayam.ai","Aayam Super Admin","super_admin",None),
              ("registrar@aayam.ai","University Registrar","registrar",None),
              ("hod.cse@aayam.ai","HOD CSE","hod","CSE"),
              ("faculty.cse@aayam.ai","Dr. Meera Sharma","faculty","CSE"),
              ("student@aayam.ai","Arjun Verma","student","CSE")]
            for e,n,r,d in users:c.execute("insert into users(email,full_name,role,department,password_hash) values(?,?,?,?,?)",(e,n,r,d,hash_pw("Admin@123")))
            student_uid=c.execute("select id from users where email='student@aayam.ai'").fetchone()["id"]
            rows=[
              (student_uid,"SGT26CSE001","Arjun Verma","student@aayam.ai","CSE","B.Tech CSE",1,8.2,75.0,18500),
              (None,"SGT26CSE002","Aditi Singh","aditi@example.com","CSE","B.Tech CSE",1,9.1,100.0,0),
              (None,"SGT26CSE003","Rohan Mehta","rohan@example.com","CSE","B.Tech CSE",1,7.4,25.0,50000)]
            c.executemany("insert into students(user_id,enrollment_no,full_name,email,department,program,semester,cgpa,attendance,fee_due) values(?,?,?,?,?,?,?,?,?,?)",rows)
            c.executemany("insert into applicants(application_no,full_name,email,program,score,stage) values(?,?,?,?,?,?)",[
              ("APP-2026-0001","Nisha Yadav","nisha@example.com","B.Tech CSE",84,"review"),
              ("APP-2026-0002","Kabir Arora","kabir@example.com","B.Tech CSE",91,"shortlisted"),
              ("APP-2026-0003","Mehak Jain","mehak@example.com","MBA",78,"applied")])
            c.executemany("insert into timetable(course_code,course_title,faculty,room,program,semester,section,weekday,start_time,end_time) values(?,?,?,?,?,?,?,?,?,?)",[
              ("CSE101","Programming Fundamentals","Dr. Meera Sharma","B-201","B.Tech CSE",1,"A",0,"09:00","10:00"),
              ("CSE101","Programming Fundamentals","Dr. Meera Sharma","B-201","B.Tech CSE",1,"A",2,"11:00","12:00")])

init()

class Login(BaseModel): email:str; password:str
class Stage(BaseModel): stage:str
class Slot(BaseModel):
    course_code:str; course_title:str; faculty:str; room:str; program:str; semester:int; section:str="A"; weekday:int; start_time:str; end_time:str
class Ask(BaseModel): question:str

@app.get("/health")
def health(): return {"status":"ok","service":"Aayam AI","version":"0.4.0"}

@app.post("/api/login")
def login(p:Login):
    with db() as c:u=c.execute("select * from users where email=?",(p.email.lower(),)).fetchone()
    if not u or u["password_hash"]!=hash_pw(p.password): raise HTTPException(401,"Invalid email or password")
    token=sign({"id":u["id"],"exp":(datetime.utcnow()+timedelta(hours=12)).isoformat()})
    return {"access_token":token,"role":u["role"],"full_name":u["full_name"]}

@app.get("/api/me")
def me(authorization:str|None=Header(None)):
    u=user_from(authorization); return {k:u[k] for k in ("id","email","full_name","role","department")}

@app.get("/api/dashboard")
def dashboard(authorization:str|None=Header(None)):
    u=user_from(authorization)
    with db() as c:
        ss=scope_students(c,u)
        faculty=c.execute("select count(*) n from users where role='faculty'").fetchone()["n"]
        applicants=c.execute("select count(*) n from applicants").fetchone()["n"]
    return {"students":len(ss),"faculty":faculty,"applicants":applicants,"fee_due_total":round(sum(x["fee_due"] for x in ss),2),"attendance_avg":round(sum(x["attendance"] for x in ss)/len(ss),1) if ss else None}

@app.get("/api/students")
def students(authorization:str|None=Header(None)):
    u=user_from(authorization)
    with db() as c: rows=scope_students(c,u)
    return [dict(x) for x in rows]

@app.get("/api/admissions")
def admissions(authorization:str|None=Header(None)):
    user_from(authorization)
    with db() as c:return [dict(x) for x in c.execute("select * from applicants order by id desc").fetchall()]

@app.patch("/api/admissions/{applicant_id}")
def admission_stage(applicant_id:int,p:Stage,authorization:str|None=Header(None)):
    u=user_from(authorization)
    if u["role"] not in ("super_admin","registrar"):raise HTTPException(403,"Not allowed")
    if p.stage not in ("applied","review","shortlisted","admitted","rejected","withdrawn"):raise HTTPException(422,"Invalid stage")
    with db() as c:
        c.execute("update applicants set stage=? where id=?",(p.stage,applicant_id))
        c.execute("insert into audit(user_id,action,entity,detail,created_at) values(?,?,?,?,?)",(u["id"],"stage_change","applicant",p.stage,datetime.utcnow().isoformat()))
    return {"ok":True}

@app.get("/api/timetable")
def timetable(authorization:str|None=Header(None)):
    user_from(authorization)
    with db() as c:return [dict(x) for x in c.execute("select * from timetable order by weekday,start_time").fetchall()]

def overlaps(a,b,c,d):return a<d and c<b

@app.post("/api/timetable")
def timetable_add(p:Slot,authorization:str|None=Header(None)):
    u=user_from(authorization)
    if u["role"] not in ("super_admin","registrar","hod"):raise HTTPException(403,"Not allowed")
    if p.weekday<0 or p.weekday>6 or p.start_time>=p.end_time:raise HTTPException(422,"Invalid slot")
    with db() as c:
        rows=c.execute("select * from timetable where weekday=?",(p.weekday,)).fetchall()
        for x in rows:
            if not overlaps(p.start_time,p.end_time,x["start_time"],x["end_time"]):continue
            if x["room"].lower()==p.room.lower():raise HTTPException(409,"Room conflict")
            if x["faculty"].lower()==p.faculty.lower():raise HTTPException(409,"Faculty conflict")
            if x["program"]==p.program and x["semester"]==p.semester and x["section"]==p.section:raise HTTPException(409,"Student cohort conflict")
        cur=c.execute("insert into timetable(course_code,course_title,faculty,room,program,semester,section,weekday,start_time,end_time) values(?,?,?,?,?,?,?,?,?,?)",(p.course_code,p.course_title,p.faculty,p.room,p.program,p.semester,p.section,p.weekday,p.start_time,p.end_time))
    return {"id":cur.lastrowid,**p.model_dump()}

@app.post("/api/ai")
def ask(p:Ask,authorization:str|None=Header(None)):
    u=user_from(authorization); q=p.question.lower()
    if any(x in q for x in ["delete ","drop ","truncate ","alter ","update ","insert "]):return {"answer":"Aayam AI is read-only for destructive database actions.","data":None}
    with db() as c:ss=scope_students(c,u)
    if "below 75" in q or "attendance" in q and "risk" in q:
        d=[{"name":x["full_name"],"attendance":x["attendance"],"enrollment_no":x["enrollment_no"]} for x in ss if x["attendance"]<75]
        return {"answer":f"{len(d)} students are below 75% attendance.","data":d}
    if "fee" in q and ("due" in q or "outstanding" in q):
        d=[{"name":x["full_name"],"fee_due":x["fee_due"]} for x in ss if x["fee_due"]>0]
        return {"answer":f"Outstanding fees total INR {sum(x['fee_due'] for x in ss):,.0f}.","data":d}
    if "how many" in q and "student" in q:return {"answer":f"There are {len(ss)} students in your permitted scope.","data":{"students":len(ss)}}
    if "top" in q and "cgpa" in q:
        d=sorted([{"name":x["full_name"],"cgpa":x["cgpa"]} for x in ss],key=lambda x:x["cgpa"],reverse=True)
        return {"answer":"Top students by CGPA.","data":d[:10]}
    return {"answer":"Ask about student counts, attendance risk, fee dues or top CGPA. This preview keeps AI read-only and permission-aware.","data":None}

PAGE='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Aayam AI</title><style>
:root{font-family:Inter,system-ui;background:#f5f7fb;color:#151821}*{box-sizing:border-box}body{margin:0}.login{min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at top left,#dfe5ff,transparent 35%),#f8f9fc}.card{background:#fff;border:1px solid #e6e9f0;border-radius:18px;padding:20px;box-shadow:0 12px 35px #27304a14}.login .card{width:min(420px,92vw);padding:28px}input,select,textarea{width:100%;padding:11px;border:1px solid #dfe3ea;border-radius:10px;margin:6px 0 12px}button{border:0;border-radius:10px;padding:10px 14px;font-weight:700;cursor:pointer;background:#4f5fff;color:#fff}.shell{display:grid;grid-template-columns:240px 1fr;min-height:100vh}.side{background:#111522;color:white;padding:24px}.brand{font-size:24px;font-weight:800}.side button{display:block;width:100%;text-align:left;background:transparent;color:#aeb5c4;margin-top:8px}.side button:hover{background:#22283a}.main{padding:28px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.metric b{display:block;font-size:28px;margin-top:8px}.muted{color:#717887}.table{background:#fff;border:1px solid #e4e7ee;border-radius:14px;overflow:auto;margin-top:18px}table{width:100%;border-collapse:collapse}th,td{padding:12px;border-bottom:1px solid #eceef2;text-align:left;font-size:13px}.row{display:flex;gap:12px;flex-wrap:wrap}.row>*{flex:1}.answer{white-space:pre-wrap;background:#111522;color:#e4e8ff;padding:15px;border-radius:12px;margin-top:12px}.pill{padding:5px 8px;border-radius:999px;background:#eef1ff;color:#4753c7;font-size:11px}@media(max-width:850px){.shell{grid-template-columns:1fr}.side{position:static}.grid{grid-template-columns:1fr 1fr}.main{padding:16px}}</style></head><body><div id="app"></div><script>
const A=document.querySelector('#app');let token=localStorage.aayamToken||'';let me=null;
async function api(path,opt={}){let h={'Content-Type':'application/json',...(opt.headers||{})};if(token)h.Authorization='Bearer '+token;let r=await fetch('/api'+path,{...opt,headers:h});let j=await r.json();if(!r.ok)throw Error(j.detail||'Request failed');return j}
function login(){A.innerHTML='<div class="login"><form class="card" id="f"><h1>Aayam AI</h1><p class="muted">University Intelligence Platform</p><input id="e" value="admin@aayam.ai"><input id="p" value="Admin@123" type="password"><button>Sign in</button><p id="err"></p></form></div>';f.onsubmit=async x=>{x.preventDefault();try{let r=await api('/login',{method:'POST',body:JSON.stringify({email:e.value,password:p.value})});token=r.access_token;localStorage.aayamToken=token;boot()}catch(z){err.textContent=z.message}}}
function shell(){A.innerHTML='<div class="shell"><aside class="side"><div class="brand">Aayam AI</div><p class="muted">University OS</p><button onclick="dash()">Dashboard</button><button onclick="students()">Students</button><button onclick="admissions()">Admissions</button><button onclick="timetable()">Timetable</button><button onclick="ask()">Ask Aayam AI</button><hr style="border-color:#2b3040"><small>'+me.full_name+'<br>'+me.role+'</small><button onclick="localStorage.removeItem(\'aayamToken\');location.reload()">Logout</button></aside><main class="main" id="v"></main></div>'}
async function dash(){let d=await api('/dashboard');v.innerHTML='<h1>University Command Center</h1><p class="muted">Live data from Aayam Core</p><div class="grid">'+[['Students',d.students],['Faculty',d.faculty],['Applicants',d.applicants],['Fee Due','INR '+d.fee_due_total.toLocaleString()]].map(x=>'<div class="card metric"><span class="muted">'+x[0]+'</span><b>'+x[1]+'</b></div>').join('')+'</div><div class="card" style="margin-top:18px"><b>Average attendance</b><h2>'+(d.attendance_avg??'—')+'%</h2></div>'}
async function students(){let r=await api('/students');v.innerHTML='<h1>Students</h1><div class="table"><table><tr><th>Enrollment</th><th>Name</th><th>Program</th><th>Attendance</th><th>CGPA</th><th>Fee Due</th></tr>'+r.map(x=>'<tr><td>'+x.enrollment_no+'</td><td><b>'+x.full_name+'</b></td><td>'+x.program+'</td><td>'+x.attendance+'%</td><td>'+x.cgpa+'</td><td>INR '+x.fee_due.toLocaleString()+'</td></tr>').join('')+'</table></div>'}
async function admissions(){let r=await api('/admissions');v.innerHTML='<h1>Admissions Pipeline</h1><div class="table"><table><tr><th>Application</th><th>Name</th><th>Program</th><th>Score</th><th>Stage</th></tr>'+r.map(x=>'<tr><td>'+x.application_no+'</td><td><b>'+x.full_name+'</b></td><td>'+x.program+'</td><td>'+x.score+'</td><td><select onchange="stage('+x.id+',this.value)">'+['applied','review','shortlisted','admitted','rejected','withdrawn'].map(s=>'<option '+(s==x.stage?'selected':'')+'>'+s+'</option>').join('')+'</select></td></tr>').join('')+'</table></div>'}
async function stage(id,s){try{await api('/admissions/'+id,{method:'PATCH',body:JSON.stringify({stage:s})})}catch(e){alert(e.message)}}
async function timetable(){let r=await api('/timetable');v.innerHTML='<h1>Timetable</h1><p class="muted">Room, faculty and cohort conflicts are blocked by the backend.</p><div class="table"><table><tr><th>Day</th><th>Time</th><th>Course</th><th>Faculty</th><th>Room</th></tr>'+r.map(x=>'<tr><td>'+['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][x.weekday]+'</td><td>'+x.start_time+'-'+x.end_time+'</td><td><b>'+x.course_code+'</b> '+x.course_title+'</td><td>'+x.faculty+'</td><td>'+x.room+'</td></tr>').join('')+'</table></div>'}
function ask(){v.innerHTML='<h1>Ask Aayam AI</h1><div class="card"><textarea id="q">Show students below 75% attendance</textarea><button onclick="runAsk()">Ask</button><div id="ans" class="answer">Ready.</div></div>'}
async function runAsk(){try{let r=await api('/ai',{method:'POST',body:JSON.stringify({question:q.value})});ans.textContent=r.answer+(r.data?'\n\n'+JSON.stringify(r.data,null,2):'')}catch(e){ans.textContent=e.message}}
async function boot(){if(!token)return login();try{me=await api('/me');shell();dash()}catch(e){localStorage.removeItem('aayamToken');token='';login()}}boot();
</script></body></html>'''
@app.get("/",response_class=HTMLResponse)
def root(): return PAGE
