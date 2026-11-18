import os
import re
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader


def safe_name(filename: str) -> str:
    base = re.split(r"[\\/]", filename)[-1]
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip(".")
    return base or "file"


def _docx(path: Path) -> str:
    doc = Document(str(path))
    lines = []
    for el in doc.element.body.iterchildren():
        if el.tag.endswith("}p"):
            lines.append(Paragraph(el, doc).text)
        elif el.tag.endswith("}tbl"):
            for row in Table(el, doc).rows:
                lines.append(" | ".join(c.text.strip() for c in row.cells))
    return "\n".join(lines)


def fsd_to_text(path: Path) -> str:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in (".docx", ".pdf"):
        raise ValueError("Format file harus .docx atau .pdf")
    try:
        if ext == ".docx":
            text = _docx(path)
        else:
            text = "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    except Exception as e:
        raise ValueError(f"File tidak dapat dibaca: {e}") from e
    if not text.strip():
        raise ValueError("File kosong atau tidak berisi teks")
    return text


def git_roots() -> list[Path]:
    return [Path(r).resolve() for r in os.environ.get("GIT_ROOTS", "").split(os.pathsep) if r.strip()]


def git_browse(path: str) -> Path:
    """Folder yang boleh ditelusuri di pemilih: root atau apa pun di dalam GIT_ROOTS (symlink ikut diselesaikan)."""
    try:
        real = Path(path).resolve(strict=True) if os.path.isabs(path) else None
    except (OSError, ValueError):
        real = None
    if real is None or not real.is_dir():
        raise ValueError("Folder Git tidak ditemukan")
    if not any(real.is_relative_to(r) for r in git_roots()):
        raise ValueError("Folder Git di luar GIT_ROOTS")
    return real


def git_dir(path: str) -> Path:
    """Folder yang boleh dipilih: repo Git di dalam GIT_ROOTS, bukan root itu sendiri."""
    real = git_browse(path)
    if real in git_roots() or not (real / ".git").exists():
        raise ValueError("Pilih folder repo Git (berisi .git), bukan folder induknya")
    return real
