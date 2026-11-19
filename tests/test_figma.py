import io
import json
import sys
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter

from app import figma_quota
from app.figma_files import MAX_FILES, save_figma_files
from app.prompt import build_prompt
from app.jobs import JobForm
from app.runner import figma_quota_hit
from app.server import create_app
from tests.test_server import FORM, docx_bytes, fake_run, login


def img(fmt="PNG", size=(40, 30), mode="RGB"):
    b = io.BytesIO()
    Image.new(mode, size, "red").save(b, fmt)
    return b.getvalue()


def uniq(n, size=(40, 30)):
    """n gambar PNG yang berbeda (ukuran sedikit berbeda) agar tidak digabung sebagai duplikat."""
    return {f"{i}.png": img(size=(size[0] + i, size[1])) for i in range(n)}


def pdf():
    b = io.BytesIO()
    w = PdfWriter()
    w.add_blank_page(100, 100)
    w.write(b)
    return b.getvalue()


def zipped(files: dict[str, bytes]):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)
    return b.getvalue()


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "GIF", "BMP", "WEBP", "TIFF"])
def test_any_image_becomes_png(tmp_path, fmt):
    out = save_figma_files([("a", img(fmt))], tmp_path / "figma")
    assert out == ["figma/figma_1.png"]
    assert Image.open(tmp_path / out[0]).format == "PNG"


def test_big_image_is_shrunk_and_rgba_kept(tmp_path):
    out = save_figma_files([("a", img(size=(4000, 100), mode="RGBA"))], tmp_path / "figma")
    im = Image.open(tmp_path / out[0])
    assert im.size[0] == 1568 and im.mode == "RGBA"


def test_pdf_kept_as_is(tmp_path):
    out = save_figma_files([("a", pdf())], tmp_path / "figma")
    assert out == ["figma/figma_1.pdf"] and (tmp_path / out[0]).read_bytes()[:5] == b"%PDF-"


def test_zip_unpacks_images_pdf_skips_others_and_ignores_names(tmp_path):
    z = zipped({"../../evil.png": img(), "d/b.jpg": img("JPEG"), "note.txt": b"hi", "c.pdf": pdf(), "inner.zip": zipped({"x.png": img()})})
    out = save_figma_files([("a.zip", z)], tmp_path / "figma")
    assert out == ["figma/figma_1.png", "figma/figma_2.png", "figma/figma_3.pdf"]
    assert not (tmp_path / "evil.png").exists() and sorted(p.name for p in (tmp_path / "figma").iterdir()) == [f.split("/")[1] for f in out]


def test_rejects(tmp_path):
    for bad in ([("a.txt", b"not an image")], [("a.zip", zipped({"n.txt": b"x"}))], [("a.zip", b"PK\x03\x04broken")],
                [("a.rar", b"Rar!\x1a\x07\x00broken")], [("a.pdf", b"%PDF-1.4 broken")]):
        with pytest.raises(ValueError):
            save_figma_files(bad, tmp_path / "figma")


def test_too_many_files_in_one_archive(tmp_path):
    z = zipped(uniq(MAX_FILES + 1))
    with pytest.raises(ValueError, match="Maksimal"):
        save_figma_files([("a.zip", z)], tmp_path / "figma")


def test_limit_is_per_archive_not_total(tmp_path):
    z1 = zipped(uniq(MAX_FILES))
    z2 = zipped(uniq(MAX_FILES, size=(500, 30)))
    out = save_figma_files([("a.zip", z1), ("b.zip", z2), ("c.png", img(size=(7, 7)))], tmp_path / "figma")
    assert len(out) == 2 * MAX_FILES + 1 and out[-1] == f"figma/figma_{2 * MAX_FILES + 1}.png"


def test_zip_bomb_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("app.figma_files.MAX_UNPACKED", 10)
    with pytest.raises(ValueError, match="terlalu besar"):
        save_figma_files([("a.zip", zipped({"a.png": img()}))], tmp_path / "figma")


# --- kuota ---
def test_quota_exhausted_only_after_mark_and_resets_next_month(tmp_path):
    assert figma_quota.status(tmp_path)["exhausted"] is False
    figma_quota.mark_exhausted(tmp_path)
    assert figma_quota.status(tmp_path)["exhausted"] is True
    assert figma_quota.status(tmp_path, date(2099, 1, 5))["exhausted"] is False  # bulan baru: pulih


def test_quota_reset_date_and_corrupt_file(tmp_path):
    assert figma_quota.status(tmp_path, date(2026, 12, 20))["reset"] == "2027-01-01"
    assert figma_quota.status(tmp_path, date(2026, 11, 20))["reset"] == "2026-12-01"
    (tmp_path / "figma_quota.json").write_text("{rusak")
    assert figma_quota.status(tmp_path)["exhausted"] is False


def test_quota_hit_only_for_figma_tool_error_about_limit():
    ids = set()
    call = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t1", "name": "mcp__claude_ai_Figma__get_metadata"},
        {"type": "tool_use", "id": "t2", "name": "Read"}]}}
    assert figma_quota_hit(call, ids) is False
    res = lambda tid, err, txt: {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "is_error": err, "content": txt}]}}
    assert figma_quota_hit(res("t1", True, "You have reached your monthly limit"), ids)
    assert figma_quota_hit(res("t1", True, "HTTP 429 Too Many Requests"), ids)
    assert not figma_quota_hit(res("t1", True, "File not found or private"), ids)  # error biasa bukan kuota
    assert not figma_quota_hit(res("t2", True, "limit"), ids)  # bukan tool Figma
    assert not figma_quota_hit(res("t1", False, "limit"), ids)
    assert not figma_quota_hit({"type": "user", "message": {"content": "teks"}}, ids)


def test_run_job_marks_exhausted_on_figma_limit_error(tmp_path, monkeypatch):
    from app.jobs import JobStore
    from app.runner import run_job
    events = [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "mcp__claude_ai_Figma__get_metadata"}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "monthly limit reached"}]}},
        {"type": "result", "is_error": True, "result": "stop"},
    ]
    fake = tmp_path / "fake.py"
    fake.write_text("import sys, json\nfor e in %r: print(json.dumps(e))\n" % events)
    store = JobStore(tmp_path / "jobs")
    form = JobForm(dev=1, test=2, title="x", figma_urls=["https://figma.com/design/a"])
    jid = store.create(form)
    (store.dir(jid) / "1_a.docx").write_bytes(docx_bytes())
    run_job(store, jid, form, [sys.executable, str(fake)])
    assert figma_quota.status(store.root)["exhausted"] is True


# --- server ---
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    c = TestClient(create_app(run_job=fake_run))
    login(c)
    return c


def post(c, figma=(), data=None):
    files = [("fsd", ("a.docx", docx_bytes()))] + [("figma_file", f) for f in figma]
    return c.post("/api/generate", data=data or FORM, files=files)


def test_upload_figma_saved_and_in_form(client, tmp_path):
    r = post(client, [("a.zip", zipped({"1.png": img(), "2.pdf": pdf()})), ("b.jpg", img("JPEG"))])
    assert r.status_code == 200
    d = tmp_path / "jobs" / r.json()["job_id"]
    form = json.loads((d / "form.json").read_text())
    assert form["figma_files"] == ["figma/figma_1.png", "figma/figma_2.pdf", "figma/figma_3.png"]
    assert all((d / f).exists() for f in form["figma_files"])


def test_upload_figma_bad_file_422_and_cleans_job(client, tmp_path):
    r = post(client, [("a.txt", b"bukan gambar")])
    assert r.status_code == 422 and "tidak didukung" in r.json()["detail"]
    assert not any((tmp_path / "jobs").glob("[0-9a-f]" * 12))


def test_upload_figma_too_large_413(client, monkeypatch):
    monkeypatch.setattr("app.server.MAX_FIGMA_UPLOAD", 10)
    assert post(client, [("a.png", img())]).status_code == 413


def test_quota_endpoint_requires_login_and_reports(client, tmp_path):
    assert TestClient(client.app).get("/api/figma/quota").status_code == 401
    assert client.get("/api/figma/quota").json()["exhausted"] is False
    figma_quota.mark_exhausted(tmp_path / "jobs")
    assert client.get("/api/figma/quota").json()["exhausted"] is True


def test_link_refused_when_exhausted_but_upload_still_works(client, tmp_path):
    figma_quota.mark_exhausted(tmp_path / "jobs")
    r = post(client, data={**FORM, "figma_url": "https://figma.com/design/a"})
    assert r.status_code == 422 and "Kuota Figma MCP" in r.json()["detail"]
    assert post(client, [("a.png", img())]).status_code == 200


def test_link_ok_when_not_exhausted(client):
    assert post(client, data={**FORM, "figma_url": "https://figma.com/design/a"}).status_code == 200


# --- prompt ---
def test_prompt_lists_figma_files():
    p = build_prompt(JobForm(dev=1, test=2, title="x", figma_files=["figma/figma_1.png", "figma/figma_2.pdf"]), ["fsd_1.md"])
    assert "`figma/figma_1.png`" in p and "`figma/figma_2.pdf`" in p and "pages" in p
    assert "figma_url: (kosong)" in p and "tandai case yang bergantung padanya" not in p.split("figma_url")[1].split("\n")[0]
    p2 = build_prompt(JobForm(dev=1, test=2, title="x"), ["fsd_1.md"])
    assert "figma/" not in p2 and "figma_url (baca" in p2


def test_big_jpeg_shrunk_with_draft(tmp_path):
    from app.figma_files import MAX_SIDE
    out = save_figma_files([("a.jpg", img("JPEG", size=(6000, 3000)))], tmp_path / "figma")
    assert max(Image.open(tmp_path / out[0]).size) <= MAX_SIDE


def test_build_module_loaded_once():
    from app.finalize import _build_module
    assert _build_module() is _build_module()


def test_duplicates_saved_once_and_not_counted(tmp_path):
    same = img()
    z = zipped({"a.png": same, "b.png": same, "c.pdf": pdf()})
    out = save_figma_files([("1.zip", z), ("2.png", same), ("3.pdf", pdf())], tmp_path / "figma")
    assert out == ["figma/figma_1.png", "figma/figma_2.pdf"]


def test_duplicates_do_not_use_archive_limit(tmp_path):
    members = uniq(MAX_FILES)
    members["salinan.png"] = members["0.png"]  # 101 berkas, 100 unik
    out = save_figma_files([("a.zip", zipped(members))], tmp_path / "figma")
    assert len(out) == MAX_FILES


def _widest(tmp_path, out):
    return max(Image.open(tmp_path / f).size[0] for f in out if f.endswith(".png"))


def test_adaptive_side_by_image_count(tmp_path):
    big = lambda n, w=2400: zipped({f"{i}.png": img(size=(w + i, 800)) for i in range(n)})
    assert _widest(tmp_path, save_figma_files([("a.zip", big(20))], tmp_path / "a")) == 1568
    assert _widest(tmp_path, save_figma_files([("a.zip", big(21))], tmp_path / "b")) == 1152
    assert _widest(tmp_path, save_figma_files([("a.zip", big(60))], tmp_path / "c")) == 1152
    assert _widest(tmp_path, save_figma_files([("a.zip", big(61))], tmp_path / "d")) == 896


def _pdf_n(n):
    b = io.BytesIO()
    w = PdfWriter()
    w.add_blank_page(100 + n, 100)
    w.write(b)
    return b.getvalue()


def test_pdf_not_counted_for_size_tier_and_kept(tmp_path):
    files = [(f"{i}.pdf", pdf() if i == 0 else _pdf_n(i)) for i in range(25)] + [("a.png", img(size=(3000, 100)))]
    out = save_figma_files(files, tmp_path / "figma")
    assert _widest(tmp_path, out) == 1568 and len(out) == 26


def test_parallel_processing_keeps_input_order(tmp_path):
    widths = [30 + 7 * i for i in range(40)]
    z = zipped({f"{i:02d}.png": img(size=(w, 20)) for i, w in enumerate(widths)})
    out = save_figma_files([("a.zip", z)], tmp_path / "figma")
    assert [Image.open(tmp_path / f).size[0] for f in out] == widths
