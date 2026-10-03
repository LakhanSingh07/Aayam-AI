import csv, io
from datetime import datetime
from fastapi import HTTPException, Header
from pydantic import BaseModel

ROLE_PERMISSIONS = {
 "super_admin":["*"],
 "registrar":["students.read","students.write","admissions.read","admissions.write","timetable.read","timetable.write","documents.read","documents.write","imports.students","notifications.read"],
 "hod":["students.read","timetable.read","timetable.write","documents.read","documents.write","notifications.read"],
 "faculty":["students.read","timetable.read","documents.read","notifications.read"],
 "student":["students.self","timetable.read","documents.read","notifications.read"]
}

class DocumentIn(BaseModel):
    title:str
    category:str="general"
    content:str
    department:str|None=None

class CsvImport(BaseModel):
    csv_text:str

def mount_features(app, db, user_from, scope_students):
    with db() as c:
        c.executescript("""
        create table if not exists documents(
          id integer primary key,title text,category text,content text,department text,
          created_by integer,created_at text
        );
        create table if not exists notifications(
          id integer primary key,title text,message text,role text,department text,
          is_read integer default 0,created_at text
        );
        """)
        if c.execute("select count(*) n from documents").fetchone()["n"]==0:
            c.executemany("insert into documents(title,category,content,department,created_by,created_at) values(?,?,?,?,?,?)",[
              ("Academic Regulations 2026","policy","Minimum attendance requirement is 75 percent. Students below the threshold require academic review.",None,1,datetime.utcnow().isoformat()),
              ("CSE Semester Guidelines","academic","CSE semester one follows the approved curriculum, lab schedule and continuous assessment framework.","CSE",1,datetime.utcnow().isoformat()),
              ("Placement Eligibility Guide","placement","Placement eligibility may consider CGPA, attendance, active backlogs and employer-specific criteria.",None,1,datetime.utcnow().isoformat())
            ])
        if c.execute("select count(*) n from notifications").fetchone()["n"]==0:
            c.executemany("insert into notifications(title,message,role,department,created_at) values(?,?,?,?,?)",[
              ("Attendance review","Students below 75% attendance need mentoring follow-up.","faculty","CSE",datetime.utcnow().isoformat()),
              ("Admissions pipeline","Shortlisted applications are ready for registrar review.","registrar",None,datetime.utcnow().isoformat()),
              ("Welcome to Aayam AI","Your university workspace is active.",None,None,datetime.utcnow().isoformat())
            ])

    @app.get("/api/permissions/me")
    def my_permissions(authorization:str|None=Header(None)):
        u=user_from(authorization)
        return {"role":u["role"],"department":u["department"],"permissions":ROLE_PERMISSIONS.get(u["role"],[])}

    @app.get("/api/students/{student_id}/360")
    def student_360(student_id:int, authorization:str|None=Header(None)):
        u=user_from(authorization)
        with db() as c:
            permitted={x["id"] for x in scope_students(c,u)}
            if student_id not in permitted: raise HTTPException(403,"Student outside your data scope")
            s=c.execute("select * from students where id=?",(student_id,)).fetchone()
            if not s: raise HTTPException(404,"Student not found")
            risk=[]
            if s["attendance"]<75:risk.append("attendance")
            if s["cgpa"]<6.5:risk.append("academic")
            if s["fee_due"]>0:risk.append("fees")
            return {
              "profile":dict(s),
              "risk_flags":risk,
              "risk_level":"high" if len(risk)>=2 else "medium" if risk else "low",
              "timeline":[
                {"type":"enrollment","label":"Student enrolled in "+s["program"]},
                {"type":"attendance","label":f"Current attendance {s['attendance']}%"},
                {"type":"finance","label":f"Outstanding fee INR {s['fee_due']:,.0f}"}
              ]
            }

    @app.get("/api/documents")
    def list_documents(q:str="", authorization:str|None=Header(None)):
        u=user_from(authorization)
        with db() as c:
            rows=c.execute("select * from documents order by id desc").fetchall()
        out=[]
        for r in rows:
            if r["department"] and u["role"] not in ("super_admin","registrar") and r["department"]!=u["department"]: continue
            if q and q.lower() not in (r["title"]+" "+r["category"]+" "+r["content"]).lower(): continue
            out.append({**dict(r),"content_preview":r["content"][:220]})
        return out

    @app.post("/api/documents")
    def create_document(p:DocumentIn, authorization:str|None=Header(None)):
        u=user_from(authorization)
        if u["role"] not in ("super_admin","registrar","hod"): raise HTTPException(403,"Not allowed")
        dept=p.department
        if u["role"]=="hod": dept=u["department"]
        with db() as c:
            cur=c.execute("insert into documents(title,category,content,department,created_by,created_at) values(?,?,?,?,?,?)",
              (p.title,p.category,p.content,dept,u["id"],datetime.utcnow().isoformat()))
        return {"id":cur.lastrowid,"ok":True}

    @app.get("/api/documents/search")
    def search_documents(q:str, authorization:str|None=Header(None)):
        u=user_from(authorization)
        terms=[x for x in q.lower().split() if len(x)>2]
        with db() as c: rows=c.execute("select * from documents").fetchall()
        scored=[]
        for r in rows:
            if r["department"] and u["role"] not in ("super_admin","registrar") and r["department"]!=u["department"]: continue
            text=(r["title"]+" "+r["category"]+" "+r["content"]).lower()
            score=sum(text.count(t) for t in terms)
            if score: scored.append((score,r))
        scored.sort(key=lambda x:x[0],reverse=True)
        return [{"id":r["id"],"title":r["title"],"category":r["category"],"excerpt":r["content"][:500],"score":s} for s,r in scored[:10]]

    @app.post("/api/import/students")
    def import_students(p:CsvImport, authorization:str|None=Header(None)):
        u=user_from(authorization)
        if u["role"] not in ("super_admin","registrar"): raise HTTPException(403,"Not allowed")
        reader=csv.DictReader(io.StringIO(p.csv_text))
        required={"enrollment_no","full_name","email","department","program","semester"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise HTTPException(422,"CSV requires enrollment_no, full_name, email, department, program, semester")
        created=0; skipped=0; errors=[]
        with db() as c:
            for idx,row in enumerate(reader,start=2):
                try:
                    if c.execute("select 1 from students where enrollment_no=?",(row["enrollment_no"],)).fetchone():
                        skipped+=1; continue
                    c.execute("""insert into students(user_id,enrollment_no,full_name,email,department,program,semester,cgpa,attendance,fee_due)
                               values(NULL,?,?,?,?,?,?,?,?,?)""",
                      (row["enrollment_no"],row["full_name"],row["email"],row["department"],row["program"],int(row["semester"]),
                       float(row.get("cgpa") or 0),float(row.get("attendance") or 0),float(row.get("fee_due") or 0)))
                    created+=1
                except Exception as e: errors.append({"row":idx,"error":str(e)})
            c.execute("insert into audit(user_id,action,entity,detail,created_at) values(?,?,?,?,?)",
              (u["id"],"bulk_import","student",f"created={created}, skipped={skipped}, errors={len(errors)}",datetime.utcnow().isoformat()))
        return {"created":created,"skipped":skipped,"errors":errors[:20]}

    @app.get("/api/notifications")
    def notifications(authorization:str|None=Header(None)):
        u=user_from(authorization)
        with db() as c: rows=c.execute("select * from notifications order by id desc").fetchall()
        return [dict(r) for r in rows if (not r["role"] or r["role"]==u["role"]) and (not r["department"] or r["department"]==u["department"])]

    @app.post("/api/notifications/{notification_id}/read")
    def notification_read(notification_id:int, authorization:str|None=Header(None)):
        user_from(authorization)
        with db() as c:c.execute("update notifications set is_read=1 where id=?",(notification_id,))
        return {"ok":True}
