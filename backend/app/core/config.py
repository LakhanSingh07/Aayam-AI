import os
DATABASE_PATH=os.getenv("DB_PATH","/tmp/aayam.db")
JWT_SECRET=os.getenv("JWT_SECRET","change-me")
API_PREFIX="/api/v1"
