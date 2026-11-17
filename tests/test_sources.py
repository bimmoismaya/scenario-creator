import pytest
from docx import Document
from pypdf import PdfWriter
from app.sources import fsd_to_text, safe_name


def test_docx(tmp_path):
    d = Document()
    d.add_heading("Judul FSD", 1)
    d.add_paragraph("Paragraf satu")
    t = d.add_table(rows=1, cols=3)
    for c, v in zip(t.rows[0].cells, "abc"):
        c.text = v
    p = tmp_path / "a.docx"
    d.save(p)
    out = fsd_to_text(p)
    assert "Judul FSD" in out and "a | b | c" in out
    assert out.index("Paragraf satu") < out.index("a | b | c")


def test_pdf(tmp_path):
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 300]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
        None,
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    stream = b"BT /F1 18 Tf 20 100 Td (Halo PDF) Tj ET"
    objs[3] = b"<</Length %d>>\nstream\n" % len(stream) + stream + b"\nendstream"
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, x)
    p = tmp_path / "a.pdf"
    p.write_bytes(out)
    assert "Halo PDF" in fsd_to_text(p)


def test_bad_ext(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("x")
    with pytest.raises(ValueError):
        fsd_to_text(p)


def test_empty_file(tmp_path):
    p = tmp_path / "a.docx"
    p.write_bytes(b"")
    with pytest.raises(ValueError):
        fsd_to_text(p)


def test_blank_pdf(tmp_path):
    w = PdfWriter()
    w.add_blank_page(100, 100)
    p = tmp_path / "a.pdf"
    with open(p, "wb") as f:
        w.write(f)
    with pytest.raises(ValueError):
        fsd_to_text(p)


def test_safe_name():
    assert safe_name("../../etc/x y.docx") == "x_y.docx"
    assert safe_name("") == "file"
    assert safe_name("..") != ""
