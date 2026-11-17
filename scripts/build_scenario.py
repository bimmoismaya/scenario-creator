#!/usr/bin/env python3
"""
Build a test-scenario workbook (company format) from a JSON spec.

Usage:
    python build_scenario.py spec.json -o "Scenario Sprint 54 Testing (53).xlsx"
    python build_scenario.py spec.json --check        # validate only, no file

The workbook keeps the company layout: Statistic / Skenario / Bug List
(+ optional "Analisa" sheet when spec["analysis"] is non-empty).
See references/template-format.md for the spec schema and conventions.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import Counter

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(HERE, "..", "assets", "template.xlsx")

ALLOWED = {
    "type": {"Positive", "Negative"},
    "method": {"Manual", "Automated", "Load"},
    "priority": {"P0", "P1", "P2", "P3"},
    "status": {"Pending", "Pass", "Failed", "Blocker"},
}
# Platform atoms; combinations are joined with " / " (e.g. "API / Database").
PLATFORM_ORDER = ["Mobile Apps", "PWA", "Website", "API", "Backend", "Database"]
PLATFORM_ATOMS = set(PLATFORM_ORDER)


def norm_platform(p):
    """Canonical order so 'API / Mobile Apps' and 'Mobile Apps / API' are counted as one value."""
    atoms = [a.strip() for a in str(p).split("/") if a.strip()]
    atoms = sorted(set(atoms), key=lambda a: PLATFORM_ORDER.index(a) if a in PLATFORM_ORDER else 99)
    return " / ".join(atoms)

# ---- styles copied from the company template --------------------------------
ARIAL = Font(name="Arial", size=10)
ARIAL_B = Font(name="Arial", size=10, bold=True)
FILL_HEADER = PatternFill("solid", fgColor="FFC9DAF8")
FILL_PRECOND = PatternFill("solid", fgColor="FFFFF2CC")
FILL_SECTION = PatternFill("solid", fgColor="FFD9EAD3")
FILL_ANALYSIS_HDR = PatternFill("solid", fgColor="FFCFE2F3")
THIN = Side(style="thin")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(vertical="center", wrap_text=True)
TOP_LEFT = Alignment(vertical="top", wrap_text=True)

HEADERS = ["ID", "Type Case", "Test Method", "Priority", "Test Case Description",
           "Step To Reproduce", "Expected Result", "Actual Result", "Platform",
           "Status", "Bug ID (Refer To)", "Attachment", "Notes"]
WIDTHS = {"A": 4.25, "B": 13, "C": 14, "D": 9.88, "E": 38.88, "F": 38.88,
          "G": 46.38, "H": 38.88, "I": 14.63, "J": 14.63, "K": 14.63,
          "L": 14.63, "M": 32.38}
CENTER_COLS = {1, 2, 3, 4, 9, 10}

ANALYSIS_HEADERS = ["No", "Kategori", "Area / Ref", "Sumber", "Temuan",
                    "Dampak ke Testing", "Confidence", "Pertanyaan / Rekomendasi",
                    "Skenario Terkait"]
ANALYSIS_WIDTHS = [5, 14, 22, 24, 55, 40, 14, 45, 16]


def numbered(items):
    """List of strings -> '1. a\n2. b'. A plain string is returned unchanged."""
    if isinstance(items, str):
        return items
    return "\n".join(f"{i}. {s}" for i, s in enumerate(items, 1))


# ---- quality checks (warnings only, never errors) ------------------------------
FORBIDDEN_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in (
        "wajar", "mendekati", "sesuai kesepakatan", "kondisi tertentu", "dan lain-lain", "dll",
        "dengan benar", "melewati batas")) + r")\b")
TWO_HTTP_RE = re.compile(r"\b[1-5]\d\d\s*/\s*[1-5]\d\d\b")
HTTP_CONTEXT_RE = re.compile(r"status|kode|http|respons|response")
PLACEHOLDER_RE = re.compile(r"<[A-Z0-9_]+>")
SOURCE_LABELS = ("[FSD", "[Swagger", "[Figma", "[Usulan")
ANALYSIS_CATEGORIES = {"diskrepansi", "ambigu", "gap", "risiko", "typo fsd", "konflik", "nilai hilang", "input gagal"}


def _text(v):
    return v if isinstance(v, str) else "\n".join(map(str, v or []))


def quality_warnings(spec):
    """Mutu checks from the prompt rules 6.2/6.3/7; each item starts with '[Mutu] '."""
    w = []
    cases = [c for s in spec.get("sections", []) if isinstance(s, dict) for c in s.get("cases", []) if isinstance(c, dict)]
    total = len(cases)
    if total >= 10:
        p0 = sum(1 for c in cases if c.get("priority") == "P0") / total
        if not 0.05 <= p0 <= 0.20:
            w.append(f"[Mutu] proporsi P0 {p0:.0%} di luar 5-20%")
        neg = sum(1 for c in cases if c.get("type") == "Negative") / total
        if neg < 0.30:
            w.append(f"[Mutu] proporsi Negative {neg:.0%} di bawah 30%")
    for n, c in enumerate(cases, 1):
        where = f"case #{n} ({str(c.get('desc') or '')[:50]})"
        exp, notes = _text(c.get("expected")), _text(c.get("notes")).strip()
        bad = sorted(set(FORBIDDEN_RE.findall(exp.lower())))
        if bad:
            w.append(f"[Mutu] {where}: expected memuat kata terlarang {bad}")
        if TWO_HTTP_RE.search(exp) and HTTP_CONTEXT_RE.search(exp.lower()):
            w.append(f"[Mutu] {where}: expected memuat dua kode HTTP, pilih satu")
        if not notes.startswith(SOURCE_LABELS):
            w.append(f"[Mutu] {where}: Notes tidak diawali label sumber [FSD|Swagger|Figma|Usulan]")
        if PLACEHOLDER_RE.search(exp) and "Menunggu nilai dari SA" not in notes:
            w.append(f"[Mutu] {where}: expected berisi placeholder tetapi Notes tanpa 'Menunggu nilai dari SA'")
    for i, it in enumerate(spec.get("analysis") or [], 1):
        if not isinstance(it, dict):
            continue
        cat = str(it.get("category", "")).strip()
        if cat and cat.lower() not in ANALYSIS_CATEGORIES:
            w.append(f"[Mutu] analysis #{i}: kategori '{cat}' tidak dikenal; pakai Diskrepansi, Ambigu, Gap, Risiko, Typo FSD, Konflik, Nilai hilang, Input gagal")
    return w


# ---- validation --------------------------------------------------------------
def validate(spec):
    errors, warns = [], []
    meta = spec.get("meta", {})
    for k in ("doc_number", "test_description", "feature_title"):
        if not meta.get(k):
            errors.append(f"meta.{k} kosong")
    if not spec.get("precondition"):
        warns.append("precondition kosong")
    seen_desc = {}
    n = 0
    for si, sec in enumerate(spec.get("sections", []), 1):
        if not isinstance(sec, dict):
            errors.append(f"section #{si} bukan objek")
            continue
        title = str(sec.get("title") or "")
        if not title:
            errors.append(f"section #{si} tanpa title")
        if not re.search(r"\([^)]*\d[^)]*\)", title) and not any(w in title for w in ("Regresi", "Umum", "Non-Fungsional", "Lintas")):
            warns.append(f"section '{title}' tidak menyebut referensi FSD dalam kurung, mis. (F-xx No x.y)")
        if not sec.get("cases"):
            warns.append(f"section '{title}' tidak punya case")
        for c in sec.get("cases", []):
            n += 1
            if not isinstance(c, dict):
                errors.append(f"case #{n} bukan objek")
                continue
            where = f"case #{n} ({str(c.get('desc') or '')[:50]})"
            for key, allowed in (("type", ALLOWED["type"]), ("priority", ALLOWED["priority"])):
                if c.get(key) not in allowed:
                    errors.append(f"{where}: {key}='{c.get(key)}' tidak valid {sorted(allowed)}")
            if c.get("method", "Manual") not in ALLOWED["method"]:
                errors.append(f"{where}: method tidak valid")
            if c.get("status", "Pending") not in ALLOWED["status"]:
                errors.append(f"{where}: status tidak valid")
            atoms = [p.strip() for p in str(c.get("platform", "")).split("/")]
            bad = [a for a in atoms if a not in PLATFORM_ATOMS]
            if bad:
                errors.append(f"{where}: platform tidak dikenal {bad}; pakai {sorted(PLATFORM_ATOMS)}")
            d = str(c.get("desc") or "")
            if not d.startswith("["):
                warns.append(f"{where}: desc sebaiknya diawali tag area, mis. '[Ongoing API] ...'")
            if not c.get("steps") or not c.get("expected"):
                errors.append(f"{where}: steps/expected wajib diisi")
            if d in seen_desc:
                warns.append(f"{where}: deskripsi duplikat dengan case #{seen_desc[d]}")
            seen_desc[d] = n
    if n == 0:
        errors.append("tidak ada test case")
    warns.extend(quality_warnings(spec))
    return errors, warns, n


def summary(spec):
    cases = [c for s in spec["sections"] for c in s["cases"]]
    out = [f"Total skenario : {len(cases)}"]
    for key in ("type", "priority", "platform"):
        cnt = Counter(c.get(key) for c in cases)
        out.append(f"{key:<15}: " + ", ".join(f"{k}={v}" for k, v in sorted(cnt.items())))
    neg = sum(1 for c in cases if c["type"] == "Negative")
    out.append(f"Rasio Negative : {neg / len(cases):.0%}")
    for p in sorted(ALLOWED["priority"]):
        k = sum(1 for c in cases if c.get("priority") == p)
        out.append(f"Proporsi {p:<8}: {k / len(cases):.0%}")
    out.append(f"Persen Negative: {neg / len(cases):.0%}")
    out.append(f"Case berlabel [Usulan]: {sum(1 for c in cases if (c.get('notes') or '').lstrip().startswith('[Usulan'))}")
    out.append(f"Case dengan placeholder: {sum(1 for c in cases if PLACEHOLDER_RE.search(_text(c.get('expected'))))}")
    flagged = sum(1 for c in cases if "verifikasi" in (c.get("notes") or "").lower())
    out.append(f"Case dengan catatan 'Perlu verifikasi': {flagged}")
    out.append("Per section:")
    for s in spec["sections"]:
        out.append(f"  - {len(s['cases']):>3}  {s['title']}")
    return "\n".join(out)


# ---- writers -----------------------------------------------------------------
def style_row(ws, r, fill=None, font=ARIAL, cols=13):
    for col in range(1, cols + 1):
        cell = ws.cell(r, col)
        cell.font = font
        cell.border = BORDER
        if fill:
            cell.fill = fill


def write_statistic(wb, meta):
    st = wb["Statistic"]
    st["C1"] = meta.get("system_name", "Nama Sistem")
    st["C2"] = meta["doc_number"]
    d = meta.get("test_date")
    st["C3"] = dt.datetime.strptime(d, "%Y-%m-%d") if d else dt.datetime.now()
    st["C3"].number_format = "mmmm yyyy"
    st["C4"] = meta["test_description"]
    st["C5"] = meta.get("environment", "Staging")
    appr = meta.get("approval", {})
    st["E2"] = appr.get("technical_lead", "Nama (Technical Lead)")
    st["E3"] = appr.get("qa_lead", "Nama (QA Lead)")
    st["E4"] = appr.get("system_analyst", "Nama (System Analyst)")
    if meta.get("review_by"):
        st["E5"] = meta["review_by"]


def write_skenario(wb, spec):
    ws = wb["Skenario"]
    meta = spec["meta"]
    for col, w in WIDTHS.items():
        ws.column_dimensions[col].width = w

    # Row 1: feature number | feature title | scope
    ws["C1"] = meta.get("feature_no", 1)
    ws["C1"].fill, ws["C1"].border, ws["C1"].font = FILL_PRECOND, BORDER, ARIAL
    ws["C1"].alignment = Alignment(horizontal="right", vertical="center", wrap_text=True)
    ws.merge_cells("D1:E1")
    ws["D1"] = meta["feature_title"]
    for col in ("D", "E"):
        ws[f"{col}1"].fill, ws[f"{col}1"].border = FILL_PRECOND, BORDER
    ws["D1"].font, ws["D1"].alignment = ARIAL_B, LEFT
    ws["F1"] = meta.get("scope", "API/Backend/Frontend")
    ws["F1"].fill, ws["F1"].border, ws["F1"].font, ws["F1"].alignment = FILL_SECTION, BORDER, ARIAL, LEFT

    # Row 2: headers
    for i, h in enumerate(HEADERS, 1):
        c = ws.cell(2, i, h)
        c.font, c.fill, c.border, c.alignment = ARIAL_B, FILL_HEADER, BORDER, CENTER

    # Row 3: precondition (B3:J3 merged)
    ws.merge_cells("B3:J3")
    ws["B3"] = spec.get("precondition", "Precondition:\n-")
    for col in range(1, 14):
        ws.cell(3, col).border = BORDER
        ws.cell(3, col).font = ARIAL
    for col in range(2, 11):
        ws.cell(3, col).fill = FILL_PRECOND
    ws["B3"].alignment = LEFT
    lines = spec.get("precondition", "").count("\n") + 1
    ws.row_dimensions[3].height = min(409, 14 * lines + 6)

    r, case_id = 4, 0
    rows_for_dv = []
    for sec in spec["sections"]:
        style_row(ws, r, FILL_SECTION)
        ws.cell(r, 2, sec["title"]).alignment = Alignment(vertical="center")
        r += 1
        for c in sec["cases"]:
            case_id += 1
            vals = [case_id, c["type"], c.get("method", "Manual"), c["priority"],
                    c["desc"], numbered(c["steps"]), numbered(c["expected"]),
                    c.get("actual", ""), c["platform"], c.get("status", "Pending"),
                    c.get("bug_id", ""), c.get("attachment", ""), c.get("notes", "")]
            for col, v in enumerate(vals, 1):
                cell = ws.cell(r, col, v if v != "" else None)
                cell.font, cell.border = ARIAL, BORDER
                cell.alignment = CENTER if col in CENTER_COLS else LEFT
            rows_for_dv.append(r)
            r += 1

    if rows_for_dv:
        # one block per run of consecutive case rows, so section-title rows stay editable
        blocks, start = [], rows_for_dv[0]
        for prev, cur in zip(rows_for_dv, rows_for_dv[1:] + [None]):
            if cur != prev + 1:
                blocks.append((start, prev))
                start = cur
        for col, allowed in (("B", "Positive,Negative"), ("C", "Manual,Automated,Load"),
                             ("D", "P0,P1,P2,P3"), ("J", "Pending,Pass,Failed,Blocker")):
            dv = DataValidation(type="list", formula1=f'"{allowed}"', allow_blank=True)
            for a, b in blocks:
                dv.add(f"{col}{a}:{col}{b}")
            ws.add_data_validation(dv)
    ws.freeze_panes = "A3"
    return case_id


def write_bugs(wb, spec):
    bl = wb["Bug List"]
    for i, b in enumerate(spec.get("bugs", []), 2):
        vals = [b.get("environment", "Staging"), b.get("project", "Nama Sistem"), b.get("sprint", ""),
                b.get("bug_id", ""), b.get("priority", ""), b.get("severity", ""),
                b.get("reporter", ""), b.get("assign_to", ""), b.get("issue", ""),
                numbered(b.get("steps", [])), b.get("actual", ""), b.get("expected", ""),
                b.get("report_date"), b.get("update_date"), b.get("status", "Open"),
                b.get("duration", ""), b.get("log", "")]
        for col, v in enumerate(vals, 1):
            cell = bl.cell(i, col, v if v not in ("", None) else None)
            cell.font, cell.border, cell.alignment = ARIAL, BORDER, LEFT


def write_analysis(wb, items):
    ws = wb.create_sheet("Analisa")
    for i, (h, w) in enumerate(zip(ANALYSIS_HEADERS, ANALYSIS_WIDTHS), 1):
        c = ws.cell(1, i, h)
        c.font, c.fill, c.border, c.alignment = ARIAL_B, FILL_ANALYSIS_HDR, BORDER, CENTER
        ws.column_dimensions[c.column_letter].width = w
    for n, it in enumerate(items, 1):
        vals = [n, it.get("category", ""), it.get("ref", ""), it.get("source", ""),
                it.get("finding", ""), it.get("impact", ""), it.get("confidence", ""),
                it.get("question", ""), it.get("cases", "")]
        for col, v in enumerate(vals, 1):
            cell = ws.cell(n + 1, col, v)
            cell.font, cell.border = ARIAL, BORDER
            cell.alignment = CENTER if col in (1, 7) else TOP_LEFT
    ws.freeze_panes = "A2"


class SpecError(ValueError):
    pass


def _read_json(path, label):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise SpecError(f"{label} tidak ditemukan: {path}")
    except (ValueError, OSError) as e:
        raise SpecError(f"{label} bukan JSON valid: {e}")
    if not isinstance(data, dict):
        raise SpecError(f"{label} bukan objek JSON")
    return data


def load_spec(path):
    """Baca spec.json dan gabungkan file bagian ("parts") ke sections/analysis, sesuai urutan."""
    spec = _read_json(path, "spec.json")
    parts = spec.pop("parts", None) or []
    if not isinstance(parts, list):
        raise SpecError("'parts' harus berupa daftar nama file")
    base = os.path.realpath(os.path.dirname(os.path.abspath(path)))
    spec.setdefault("sections", [])
    for name in parts:
        if not isinstance(name, str) or not name:
            raise SpecError(f"nama file bagian tidak valid: {name!r}")
        full = os.path.realpath(os.path.join(base, name))
        if (os.path.isabs(name) or ".." in re.split(r"[\\/]", name)
                or os.path.commonpath([base, full]) != base):
            raise SpecError(f"path bagian '{name}' ditolak: harus relatif dan di dalam folder spec")
        part = _read_json(full, f"file bagian '{name}'")
        for key in ("sections", "analysis"):
            val = part.get(key) or []
            if not isinstance(val, list):
                raise SpecError(f"file bagian '{name}': '{key}' harus berupa daftar")
            if key == "analysis":
                spec[key] = list(spec.get(key) or []) + val
            else:
                spec[key] = list(spec[key]) + val
    return spec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("-o", "--output")
    ap.add_argument("--template", default=DEFAULT_TEMPLATE)
    ap.add_argument("--check", action="store_true", help="validate only")
    ap.add_argument("--no-analysis", action="store_true", help="skip the Analisa sheet")
    a = ap.parse_args()

    try:
        spec = load_spec(a.spec)
    except SpecError as e:
        print("ERROR:", e)
        sys.exit(1)
    for sec in spec.get("sections", []):
        for case in sec.get("cases", []):
            case["platform"] = norm_platform(case.get("platform", ""))
    errors, warns, n = validate(spec)
    for w in warns:
        print("WARN :", w)
    for e in errors:
        print("ERROR:", e)
    if errors:
        sys.exit(1)
    print(summary(spec))
    if a.check:
        return
    if not a.output:
        sys.exit("ERROR: -o/--output wajib bila bukan --check")

    wb = load_workbook(a.template)
    write_statistic(wb, spec["meta"])
    write_skenario(wb, spec)
    write_bugs(wb, spec)
    if spec.get("analysis") and not a.no_analysis:
        write_analysis(wb, spec["analysis"])
    wb.active = wb.sheetnames.index("Skenario")
    wb.save(a.output)
    print(f"OK -> {a.output}")


if __name__ == "__main__":
    main()
