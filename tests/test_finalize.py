import json
import shutil
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from app.finalize import FinalizeError, finalize, preview_data

EXAMPLE = Path(__file__).parent.parent / "assets/examples/example_spec.json"
FORM = SimpleNamespace(dev="53", test="54", title="Contoh Fitur", environment="Staging")


def _job(tmp_path, spec):
    (tmp_path / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    return tmp_path


def _example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_finalize_ok(tmp_path):
    out = finalize(_job(tmp_path, _example()), FORM)
    assert out.name == "Scenario Sprint 54 Testing (53).xlsx"
    assert out.exists()
    wb = load_workbook(out)
    for name in ("Statistic", "Skenario", "Bug List", "Analisa"):
        assert name in wb.sheetnames
    assert wb["Statistic"]["C2"].value == f"TC-53/54-{date.today().year}-1"


def test_missing_spec(tmp_path):
    with pytest.raises(FinalizeError):
        finalize(tmp_path, FORM)


def test_bad_json(tmp_path):
    (tmp_path / "spec.json").write_text("{nope")
    with pytest.raises(FinalizeError):
        finalize(tmp_path, FORM)


def test_validation_error(tmp_path):
    spec = _example()
    spec["sections"][0]["cases"][0]["priority"] = "P9"
    with pytest.raises(FinalizeError, match="ERROR"):
        finalize(_job(tmp_path, spec), FORM)


def test_preview_data():
    p = preview_data(_example())
    assert set(p) == {"statistic", "skenario", "analisa", "bugs", "peringatan"}
    assert isinstance(p["peringatan"], list)
    json.dumps(p)
    assert p["skenario"] and p["analisa"]


def test_preview_peringatan_mutu():
    spec = _example()
    cases = [c for s in spec["sections"] for c in s["cases"]]
    cases += [dict(cases[0], description=f"extra {i}") for i in range(10)]
    spec["sections"][0]["cases"] = cases[:0] + spec["sections"][0]["cases"] + cases[-10:]
    for s in spec["sections"]:
        for c in s["cases"]:
            c["priority"] = "P0"
    p = preview_data(spec)
    assert any("[Mutu]" in w for w in p["peringatan"])
    json.dumps(p)


def test_finalize_with_parts(tmp_path):
    ex = _example()
    total = sum(len(s["cases"]) for s in ex["sections"])
    secs = ex.pop("sections")
    ex["parts"] = ["a.json", "b.json"]
    (tmp_path / "a.json").write_text(json.dumps({"sections": secs[:1]}), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps({"sections": secs[1:]}), encoding="utf-8")
    out = finalize(_job(tmp_path, ex), FORM)
    merged = json.loads((tmp_path / "spec.json").read_text(encoding="utf-8"))
    assert "parts" not in merged and len(merged["sections"]) == len(secs)
    ws = load_workbook(out)["Skenario"]
    ids = [r[0] for r in ws.iter_rows(min_row=4, values_only=True) if isinstance(r[0], int)]
    assert len(ids) == total


def test_finalize_missing_part(tmp_path):
    ex = _example()
    ex["parts"] = ["hilang.json"]
    with pytest.raises(FinalizeError, match="tidak ditemukan"):
        finalize(_job(tmp_path, ex), FORM)
