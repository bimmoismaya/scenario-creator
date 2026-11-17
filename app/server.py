import hmac
import json
import os
import secrets
import shutil
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import ValidationError

from app.finalize import preview_data
from app.jobs import JobForm, JobStore, Queue
from app.sources import fsd_to_text, safe_name

MAX_UPLOAD = 20 * 1024 * 1024
STATIC = Path(__file__).parent / "static"
SESSION_AGE = 7 * 86400


def create_app(run_job=None) -> FastAPI:
    password = os.environ.get("APP_PASSWORD", "")
    if not password:
        raise RuntimeError("APP_PASSWORD wajib diisi")
    signer = URLSafeTimedSerializer(os.environ.get("APP_SECRET") or secrets.token_hex(32))
    if run_job is None:
        from app.runner import run_job
    store = JobStore(Path(os.environ.get("JOBS_DIR", "jobs")))
    queue = Queue(store)
    fails: dict[str, list[float]] = {}  # shortcut: in-memory per process, fine for one worker
    app = FastAPI()

    store.purge()

    def _purge_loop():
        while True:
            time.sleep(3600)
            store.purge()

    threading.Thread(target=_purge_loop, daemon=True).start()

    def auth(request: Request):
        try:
            signer.loads(request.cookies.get("session", ""), max_age=SESSION_AGE)
        except BadSignature:
            raise HTTPException(401)

    def job_dir(job_id: str) -> Path:
        try:
            d = store.dir(job_id)
        except ValueError:
            raise HTTPException(404)
        if not (d / "status.json").exists():
            raise HTTPException(404)
        return d

    @app.post("/api/login")
    def login(request: Request, response: Response, password_in: str = Form(alias="password")):
        ip = request.client.host if request.client else "?"
        now = time.time()
        recent = [t for t in fails.get(ip, []) if now - t < 300]
        if len(recent) >= 3:
            raise HTTPException(429)
        if not hmac.compare_digest(password_in.encode(), password.encode()):
            recent.append(now)
            fails[ip] = recent
            raise HTTPException(429 if len(recent) >= 3 else 401)
        fails.pop(ip, None)
        response.set_cookie("session", signer.dumps("ok"), httponly=True, samesite="lax", max_age=SESSION_AGE)
        return {"ok": True}

    @app.post("/api/generate")
    async def generate(request: Request, dev: str = Form(""), test: str = Form(""), title: str = Form(""),
                       environment: str = Form("Staging"), scope_note: str = Form(""),
                       swagger_url: str = Form(""), figma_url: str = Form(""), roles: str = Form(""),
                       fsd: UploadFile = File(...)):
        auth(request)
        try:
            if not title.strip():
                raise ValueError("title")
            form = JobForm(dev=dev, test=test, title=title.strip(), environment=environment or "Staging",
                           scope_note=scope_note, swagger_url=swagger_url, figma_url=figma_url, roles=roles)
        except (ValidationError, ValueError):
            raise HTTPException(422, "Isian tidak lengkap")
        name = safe_name(fsd.filename or "")
        if Path(name).suffix.lower() not in (".docx", ".pdf"):
            raise HTTPException(422, "Format file harus .docx atau .pdf")
        data = await fsd.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413)
        job_id = store.create(form)
        d = store.dir(job_id)
        try:
            (d / name).write_bytes(data)
            (d / "fsd.md").write_text(fsd_to_text(d / name), encoding="utf-8")
        except ValueError as e:
            shutil.rmtree(d, ignore_errors=True)
            raise HTTPException(422, str(e))
        queue.submit(job_id, lambda: run_job(store, job_id, form))
        return {"job_id": job_id}

    @app.get("/api/jobs/{job_id}")
    def status(job_id: str, request: Request):
        auth(request)
        d = job_dir(job_id)
        st = store.status(job_id)
        out = {k: st.get(k) for k in ("state", "stage", "queue_pos", "error")}
        if st.get("state") == "done":
            out["preview"] = preview_data(json.loads((d / "spec.json").read_text(encoding="utf-8")))
        return out

    @app.get("/api/jobs/{job_id}/download")
    def download(job_id: str, request: Request):
        auth(request)
        files = sorted(job_dir(job_id).glob("*.xlsx"))
        if not files:
            raise HTTPException(404)
        return FileResponse(files[0], filename=files[0].name)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app
