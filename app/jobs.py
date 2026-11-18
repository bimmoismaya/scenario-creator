import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from queue import Queue as _Q

from pydantic import BaseModel, Field

_ID = re.compile(r"[0-9a-f]{12}")


class JobForm(BaseModel):
    dev: int
    test: int
    title: str
    environment: str = "Staging"
    scope_note: str = ""
    swagger_urls: list[str] = []
    figma_urls: list[str] = []
    git_repos: dict[str, str] = {}  # path folder di server -> nama folder, mis. {"/home/u/git/myrepo": "myrepo"}
    roles: str = Field("", max_length=500)


class JobStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def dir(self, job_id: str) -> Path:
        if not isinstance(job_id, str) or not _ID.fullmatch(job_id):
            raise ValueError(f"invalid job_id: {job_id!r}")
        return self.root / job_id

    def create(self, form: JobForm) -> str:
        job_id = uuid.uuid4().hex[:12]
        self.dir(job_id).mkdir()
        (self.dir(job_id) / "form.json").write_text(form.model_dump_json(), encoding="utf-8")
        self._write(job_id, {"state": "queued", "stage": "", "error": None, "queue_pos": 0})
        return job_id

    def status(self, job_id: str) -> dict:
        return json.loads((self.dir(job_id) / "status.json").read_text(encoding="utf-8"))

    def set_status(self, job_id: str, **fields) -> None:
        with self._lock:
            self._write(job_id, {**self.status(job_id), **fields})

    def _write(self, job_id: str, data: dict) -> None:
        p = self.dir(job_id) / "status.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(p)

    def purge(self, older_than_seconds: int = 86400) -> None:
        cutoff = time.time() - older_than_seconds
        for d in self.root.iterdir():
            if _ID.fullmatch(d.name) and d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)


class Queue:
    """Single worker thread. queue_pos = jobs ahead (running one included)."""

    def __init__(self, store: JobStore):
        self.store = store
        self._q: _Q = _Q()
        self._ids: list[str] = []  # running first, then waiting
        self._lock = threading.Lock()
        threading.Thread(target=self._work, daemon=True).start()

    def submit(self, job_id: str, fn) -> None:
        with self._lock:
            pos = len(self._ids)
            self._ids.append(job_id)
        self.store.set_status(job_id, queue_pos=pos)
        self._q.put((job_id, fn))

    def _work(self) -> None:
        while True:
            job_id, fn = self._q.get()
            try:
                fn()
            except Exception as e:
                self.store.set_status(job_id, state="failed", error=f"Kesalahan internal ({type(e).__name__})")
            with self._lock:
                self._ids.remove(job_id)
                ids = list(self._ids)
            for i, j in enumerate(ids):
                self.store.set_status(j, queue_pos=i)
