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
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import ValidationError

from app.finalize import preview_data
from app.jobs import JobForm, JobStore, Queue
from app.sources import fsd_to_text, git_target, safe_name

MAX_UPLOAD = 20 * 1024 * 1024
MAX_ITEMS = 10  # per sumber
GIT_MAX_FILES = 900  # Starlette membatasi 1000 file per request (FSD ikut dihitung)
GIT_MAX_FILE = 1024 * 1024
GIT_MAX_TOTAL = 30 * 1024 * 1024
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
                       swagger_url: list[str] = Form([]), figma_url: list[str] = Form([]),
                       git_rel: list[str] = Form([]), git_file: list[UploadFile] = File([]), roles: str = Form(""),
                       fsd: list[UploadFile] = File(...)):
        auth(request)
        clean_list = lambda xs: [x.strip() for x in xs if x.strip()]
        swagger_url, figma_url = map(clean_list, (swagger_url, figma_url))
        if not fsd or max(len(fsd), len(swagger_url), len(figma_url)) > MAX_ITEMS:
            raise HTTPException(422, f"Maksimal {MAX_ITEMS} isian per sumber, minimal satu FSD")
        try:
            if not title.strip():
                raise ValueError("title")
            form = JobForm(dev=dev, test=test, title=title.strip(), environment=environment or "Staging",
                           scope_note=scope_note, swagger_urls=swagger_url, figma_urls=figma_url,
                           roles=roles)
        except ValidationError:
            raise HTTPException(422, "Isian tidak lengkap")
        except ValueError as e:
            raise HTTPException(422, str(e) if str(e) != "title" else "Isian tidak lengkap")
        uploads = []
        for f in fsd:
            name = safe_name(f.filename or "")
            if Path(name).suffix.lower() not in (".docx", ".pdf"):
                raise HTTPException(422, "Format file harus .docx atau .pdf")
            data = await f.read(MAX_UPLOAD + 1)
            if len(data) > MAX_UPLOAD:
                raise HTTPException(413)
            uploads.append((name, data))
        if len(git_file) != len(git_rel) or len(git_file) > GIT_MAX_FILES:
            raise HTTPException(422, f"Folder Git maksimal {GIT_MAX_FILES} file; pilih subfolder yang lebih kecil")
        repos: dict[str, str] = {}
        git_data: list[tuple[Path, bytes]] = []
        total = 0
        try:
            for f, rel in zip(git_file, git_rel):
                n, folder, sub = git_target(rel, MAX_ITEMS)
                repos[f"git_{n}"] = folder
                data = await f.read(GIT_MAX_FILE + 1)
                total += len(data)
                if len(data) > GIT_MAX_FILE or total > GIT_MAX_TOTAL:
                    raise HTTPException(413, "Folder Git terlalu besar (maks 1 MB per file, 30 MB total)")
                git_data.append((Path(f"git_{n}") / sub, data))
        except ValueError as e:
            raise HTTPException(422, str(e))
        form.git_repos = repos
        job_id = store.create(form)
        d = store.dir(job_id)
        for rel_path, data in git_data:
            (d / rel_path).parent.mkdir(parents=True, exist_ok=True)
            (d / rel_path).write_bytes(data)
        try:
            for i, (name, data) in enumerate(uploads, 1):
                (d / f"{i}_{name}").write_bytes(data)
                (d / f"fsd_{i}.md").write_text(fsd_to_text(d / f"{i}_{name}"), encoding="utf-8")
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

    app.mount("/static", StaticFiles(directory=STATIC))
    return app
