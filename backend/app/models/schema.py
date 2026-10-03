SCHEMA = """
create table if not exists users(
 id integer primary key,email text unique,full_name text,role text,department text,password_hash text
);
create table if not exists students(
 id integer primary key,user_id integer,enrollment_no text unique,full_name text,email text,
 department text,program text,semester integer,cgpa real,attendance real,fee_due real
);
create table if not exists faculty(
 id integer primary key,employee_no text unique,full_name text,email text,designation text,department text
);
create table if not exists courses(
 id integer primary key,code text unique,title text,semester integer,credits integer,department text
);
create table if not exists applicants(
 id integer primary key,application_no text unique,full_name text,email text,program text,score real,stage text
);
create table if not exists timetable(
 id integer primary key,course_code text,course_title text,faculty text,room text,program text,
 semester integer,section text,weekday integer,start_time text,end_time text
);
create table if not exists documents(
 id integer primary key,title text,category text,content text,department text,created_by integer,created_at text
);
create table if not exists notifications(
 id integer primary key,title text,message text,role text,department text,is_read integer default 0,created_at text
);
create table if not exists audit(
 id integer primary key,user_id integer,action text,entity text,detail text,created_at text
);
"""
