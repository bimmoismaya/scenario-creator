import json
from datetime import date
from pathlib import Path


def _file(root: Path) -> Path:
    return Path(root) / "figma_quota.json"


def status(root: Path, today: date | None = None) -> dict:
    """Kuota Figma MCP dianggap habis bila Figma pernah menolak bulan ini; otomatis pulih awal bulan berikutnya."""
    today = today or date.today()
    try:
        exhausted = json.loads(_file(root).read_text(encoding="utf-8"))["month"] == today.strftime("%Y-%m")
    except (OSError, ValueError, KeyError, TypeError):
        exhausted = False
    reset = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    return {"exhausted": exhausted, "reset": reset.isoformat()}


def mark_exhausted(root: Path) -> None:
    p = _file(root)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"month": date.today().strftime("%Y-%m")}), encoding="utf-8")
    tmp.replace(p)
