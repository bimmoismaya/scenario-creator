"""Mock API untuk uji visual UI: python tests/ui_mock_server.py (port 8001). Password: x"""
import json, time
from pathlib import Path
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, Response
import uvicorn

ROOT = Path(__file__).parent.parent
spec = json.loads((ROOT / "assets/examples/example_spec.json").read_text())
try:
    from app.finalize import preview_data
    preview = preview_data(spec)
except Exception:
    preview = {"statistic": {"total": 0, "type": {}, "priority": {}, "platform": {}},
               "skenario": spec["sections"], "analisa": spec["analysis"], "bugs": spec["bugs"]}

app = FastAPI()
t0 = {}

@app.get("/")
def index(): return FileResponse(ROOT / "app/static/index.html")

@app.post("/api/login")
def login(password: str = Form()):
    if password != "x": raise HTTPException(401)
    return {}

@app.post("/api/generate")
def gen():
    t0["t"] = time.time(); return {"job_id": "mock"}

@app.get("/api/jobs/{jid}")
def job(jid: str):
    d = time.time() - t0.get("t", 0)
    if d < 4: return {"state": "queued", "stage": "Menunggu antrian", "queue_pos": 2, "error": None}
    if d < 8: return {"state": "running", "stage": "Analisa", "queue_pos": 0, "error": None}
    return {"state": "done", "stage": "Selesai", "queue_pos": 0, "error": None, "preview": preview}

@app.get("/api/jobs/{jid}/download")
def dl(jid: str): return Response(b"x", media_type="application/octet-stream")

if __name__ == "__main__":
    uvicorn.run(app, port=8001)
