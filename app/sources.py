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


def git_target(rel: str, max_repos: int) -> tuple[int, str, Path]:
    """`N/folder/sub/file` dari browser -> (N, folder, sub/file); tolak path berbahaya."""
    parts = rel.split("/")
    if len(parts) < 3 or not parts[0].isdigit() or not 1 <= int(parts[0]) <= max_repos:
        raise ValueError("Path file Git tidak valid")
    if any(x in ("", ".", "..") or "\\" in x or "\0" in x for x in parts):
        raise ValueError("Path file Git tidak valid")
    return int(parts[0]), safe_name(parts[1]), Path(*parts[2:])
