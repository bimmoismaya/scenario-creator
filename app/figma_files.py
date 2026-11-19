import io
import tempfile
import zipfile
from pathlib import Path

import rarfile
from PIL import Image
from pypdf import PdfReader

MAX_FILES = 100  # gambar + PDF per job; tiap file dibaca Claude satu per satu
MAX_PDF_PAGES = 50
MAX_UNPACKED = 200 * 1024 * 1024  # total isi arsip setelah diekstrak (anti zip bomb)
MAX_ENTRIES = 300
MAX_SIDE = 2000
Image.MAX_IMAGE_PIXELS = 50_000_000

_RAR_MAGIC = (b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")


def _png(data: bytes) -> bytes | None:
    """Gambar format apa pun yang dikenal Pillow menjadi PNG (frame pertama, maks 2000 px). None bila bukan gambar."""
    try:
        im = Image.open(io.BytesIO(data))
        im.seek(0)
        im = im.convert("RGBA" if "A" in im.getbands() or "transparency" in im.info else "RGB")
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        im.save(out, "PNG")
        return out.getvalue()
    except Exception:  # file tidak tepercaya: format rusak/tidak dikenal/bom piksel semuanya berarti "bukan gambar"
        return None


def _members(name: str, data: bytes) -> list[bytes]:
    try:
        if data[:4] == b"PK\x03\x04":
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                infos = [i for i in z.infolist() if not i.is_dir()]
                if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_UNPACKED:
                    raise ValueError(f"Arsip terlalu besar: {name}")
                return [z.read(i) for i in infos]
        with tempfile.TemporaryDirectory() as tmp:  # unrar membaca dari path, bukan dari memori
            p = Path(tmp) / "a.rar"
            p.write_bytes(data)
            with rarfile.RarFile(p) as r:
                infos = [i for i in r.infolist() if not i.is_dir()]
                if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_UNPACKED:
                    raise ValueError(f"Arsip terlalu besar: {name}")
                return [r.read(i) for i in infos]
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, rarfile.Error) as e:
        hint = " (RAR butuh unrar, 7z, atau bsdtar di server)" if isinstance(e, rarfile.RarCannotExec) else ""
        raise ValueError(f"Arsip tidak dapat dibuka atau diproteksi password: {name}{hint}") from e


def save_figma_files(uploads: list[tuple[str, bytes]], out: Path) -> list[str]:
    """Simpan gambar (PNG) dan PDF dari unggahan, termasuk isi ZIP/RAR, ke `out`. Nama file dibuat sendiri,
    nama di dalam arsip tidak pernah dipakai sebagai path. Mengembalikan path relatif terhadap induk `out`."""
    out.mkdir(exist_ok=True)
    saved: list[str] = []

    def add(data: bytes, top: bool, name: str, depth: int = 0) -> None:
        if data[:5] == b"%PDF-":
            try:
                if len(PdfReader(io.BytesIO(data)).pages) > MAX_PDF_PAGES:
                    raise ValueError(f"PDF lebih dari {MAX_PDF_PAGES} halaman: {name}")
            except ValueError:
                raise
            except Exception as e:
                raise ValueError(f"PDF tidak dapat dibaca: {name}") from e
            ext, body = "pdf", data
        elif data[:4] == b"PK\x03\x04" or data[:8] in _RAR_MAGIC or data[:7] in _RAR_MAGIC:
            if depth:  # arsip di dalam arsip diabaikan
                return
            for m in _members(name, data):
                add(m, False, name, depth + 1)
            return
        elif (body := _png(data)) is not None:
            ext = "png"
        elif top:
            raise ValueError(f"Format file Figma tidak didukung: {name}")
        else:
            return  # berkas lain di dalam arsip (teks, __MACOSX, dll.) dilewati
        if len(saved) >= MAX_FILES:
            raise ValueError(f"Maksimal {MAX_FILES} gambar/halaman desain Figma per job")
        p = out / f"figma_{len(saved) + 1}.{ext}"
        p.write_bytes(body)
        saved.append(f"{out.name}/{p.name}")

    for name, data in uploads:
        add(data, True, name)
    if not saved:
        raise ValueError("Tidak ada gambar atau PDF yang ditemukan di file Figma")
    return saved
