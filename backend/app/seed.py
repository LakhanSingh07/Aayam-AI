from datetime import datetime
from .core.db import connect
from .core.security import hash_password
from .models.schema import SCHEMA

def seed():
    with connect() as c:
        c.executescript(SCHEMA)
        if c.execute("select count(*) n from users").fetchone()["n"]==0:
            users=[
              ("admin@aayam.ai","Aayam Super Admin","super_admin",None),
              ("registrar@aayam.ai","University Registrar","registrar",None),
              ("hod.cse@aayam.ai","HOD CSE","hod","CSE"),
              ("faculty.cse@aayam.ai","Dr. Meera Sharma","faculty","CSE"),
              ("student@aayam.ai","Arjun Verma","student","CSE")]
            for e,n,r,d in users:
                c.execute("insert into users(email,full_name,role,department,password_hash) values(?,?,?,?,?)",(e,n,r,d,hash_password("Admin@123")))
            suid=c.execute("select id from users where email='student@aayam.ai'").fetchone()["id"]
            c.executemany("insert into students(user_id,enrollment_no,full_name,email,department,program,semester,cgpa,attendance,fee_due) values(?,?,?,?,?,?,?,?,?,?)",[
              (suid,"SGT26CSE001","Arjun Verma","student@aayam.ai","CSE","B.Tech CSE",1,8.2,75.0,18500),
              (None,"SGT26CSE002","Aditi Singh","aditi@example.com","CSE","B.Tech CSE",1,9.1,100.0,0),
              (None,"SGT26CSE003","Rohan Mehta","rohan@example.com","CSE","B.Tech CSE",1,7.4,25.0,50000)])
            c.execute("insert into faculty(employee_no,full_name,email,designation,department) values(?,?,?,?,?)",("EMP-CSE-001","Dr. Meera Sharma","faculty.cse@aayam.ai","Assistant Professor","CSE"))
            c.executemany("insert into courses(code,title,semester,credits,department) values(?,?,?,?,?)",[
              ("CSE101","Programming Fundamentals",1,4,"CSE"),
              ("CSE102","Discrete Mathematics",1,4,"CSE"),
              ("CSE103","Computer Systems",1,3,"CSE")])
            c.executemany("insert into applicants(application_no,full_name,email,program,score,stage) values(?,?,?,?,?,?)",[
              ("APP-2026-0001","Nisha Yadav","nisha@example.com","B.Tech CSE",84,"review"),
              ("APP-2026-0002","Kabir Arora","kabir@example.com","B.Tech CSE",91,"shortlisted"),
              ("APP-2026-0003","Mehak Jain","mehak@example.com","MBA",78,"applied")])
            c.executemany("insert into timetable(course_code,course_title,faculty,room,program,semester,section,weekday,start_time,end_time) values(?,?,?,?,?,?,?,?,?,?)",[
              ("CSE101","Programming Fundamentals","Dr. Meera Sharma","B-201","B.Tech CSE",1,"A",0,"09:00","10:00"),
              ("CSE101","Programming Fundamentals","Dr. Meera Sharma","B-201","B.Tech CSE",1,"A",2,"11:00","12:00")])
            c.executemany("insert into documents(title,category,content,department,created_by,created_at) values(?,?,?,?,?,?)",[
              ("Academic Regulations 2026","Policy","Minimum attendance requirement is 75 percent. Students below the threshold require academic review.",None,1,datetime.utcnow().isoformat()),
              ("CSE Semester Guidelines","Academic","CSE semester one follows approved curriculum, lab schedule and continuous assessment.","CSE",1,datetime.utcnow().isoformat()),
              ("Placement Eligibility Guide","Placement","Eligibility can consider CGPA, attendance, active backlogs and employer-specific criteria.",None,1,datetime.utcnow().isoformat())])
            c.executemany("insert into notifications(title,message,role,department,created_at) values(?,?,?,?,?)",[
              ("Attendance review","Students below 75% attendance need mentoring follow-up.","faculty","CSE",datetime.utcnow().isoformat()),
              ("Admissions pipeline","Shortlisted applications are ready for registrar review.","registrar",None,datetime.utcnow().isoformat()),
              ("Welcome to Aayam AI","Your university workspace is active.",None,None,datetime.utcnow().isoformat())])
