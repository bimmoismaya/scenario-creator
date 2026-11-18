import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

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
    return ["Skill", "Read", "Write(*)", "WebFetch", "Glob", "Grep",
            "Bash(*build_scenario.py* spec.json --check)",
            *[f"mcp__claude_ai_Figma__{t}" for t in _FIGMA]]


# Rahasia umum di repo yang tidak boleh dibaca Claude (isinya bisa bocor ke spec/Excel).
_SECRETS = ["Read(**/.env*)", "Read(**/*.pem)", "Read(**/*.key)", "Read(**/id_rsa*)"]


def claude_args(prompt: str, job_dir: Path, repos: tuple | list = (), swagger_urls: tuple | list = ()) -> list[str]:
    # WebFetch hanya ke host Swagger yang diisi user; tanpa link, tanpa WebFetch.
    hosts = sorted({h for u in swagger_urls if (h := urlparse(u).hostname)})
    tools = [t for t in allowed_tools(job_dir) if t != "WebFetch"] + [f"WebFetch(domain:{h})" for h in hosts]
    # Repo dibaca langsung dari disk; Edit(...) menolak semua penulisan ke repo (deny menang atas "Write(*)").
    deny = [*_SECRETS, *[f"Edit(/{r}/**)" for r in repos]]
    return ["-p", prompt, "--output-format", "stream-json", "--verbose",
            "--allowedTools", *tools, "--add-dir", str(Path(job_dir).resolve()),
            *[x for r in repos for x in ("--add-dir", r)],
            "--disallowedTools", *deny,
            "--model", os.environ.get("CLAUDE_MODEL", "opus"),
            "--permission-mode", "dontAsk", "--no-session-persistence"]


def clean(text: str, limit: int = 300) -> str:
    """Pesan aman untuk UI: tanpa email/kontrol, dipotong."""
    text = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "[email]", str(text))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def stage_of(ev: dict, n: dict | None = None) -> str | None:
    """Tahap hanya dari nama tool dan awalan nama file; isi event tidak pernah dipakai. `n` = penghitung langkah."""
    if ev.get("type") != "assistant":
        return None
    n = n if n is not None else {}
    stage = None
    for b in ev.get("message", {}).get("content", []):
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text":
            stage = stage or "Menganalisa"
        elif b.get("type") == "tool_use":
            name, inp = str(b.get("name", "")), b.get("input")
            path = Path(str((inp or {}).get("file_path", "")) if isinstance(inp, dict) else "").name
            if name == "Write":
                n["w"] = n.get("w", 0) + 1
                stage = f"Menulis case (berkas ke-{n['w']})"
            elif name == "Bash":
                stage = "Memvalidasi spec"
            elif name == "Read" and path.startswith("fsd_"):
                stage = "Membaca FSD"
            elif name in ("Read", "Glob", "Grep"):
                n["r"] = n.get("r", 0) + 1
                stage = f"Menelusuri kode repo ({n['r']} langkah)"
            elif name == "WebFetch":
                stage = "Membaca Swagger"
            elif name.startswith("mcp__"):
                stage = "Membaca desain Figma"
            else:
                stage = "Memuat skill QA"
    return stage


def run_job(store: JobStore, job_id: str, form: JobForm,
            claude_cmd: list[str] | None = None, timeout: int = TIMEOUT) -> None:
    claude_cmd = claude_cmd or ["claude"]
    d = store.dir(job_id)

    def fail(msg: str) -> None:
        store.set_status(job_id, state="failed", error=clean(msg))

    store.set_status(job_id, state="running", stage="Membaca sumber", queue_pos=0)
    # Urut numerik menurut awalan "{i}_" dari server ("10_x" sesudah "2_x").
    num = lambda p: (int(m[1]) if (m := re.match(r"(\d+)_", p.name)) else 10**9, p.name)
    uploads = sorted((p for p in d.iterdir() if p.suffix.lower() in (".docx", ".pdf")), key=num)
    if not uploads:
        return fail("File FSD tidak ditemukan di folder job")
    try:
        for i, u in enumerate(uploads, 1):
            (d / f"fsd_{i}.md").write_text(fsd_to_text(u), encoding="utf-8")
    except ValueError as e:
        return fail(str(e))
    (d / "input.json").write_text(form.model_dump_json(), encoding="utf-8")

    (d / "spec.json").unlink(missing_ok=True)
    with tempfile.TemporaryFile("w+") as err:
        try:
            proc = subprocess.Popen(claude_cmd + claude_args(build_prompt(form, [f"fsd_{i}.md" for i in range(1, len(uploads) + 1)]), d, list(form.git_repos), form.swagger_urls), cwd=d,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err, text=True)
        except OSError as e:
            return fail(f"Claude Code tidak dapat dijalankan: {e.strerror or type(e).__name__}")
        timed_out = threading.Event()

        def kill():
            timed_out.set()
            proc.kill()

        timer = threading.Timer(timeout, kill)
        timer.start()
        result, steps = None, {}
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
                elif (s := stage_of(ev, steps)):
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
