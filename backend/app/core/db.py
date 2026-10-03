import sqlite3
from pathlib import Path
from .config import DATABASE_PATH

def connect():
    Path(DATABASE_PATH).parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DATABASE_PATH)
    c.row_factory=sqlite3.Row
    return c
