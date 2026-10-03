from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from .api.routes import router
from .seed import seed

seed()
app=FastAPI(title="Aayam AI API",version="0.6.0")
app.include_router(router,prefix="/api/v1")

WEB_DIR=Path(__file__).resolve().parents[2]/"web"
app.mount("/app",StaticFiles(directory=WEB_DIR,html=True),name="web")

@app.get("/health")
def health():
    return {"status":"ok","product":"Aayam AI","version":"0.6.0"}

@app.get("/")
def root():
    return RedirectResponse("/app/")
