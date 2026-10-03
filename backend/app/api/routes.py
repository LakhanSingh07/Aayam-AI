import csv, io
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from ..core.db import connect
from ..core.security import hash_password, issue_token, decode_token
from ..services.audit import log_event

router=APIRouter()

ROLE_PERMISSIONS={
 "super_admin":["*"],
 "registrar":["students.read","students.write","admissions.read","admissions.write","timetable.read","timetable.write","documents.read","documents.write","imports.students","notifications.read"],
 "hod":["students.read","timetable.read","timetable.write","documents.read","documents.write","notifications.read"],
 "faculty":["students.read","timetable.read","documents.read","notifications.read"],
 "student":["students.self","timetable.read","documents.read","notifications.read"],
}

class LoginIn(BaseModel): email:str; password:str
class StageIn(BaseModel): stage:str
class AskIn(BaseModel): question:str
class ImportIn(BaseModel): csv_text:str
class DocumentIn(BaseModel): title:str; category:str="General"; content:str; department:str|None=None
class TimetableIn(BaseModel):
    course_code:str; course_title:str; faculty:str; room:str; program:str
    semester:int; section:str="A"; weekday:int; start_time:str; end_time:str

def current_user(auth:str|None):
    if not auth or not auth.startswith("Bearer "): raise HTTPException(401,"Authentication required")
    data=decode_token(auth[7:])
    with connect() as c:
        row=c.execute("select * from users where id=?",(data["id"],)).fetchone()
    if not row: raise HTTPException(401,"User not found")
    return dict(row)

def scoped_students(c,u):
    if u["role"]=="student":
        return c.execute("select * from students where user_id=?",(u["id"],)).fetchall()
    if u["role"] in ("hod","faculty") and u["department"]:
        return c.execute("select * from students where department=? order by full_name",(u["department"],)).fetchall()
    return c.execute("select * from students order by full_name").fetchall()

def overlaps(a,b,c,d): return a<d and c<b

@router.post("/auth/login")
def login(p:LoginIn):
    with connect() as c:
        u=c.execute("select * from users where email=?",(p.email.lower(),)).fetchone()
    if not u or u["password_hash"]!=hash_password(p.password): raise HTTPException(401,"Invalid email or password")
    return {"access_token":issue_token(u["id"]),"role":u["role"],"full_name":u["full_name"]}

@router.get("/auth/me")
def me(authorization:str|None=Header(None)):
    u=current_user(authorization)
    return {k:u[k] for k in ("id","email","full_name","role","department")}

@router.get("/permissions/me")
def permissions(authorization:str|None=Header(None)):
    u=current_user(authorization)
    return {"role":u["role"],"department":u["department"],"permissions":ROLE_PERMISSIONS.get(u["role"],[])}

@router.get("/dashboard")
def dashboard(authorization:str|None=Header(None)):
    u=current_user(authorization)
    with connect() as c:
        students=scoped_students(c,u)
        faculty=c.execute("select count(*) n from faculty").fetchone()["n"]
        applicants=c.execute("select count(*) n from applicants").fetchone()["n"]
        courses=c.execute("select count(*) n from courses").fetchone()["n"]
        docs=c.execute("select count(*) n from documents").fetchone()["n"]
    return {
      "students":len(students),"faculty":faculty,"applicants":applicants,"courses":courses,"documents":docs,
      "attendance_avg":round(sum(x["attendance"] for x in students)/len(students),1) if students else None,
      "fee_due_total":round(sum(x["fee_due"] for x in students),2),
      "at_risk":sum(1 for x in students if x["attendance"]<75 or x["cgpa"]<6.5 or x["fee_due"]>0)
    }

@router.get("/students")
def students(authorization:str|None=Header(None)):
    u=current_user(authorization)
    with connect() as c: rows=scoped_students(c,u)
    return [dict(x) for x in rows]

@router.get("/students/{student_id}/360")
def student_360(student_id:int,authorization:str|None=Header(None)):
    u=current_user(authorization)
    with connect() as c:
        allowed={x["id"] for x in scoped_students(c,u)}
        if student_id not in allowed: raise HTTPException(403,"Student outside your scope")
        s=c.execute("select * from students where id=?",(student_id,)).fetchone()
    if not s: raise HTTPException(404,"Student not found")
    risk=[]
    if s["attendance"]<75:risk.append("attendance")
    if s["cgpa"]<6.5:risk.append("academic")
    if s["fee_due"]>0:risk.append("fees")
    return {"profile":dict(s),"risk_flags":risk,"risk_level":"high" if len(risk)>=2 else "medium" if risk else "low",
            "timeline":[{"label":f"Enrolled in {s['program']}"},{"label":f"Attendance {s['attendance']}%"},{"label":f"Fee due INR {s['fee_due']:,.0f}"}]}

@router.get("/faculty")
def faculty(authorization:str|None=Header(None)):
    u=current_user(authorization)
    with connect() as c:
        if u["role"] in ("hod","faculty") and u["department"]:
            rows=c.execute("select * from faculty where department=? order by full_name",(u["department"],)).fetchall()
        else: rows=c.execute("select * from faculty order by full_name").fetchall()
    return [dict(x) for x in rows]

@router.get("/courses")
def courses(authorization:str|None=Header(None)):
    u=current_user(authorization)
    with connect() as c:
        if u["role"] in ("hod","faculty","student") and u["department"]:
            rows=c.execute("select * from courses where department=? order by code",(u["department"],)).fetchall()
        else: rows=c.execute("select * from courses order by code").fetchall()
    return [dict(x) for x in rows]

@router.get("/admissions")
def admissions(authorization:str|None=Header(None)):
    current_user(authorization)
    with connect() as c:return [dict(x) for x in c.execute("select * from applicants order by id desc").fetchall()]

@router.patch("/admissions/{applicant_id}/stage")
def admission_stage(applicant_id:int,p:StageIn,authorization:str|None=Header(None)):
    u=current_user(authorization)
    if u["role"] not in ("super_admin","registrar"): raise HTTPException(403,"Not allowed")
    if p.stage not in ("applied","review","shortlisted","admitted","rejected","withdrawn"): raise HTTPException(422,"Invalid stage")
    with connect() as c:
        c.execute("update applicants set stage=? where id=?",(p.stage,applicant_id)); log_event(c,u["id"],"stage_change","applicant",p.stage)
    return {"ok":True}

@router.get("/timetable")
def timetable(authorization:str|None=Header(None)):
    current_user(authorization)
    with connect() as c:return [dict(x) for x in c.execute("select * from timetable order by weekday,start_time").fetchall()]

@router.post("/timetable")
def timetable_add(p:TimetableIn,authorization:str|None=Header(None)):
    u=current_user(authorization)
    if u["role"] not in ("super_admin","registrar","hod"): raise HTTPException(403,"Not allowed")
    if not 0<=p.weekday<=6 or p.start_time>=p.end_time: raise HTTPException(422,"Invalid slot")
    with connect() as c:
        rows=c.execute("select * from timetable where weekday=?",(p.weekday,)).fetchall()
        for x in rows:
            if not overlaps(p.start_time,p.end_time,x["start_time"],x["end_time"]): continue
            if x["room"].lower()==p.room.lower(): raise HTTPException(409,"Room conflict")
            if x["faculty"].lower()==p.faculty.lower(): raise HTTPException(409,"Faculty conflict")
            if x["program"]==p.program and x["semester"]==p.semester and x["section"]==p.section: raise HTTPException(409,"Student cohort conflict")
        cur=c.execute("insert into timetable(course_code,course_title,faculty,room,program,semester,section,weekday,start_time,end_time) values(?,?,?,?,?,?,?,?,?,?)",
          (p.course_code,p.course_title,p.faculty,p.room,p.program,p.semester,p.section,p.weekday,p.start_time,p.end_time))
        log_event(c,u["id"],"create","timetable",f"{p.course_code} {p.start_time}-{p.end_time}")
    return {"id":cur.lastrowid,**p.model_dump()}

@router.get("/documents")
def documents(q:str="",authorization:str|None=Header(None)):
    u=current_user(authorization)
    with connect() as c: rows=c.execute("select * from documents order by id desc").fetchall()
    out=[]
    for r in rows:
        if r["department"] and u["role"] not in ("super_admin","registrar") and r["department"]!=u["department"]: continue
        hay=(r["title"]+" "+r["category"]+" "+r["content"]).lower()
        if q and q.lower() not in hay: continue
        out.append({**dict(r),"content_preview":r["content"][:220]})
    return out

@router.post("/documents")
def create_document(p:DocumentIn,authorization:str|None=Header(None)):
    u=current_user(authorization)
    if u["role"] not in ("super_admin","registrar","hod"): raise HTTPException(403,"Not allowed")
    dept=u["department"] if u["role"]=="hod" else p.department
    with connect() as c:
        cur=c.execute("insert into documents(title,category,content,department,created_by,created_at) values(?,?,?,?,?,?)",
          (p.title,p.category,p.content,dept,u["id"],datetime.utcnow().isoformat()))
        log_event(c,u["id"],"create","document",p.title)
    return {"id":cur.lastrowid,"ok":True}

@router.post("/imports/students")
def import_students(p:ImportIn,authorization:str|None=Header(None)):
    u=current_user(authorization)
    if u["role"] not in ("super_admin","registrar"): raise HTTPException(403,"Not allowed")
    reader=csv.DictReader(io.StringIO(p.csv_text))
    required={"enrollment_no","full_name","email","department","program","semester"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)): raise HTTPException(422,"Missing required CSV columns")
    created=skipped=0; errors=[]
    with connect() as c:
        for idx,row in enumerate(reader,start=2):
            try:
                if c.execute("select 1 from students where enrollment_no=?",(row["enrollment_no"],)).fetchone(): skipped+=1; continue
                c.execute("insert into students(user_id,enrollment_no,full_name,email,department,program,semester,cgpa,attendance,fee_due) values(NULL,?,?,?,?,?,?,?,?,?)",
                  (row["enrollment_no"],row["full_name"],row["email"],row["department"],row["program"],int(row["semester"]),float(row.get("cgpa") or 0),float(row.get("attendance") or 0),float(row.get("fee_due") or 0)))
                created+=1
            except Exception as e: errors.append({"row":idx,"error":str(e)})
        log_event(c,u["id"],"bulk_import","student",f"created={created}, skipped={skipped}, errors={len(errors)}")
    return {"created":created,"skipped":skipped,"errors":errors[:20]}

@router.get("/notifications")
def notifications(authorization:str|None=Header(None)):
    u=current_user(authorization)
    with connect() as c: rows=c.execute("select * from notifications order by id desc").fetchall()
    return [dict(r) for r in rows if (not r["role"] or r["role"]==u["role"]) and (not r["department"] or r["department"]==u["department"])]

@router.get("/audit")
def audit(authorization:str|None=Header(None)):
    u=current_user(authorization)
    if u["role"] not in ("super_admin","registrar"): raise HTTPException(403,"Not allowed")
    with connect() as c:return [dict(x) for x in c.execute("select * from audit order by id desc limit 100").fetchall()]

@router.post("/ai/query")
def ask(p:AskIn,authorization:str|None=Header(None)):
    u=current_user(authorization); q=p.question.lower()
    if any(x in q for x in ("delete ","drop ","truncate ","alter ","update ","insert ")):
        return {"answer":"Aayam AI keeps destructive database actions blocked.","data":None}
    with connect() as c: ss=scoped_students(c,u)
    if "below 75" in q or ("attendance" in q and "risk" in q):
        d=[{"name":x["full_name"],"attendance":x["attendance"],"enrollment_no":x["enrollment_no"]} for x in ss if x["attendance"]<75]
        return {"answer":f"{len(d)} students are below 75% attendance.","data":d}
    if "fee" in q and ("due" in q or "outstanding" in q):
        d=[{"name":x["full_name"],"fee_due":x["fee_due"]} for x in ss if x["fee_due"]>0]
        return {"answer":f"Outstanding fees total INR {sum(x['fee_due'] for x in ss):,.0f}.","data":d}
    if "how many" in q and "student" in q:return {"answer":f"There are {len(ss)} students in your permitted scope.","data":{"students":len(ss)}}
    if "top" in q and "cgpa" in q:
        d=sorted([{"name":x["full_name"],"cgpa":x["cgpa"]} for x in ss],key=lambda x:x["cgpa"],reverse=True)
        return {"answer":"Top students by CGPA.","data":d[:10]}
    return {"answer":"Ask about student counts, attendance risk, fee dues or top CGPA.","data":None}
