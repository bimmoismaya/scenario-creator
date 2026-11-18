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


def git_repo(raw: str, roots: list[str]) -> str:
    """Path repo git lokal yang sah: di dalam salah satu GIT_ROOTS dan berisi .git."""
    if not roots:
        raise ValueError("Sumber Git belum diaktifkan: admin perlu mengisi GIT_ROOTS")
    p = Path(raw).expanduser().resolve()
    if not any(p == r or r in p.parents for r in map(lambda x: Path(x).resolve(), roots)):
        raise ValueError(f"Folder Git di luar lokasi yang diizinkan: {raw}")
    if not (p / ".git").exists():
        raise ValueError(f"Bukan repo Git (tidak ada .git): {raw}")
    return str(p)


def git_roots() -> list[str]:
    return [r for r in os.environ.get("GIT_ROOTS", "").split(os.pathsep) if r.strip()]
