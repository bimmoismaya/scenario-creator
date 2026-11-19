import hashlib
import io
import os
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import rarfile
from PIL import Image
from pypdf import PdfReader

MAX_FILES = 100  # gambar + PDF per file unggahan (tiap ZIP/RAR dihitung sendiri); tidak ada batas total per job
MAX_PDF_PAGES = 50
MAX_UNPACKED = 200 * 1024 * 1024  # total isi arsip setelah diekstrak (anti zip bomb)
MAX_ENTRIES = 300
MAX_SIDE = 1568  # sisi terpanjang yang dipakai model; lebih besar hanya menambah token dan waktu
# Makin banyak gambar, makin kecil sisinya agar total token per job terkendali: (maks gambar, sisi terpanjang).
_TIERS = ((20, MAX_SIDE), (60, 1152), (10**9, 896))
Image.MAX_IMAGE_PIXELS = 50_000_000

_RAR_MAGIC = (b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")


def _png(data: bytes, side: int = MAX_SIDE) -> bytes | None:
    """Gambar format apa pun yang dikenal Pillow menjadi PNG (frame pertama, maks `side` px). None bila bukan gambar."""
    try:
        im = Image.open(io.BytesIO(data))
        im.draft("RGB", (side, side))  # JPEG: dekode lebih cepat; format lain diabaikan
        im.seek(0)
        im = im.convert("RGBA" if "A" in im.getbands() or "transparency" in im.info else "RGB")
        im.thumbnail((side, side))
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


def _kind(data: bytes) -> str | None:
    """pdf, arc (ZIP/RAR), img (header dikenali Pillow), atau None."""
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:4] == b"PK\x03\x04" or data[:8] in _RAR_MAGIC or data[:7] in _RAR_MAGIC:
        return "arc"
    try:
        Image.open(io.BytesIO(data))  # hanya membaca header
        return "img"
    except Exception:  # file tidak tepercaya: format tidak dikenal atau bom piksel
        return None


def save_figma_files(uploads: list[tuple[str, bytes]], out: Path) -> list[str]:
    """Simpan gambar (PNG) dan PDF dari unggahan, termasuk isi ZIP/RAR, ke `out`. Nama file dibuat sendiri,
    nama di dalam arsip tidak pernah dipakai sebagai path. Berkas identik hanya disimpan sekali, ukuran gambar
    mengecil bila jumlahnya banyak, dan gambar diolah paralel. Mengembalikan path relatif terhadap induk `out`."""
    out.mkdir(exist_ok=True)
    seen: set[bytes] = set()
    items: list[tuple[str, bytes, bool, str]] = []  # (jenis, isi, dari unggahan langsung, nama unggahan)

    def collect(data: bytes, name: str, top: bool, depth: int, count: list[int]) -> None:
        digest = hashlib.sha256(data).digest()
        if digest in seen:
            return
        kind = _kind(data)
        if kind == "arc":
            if depth:  # arsip di dalam arsip diabaikan
                return
            seen.add(digest)
            for m in _members(name, data):
                collect(m, name, False, depth + 1, count)
            return
        if kind is None:
            if top:
                raise ValueError(f"Format file Figma tidak didukung: {name}")
            return  # berkas lain di dalam arsip (teks, __MACOSX, dll.) dilewati
        if kind == "pdf":
            try:
                if len(PdfReader(io.BytesIO(data)).pages) > MAX_PDF_PAGES:
                    raise ValueError(f"PDF lebih dari {MAX_PDF_PAGES} halaman: {name}")
            except ValueError:
                raise
            except Exception as e:
                raise ValueError(f"PDF tidak dapat dibaca: {name}") from e
        if count[0] >= MAX_FILES:
            raise ValueError(f"Maksimal {MAX_FILES} gambar/halaman desain Figma per file unggahan: {name}")
        seen.add(digest)
        count[0] += 1
        items.append((kind, data, top, name))

    for name, data in uploads:
        collect(data, name, True, 0, [0])

    imgs = [d for k, d, _, _ in items if k == "img"]
    side = next(s for limit, s in _TIERS if len(imgs) <= limit)
    with ThreadPoolExecutor(min(8, os.cpu_count() or 1)) as ex:  # Pillow melepas GIL saat decode/resize/encode
        pngs = iter(list(ex.map(lambda d: _png(d, side), imgs)))
    saved: list[str] = []
    for kind, data, top, name in items:
        body = data if kind == "pdf" else next(pngs)
        if body is None:  # header terbaca tapi isi rusak
            if top:
                raise ValueError(f"Format file Figma tidak didukung: {name}")
            continue
        p = out / f"figma_{len(saved) + 1}.{'pdf' if kind == 'pdf' else 'png'}"
        p.write_bytes(body)
        saved.append(f"{out.name}/{p.name}")
    if not saved:
        raise ValueError("Tidak ada gambar atau PDF yang ditemukan di file Figma")
    return saved
