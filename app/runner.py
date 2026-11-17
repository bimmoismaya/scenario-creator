import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from app.finalize import FinalizeError, finalize
from app.jobs import JobForm, JobStore
from app.prompt import ROOT, build_prompt
from app.sources import fsd_to_text

TIMEOUT = 3600  # dokumen besar dengan Opus bisa belasan menit; beri margin
_FIGMA = ["create_session", "get_metadata", "get_design_context", "get_screenshot",
          "get_variable_defs", "search_design_system"]  # use_figma/whoami sengaja tidak diizinkan
# "Write(*)" hanya berlaku di working directory (= folder job); repo tidak ditambahkan lewat --add-dir
# sehingga Claude tidak bisa menulis ke skill/skrip. Uji nyata: aturan "Write(spec.json)" ditolak semua.
# Bash: wildcard di tengah agar tanda kutip pada path skrip tidak memutus pencocokan.
def allowed_tools(job_dir: Path) -> list[str]:
    return ["Skill", "Read", "Write(*)", "WebFetch",
            "Bash(*build_scenario.py* spec.json --check)",
            *[f"mcp__claude_ai_Figma__{t}" for t in _FIGMA]]


def claude_args(prompt: str, job_dir: Path) -> list[str]:
    return ["-p", prompt, "--output-format", "stream-json", "--verbose",
            "--allowedTools", *allowed_tools(job_dir), "--add-dir", str(Path(job_dir).resolve()),
            "--model", os.environ.get("CLAUDE_MODEL", "opus"),
            "--permission-mode", "dontAsk", "--no-session-persistence"]


def clean(text: str, limit: int = 300) -> str:
    """Pesan aman untuk UI: tanpa email/kontrol, dipotong."""
    text = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "[email]", str(text))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def stage_of(ev: dict) -> str | None:
    """Tahap hanya dari nama tool; isi event tidak pernah dipakai."""
    if ev.get("type") != "assistant":
        return None
    stage = None
    for b in ev.get("message", {}).get("content", []):
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text":
            stage = stage or "Analisa"
        elif b.get("type") == "tool_use":
            name = str(b.get("name", ""))
            if name == "Write":
                stage = "Menulis case"
            elif name == "Bash":
                stage = "Validasi"
            else:  # Skill, Read, WebFetch, mcp__*
                stage = "Membaca sumber"
    return stage


def run_job(store: JobStore, job_id: str, form: JobForm,
            claude_cmd: list[str] | None = None, timeout: int = TIMEOUT) -> None:
    claude_cmd = claude_cmd or ["claude"]
    d = store.dir(job_id)

    def fail(msg: str) -> None:
        store.set_status(job_id, state="failed", error=clean(msg))

    store.set_status(job_id, state="running", stage="Membaca sumber", queue_pos=0)
    uploads = sorted(p for p in d.iterdir() if p.suffix.lower() in (".docx", ".pdf"))
    if not uploads:
        return fail("File FSD tidak ditemukan di folder job")
    try:
        (d / "fsd.md").write_text(fsd_to_text(uploads[0]), encoding="utf-8")
    except ValueError as e:
        return fail(str(e))
    (d / "input.json").write_text(form.model_dump_json(), encoding="utf-8")

    (d / "spec.json").unlink(missing_ok=True)
    with tempfile.TemporaryFile("w+") as err:
        try:
            proc = subprocess.Popen(claude_cmd + claude_args(build_prompt(form, "fsd.md"), d), cwd=d,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err, text=True)
        except OSError as e:
            return fail(f"Claude Code tidak dapat dijalankan: {e.strerror or type(e).__name__}")
        timed_out = threading.Event()

        def kill():
            timed_out.set()
            proc.kill()

        timer = threading.Timer(timeout, kill)
        timer.start()
        result = None
        try:
            for line in proc.stdout:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(ev, dict):
                    continue
                if ev.get("type") == "result":
                    result = ev
                elif (s := stage_of(ev)):
                    store.set_status(job_id, stage=s)
            rc = proc.wait()
        finally:
            timer.cancel()
            proc.stdout.close()
        err.seek(0)
        stderr = err.read()

    if timed_out.is_set():
        return fail(f"Timeout: Claude Code melebihi {timeout} detik")
    if rc != 0:
        return fail(f"Claude Code keluar dengan kode {rc}: {stderr}")
    if result and result.get("is_error"):
        return fail(f"Claude Code melaporkan error: {result.get('result', '')}")
    store.set_status(job_id, stage="Validasi")
    try:
        finalize(d, form)
    except FinalizeError as e:
        return fail(str(e))
    store.set_status(job_id, state="done", stage="Selesai", error=None)
