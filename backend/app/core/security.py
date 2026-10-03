import base64, hashlib, hmac, json
from datetime import datetime, timedelta
from fastapi import HTTPException
from .config import JWT_SECRET

SALT=b"aayam-core-v1"

def hash_password(password:str)->str:
    return hashlib.pbkdf2_hmac("sha256",password.encode(),SALT,150000).hex()

def issue_token(user_id:int)->str:
    payload={"id":user_id,"exp":(datetime.utcnow()+timedelta(hours=12)).isoformat()}
    raw=base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig=hmac.new(JWT_SECRET.encode(),raw.encode(),hashlib.sha256).hexdigest()
    return raw+"."+sig

def decode_token(token:str)->dict:
    try:
        raw,sig=token.split(".",1)
        expected=hmac.new(JWT_SECRET.encode(),raw.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig,expected): raise ValueError()
        data=json.loads(base64.urlsafe_b64decode(raw+"="*(-len(raw)%4)))
        if datetime.fromisoformat(data["exp"])<datetime.utcnow(): raise ValueError()
        return data
    except Exception:
        raise HTTPException(401,"Invalid or expired token")
