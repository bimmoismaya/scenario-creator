import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from functools import cache
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.jobs import JobForm

BUILD = Path(__file__).resolve().parent.parent / "scripts" / "build_scenario.py"


class FinalizeError(Exception):
    pass


def _recalc(xlsx: Path) -> None:
    """Hitung ulang formula lewat soffice (dimatikan dengan RECALC=0); file asli diganti hanya bila sukses."""
    soffice = shutil.which("soffice")
    if not soffice or os.environ.get("RECALC", "1") == "0":
        return
    with tempfile.TemporaryDirectory() as tmp:
        outdir = Path(tmp) / "out"
        try:
            subprocess.run(
                [soffice, f"-env:UserInstallation={(Path(tmp) / 'profile').as_uri()}", "--headless",
                 "--convert-to", "xlsx", "--outdir", str(outdir), str(xlsx)],
                capture_output=True, timeout=120, check=True)
        except (subprocess.SubprocessError, OSError):
            return
        res = outdir / xlsx.name
        if res.exists() and res.stat().st_size > 0:
            shutil.copyfile(res, xlsx)


@cache
def _build_module():
    import importlib.util
    sp = importlib.util.spec_from_file_location("build_scenario", BUILD)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    return mod


def finalize(job_dir: Path, form: "JobForm") -> Path:
    job_dir = Path(job_dir)
    spec_path = job_dir / "spec.json"
    if not spec_path.exists():
        raise FinalizeError("spec.json tidak ditemukan")
    try:
        spec = _build_module().load_spec(spec_path)
    except ValueError as e:  # SpecError subclass ValueError
        raise FinalizeError(str(e))

    meta = spec.setdefault("meta", {})
    meta.update(
        doc_number=f"TC-{form.dev}/{form.test}-{date.today().year}-1",
        system_name="Nama Sistem",
        feature_no=1,
        test_date=date.today().isoformat(),
        environment=form.environment,
        approval={},
    )
    meta.setdefault("feature_title", form.title)
    meta.setdefault("test_description", form.title)
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    out = job_dir / f"Scenario Sprint {form.test} Testing ({form.dev}).xlsx"
    try:
        r = subprocess.run([sys.executable, str(BUILD), str(spec_path), "-o", str(out)],
                           capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise FinalizeError("build_scenario timeout")
    if r.returncode != 0:
        raise FinalizeError((r.stdout + r.stderr).strip() or "build_scenario gagal")
    _recalc(out)
    return out


def preview_data(spec: dict) -> dict:
    _, warns, _ = _build_module().validate(spec)
    cases = [c for s in spec.get("sections", []) for c in s.get("cases", [])]
    return {
        "statistic": {
            "total": len(cases),
            "type": dict(Counter(c.get("type") for c in cases)),
            "priority": dict(Counter(c.get("priority") for c in cases)),
            "platform": dict(Counter(c.get("platform") for c in cases)),
        },
        "skenario": spec.get("sections", []),
        "analisa": spec.get("analysis", []),
        "bugs": spec.get("bugs", []),
        "peringatan": [str(w) for w in warns],
    }
