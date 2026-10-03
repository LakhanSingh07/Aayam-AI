from datetime import datetime

def log_event(db,user_id:int,action:str,entity:str,detail:str=""):
    db.execute("insert into audit(user_id,action,entity,detail,created_at) values(?,?,?,?,?)",
               (user_id,action,entity,detail,datetime.utcnow().isoformat()))
