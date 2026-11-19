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

from app import figma_quota
from app.figma_files import save_figma_files
from app.finalize import preview_data
from app.jobs import JobForm, JobStore, Queue
from app.sources import fsd_to_text, git_browse, git_dir, git_roots, safe_name

MAX_UPLOAD = 20 * 1024 * 1024
MAX_FIGMA_UPLOAD = 50 * 1024 * 1024  # arsip desain lebih besar dari FSD
MAX_ITEMS = 10  # per sumber
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
                       git_path: list[str] = Form([]), roles: str = Form(""),
                       fsd: list[UploadFile] = File(...), figma_file: list[UploadFile] = File([])):
        auth(request)
        clean_list = lambda xs: [x.strip() for x in xs if x.strip()]
        swagger_url, figma_url = map(clean_list, (swagger_url, figma_url))
        git_path = clean_list(git_path)
        if not fsd or max(len(fsd), len(swagger_url), len(figma_url), len(git_path), len(figma_file)) > MAX_ITEMS:
            raise HTTPException(422, f"Maksimal {MAX_ITEMS} isian per sumber, minimal satu FSD")
        if figma_url and figma_quota.status(store.root)["exhausted"]:
            raise HTTPException(422, "Kuota Figma MCP bulan ini sudah habis. Gunakan Upload file Figma, atau coba lagi bulan depan.")
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
        figma_uploads = []
        for f in figma_file:
            data = await f.read(MAX_FIGMA_UPLOAD + 1)
            if len(data) > MAX_FIGMA_UPLOAD:
                raise HTTPException(413)
            figma_uploads.append((safe_name(f.filename or ""), data))
        try:
            repos = {str(d): d.name for d in map(git_dir, git_path)}
        except ValueError as e:
            raise HTTPException(422, str(e))
        # Edit(repo) menolak penulisan; bila folder job ada di dalam repo, hasil Claude ikut terblokir.
        if any(store.root.resolve().is_relative_to(r) for r in repos):
            raise HTTPException(422, "Repo ini berisi folder hasil (JOBS_DIR). Pilih repo lain atau pindahkan JOBS_DIR ke luar repo.")
        form.git_repos = repos
        job_id = store.create(form)
        d = store.dir(job_id)
        try:
            for i, (name, data) in enumerate(uploads, 1):
                (d / f"{i}_{name}").write_bytes(data)
                (d / f"fsd_{i}.md").write_text(fsd_to_text(d / f"{i}_{name}"), encoding="utf-8")
            if figma_uploads:
                form.figma_files = save_figma_files(figma_uploads, d / "figma")
                (d / "form.json").write_text(form.model_dump_json(), encoding="utf-8")
        except ValueError as e:
            shutil.rmtree(d, ignore_errors=True)
            raise HTTPException(422, str(e))
        queue.submit(job_id, lambda: run_job(store, job_id, form))
        return {"job_id": job_id}

    @app.get("/api/figma/quota")
    def figma_quota_status(request: Request):
        auth(request)
        return figma_quota.status(store.root)

    @app.get("/api/git/dirs")
    def git_dirs(request: Request, path: str = ""):
        auth(request)
        try:
            base = git_browse(path) if path else None
            roots = git_roots()
            kids = roots if base is None else sorted(c for c in base.iterdir() if c.is_dir())
            # symlink yang menunjuk keluar GIT_ROOTS tidak ditampilkan
            dirs = [{"name": str(k) if base is None else k.name, "path": str(k.resolve()), "repo": (k / ".git").exists()}
                    for k in kids if any(k.resolve().is_relative_to(r) for r in roots)]
        except (ValueError, OSError) as e:
            raise HTTPException(422, str(e))
        parent = "" if base is None or base in roots else str(base.parent)
        return {"path": str(base or ""), "parent": parent, "repo": bool(base and (base / ".git").exists()), "dirs": dirs}

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
