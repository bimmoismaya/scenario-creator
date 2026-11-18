"""Jalankan server di Linux, macOS, dan Windows: python run.py (membaca .env di folder ini)."""
import os
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip("\"'")


if __name__ == "__main__":
    os.chdir(ROOT)
    load_env(ROOT / ".env")
    uvicorn.run("app.server:create_app", factory=True, host="0.0.0.0", port=8000)
