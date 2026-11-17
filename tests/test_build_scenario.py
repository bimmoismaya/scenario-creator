import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from build_scenario import quality_warnings, summary, validate  # noqa: E402

SCRIPT = Path(__file__).parent.parent / "scripts/build_scenario.py"


def case(**kw):
    c = {"type": "Positive", "priority": "P1", "platform": "API", "desc": "[API] tes",
         "steps": ["a"], "expected": ["Status 200"], "notes": "[FSD 1.1]"}
    c.update(kw)
    return c


def spec(cases, analysis=None):
    return {"meta": {"doc_number": "1", "test_description": "t", "feature_title": "f"},
            "precondition": "p", "analysis": analysis or [],
            "sections": [{"title": "S (F-01 No 1.1)", "cases": cases}]}


def mutu(s):
    return [w for w in validate(s)[1] if w.startswith("[Mutu] ")]


def has(s, text):
    return any(text in w for w in mutu(s))


def good(n=10):  # 1 P0 (10%), 4 Negative (40%)
    return [case(priority="P0" if i == 0 else "P1", type="Negative" if i < 4 else "Positive",
                 desc=f"[API] tes {i}") for i in range(n)]


def test_compliant_has_no_mutu():
    assert mutu(spec(good())) == []


def test_p0_proportion():
    cs = good()
    cs[0]["priority"] = "P1"
    assert has(spec(cs), "proporsi P0")
    assert not has(spec(cs[:5]), "proporsi P0")  # < 10 cases: skipped


def test_negative_proportion():
    cs = good()
    for c in cs:
        c["type"] = "Positive"
    assert has(spec(cs), "Negative")
    assert not has(spec(cs[:5]), "Negative")


def test_forbidden_words():
    assert has(spec([case(expected=["Nilai wajar"])]), "kata terlarang")
    assert has(spec([case(expected="hasil dll.")]), "kata terlarang")
    assert not has(spec([case(expected=["Nilai bawaan"])]), "kata terlarang")


def test_two_http_codes():
    assert has(spec([case(expected=["Status 400/404"])]), "dua kode HTTP")
    assert not has(spec([case(expected=["Status 400"])]), "dua kode HTTP")


def test_notes_source_label():
    assert has(spec([case(notes="")]), "label sumber")
    assert has(spec([case(notes="catatan")]), "label sumber")
    assert not has(spec([case(notes="[Usulan] Perlu konfirmasi SA")]), "label sumber")


def test_placeholder_needs_sa_note():
    c = case(expected=["Ambang <AMBANG_CROWDED>"])
    assert has(spec([c]), "placeholder")
    c["notes"] = "[FSD 1.1] Menunggu nilai dari SA"
    assert not has(spec([c]), "placeholder")


def test_analysis_category():
    assert has(spec([case()], [{"category": "Lain"}]), "kategori")
    assert not has(spec([case()], [{"category": "Typo FSD"}]), "kategori")


def test_summary_extended():
    out = summary(spec([case(notes="[Usulan] x", expected=["<NILAI_X>"])]))
    assert "Proporsi P1" in out and "[Usulan]: 1" in out and "placeholder: 1" in out


def test_mutu_warnings_do_not_add_errors_and_check_exits_0(tmp_path):
    s = spec([case(notes="", expected=["wajar"])])
    errors, warns, _ = validate(s)
    assert errors == [] and warns and quality_warnings(s)
    f = tmp_path / "s.json"
    f.write_text(json.dumps(s), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), str(f), "--check"], capture_output=True, text=True)
    assert r.returncode == 0 and "[Mutu]" in r.stdout


def test_ratio_without_http_context_is_not_two_codes():
    assert not has(spec([case(expected=["Tampil 150 / 200 item"])]), "dua kode HTTP")
    assert has(spec([case(expected=["Respons 400/404"])]), "dua kode HTTP")


def test_input_gagal_category_is_known():
    s = spec([case()], analysis=[{"category": "Input gagal", "ref": "x"}])
    assert not has(s, "kategori")


def test_forbidden_phrases_from_rules():
    assert has(spec([case(expected=["Data tersimpan dengan benar"])]), "kata terlarang")


def test_malformed_spec_does_not_crash():
    s = spec([case(notes=["a"], desc=None), "bukan-objek"], analysis=["teks"])
    errors, warns, n = validate(s)
    assert any("bukan objek" in e for e in errors)


def test_section_ref_accepts_free_numbering():
    s = spec([case()])
    s["sections"][0]["title"] = "Device Information (FSD No 1.a.i)"
    assert not any("referensi FSD" in w for w in validate(s)[1])


# ---- spec berbagian ----------------------------------------------------------
import pytest  # noqa: E402
from build_scenario import SpecError, load_spec  # noqa: E402


def _w(d, name, obj):
    (d / name).write_text(json.dumps(obj), encoding="utf-8")


def _parts(tmp_path):
    base = spec([case(desc="[API] a")])
    base["analysis"] = [{"finding": "x"}]
    base["parts"] = ["p1.json", "p2.json"]
    _w(tmp_path, "spec.json", base)
    _w(tmp_path, "p1.json", {"sections": [{"title": "P1 (F-02 No 1)", "cases": [case(desc="[API] b")]}],
                             "analysis": [{"finding": "y"}]})
    _w(tmp_path, "p2.json", {"sections": [{"title": "P2 (F-03 No 1)", "cases": [case(desc="[API] c")]}]})
    return tmp_path / "spec.json"


def test_load_spec_merges_parts_in_order(tmp_path):
    s = load_spec(_parts(tmp_path))
    assert "parts" not in s
    assert [x["title"][:2] for x in s["sections"]] == ["S ", "P1", "P2"]
    assert [a["finding"] for a in s["analysis"]] == ["x", "y"]
    assert validate(s)[2] == 3


def test_load_spec_without_parts(tmp_path):
    _w(tmp_path, "spec.json", spec([case()]))
    assert len(load_spec(tmp_path / "spec.json")["sections"]) == 1


def test_load_spec_missing_part(tmp_path):
    f = _parts(tmp_path)
    (tmp_path / "p2.json").unlink()
    with pytest.raises(SpecError, match="tidak ditemukan"):
        load_spec(f)


def test_load_spec_bad_part_json(tmp_path):
    f = _parts(tmp_path)
    (tmp_path / "p2.json").write_text("{x", encoding="utf-8")
    with pytest.raises(SpecError, match="bukan JSON valid"):
        load_spec(f)


@pytest.mark.parametrize("bad", ["../x.json", "/etc/passwd", "sub/../p1.json"])
def test_load_spec_rejects_escape(tmp_path, bad):
    s = spec([case()])
    s["parts"] = [bad]
    _w(tmp_path, "spec.json", s)
    with pytest.raises(SpecError, match="ditolak"):
        load_spec(tmp_path / "spec.json")


def test_check_cli_merged_and_error_exit(tmp_path):
    f = _parts(tmp_path)
    r = subprocess.run([sys.executable, str(SCRIPT), str(f), "--check"], capture_output=True, text=True)
    assert r.returncode == 0 and "Total skenario : 3" in r.stdout
    (tmp_path / "p1.json").unlink()
    r = subprocess.run([sys.executable, str(SCRIPT), str(f), "--check"], capture_output=True, text=True)
    assert r.returncode == 1 and "tidak ditemukan" in r.stdout
