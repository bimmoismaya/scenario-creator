import sys
from pathlib import Path

import pytest
from docx import Document

from app.jobs import JobForm, JobStore
from app.prompt import build_prompt
from app.runner import clean, run_job, stage_of

FAKE = [sys.executable, str(Path(__file__).parent / "fake_claude.py")]
FORM = JobForm(dev=53, test=54, title="Contoh Fitur")


def make(tmp_path, upload=True):
    s = JobStore(tmp_path)
    jid = s.create(FORM)
    if upload:
        doc = Document()
        doc.add_paragraph("FSD contoh")
        doc.save(s.dir(jid) / "fsd.docx")
    return s, jid


def test_ok(tmp_path, monkeypatch):
    s, jid = make(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "ok")
    run_job(s, jid, FORM, FAKE)
    st = s.status(jid)
    assert st["state"] == "done", st
    assert (s.dir(jid) / "Scenario Sprint 54 Testing (53).xlsx").exists()
    assert "FSD contoh" in (s.dir(jid) / "fsd_1.md").read_text()


def test_exit1_sanitized(tmp_path, monkeypatch):
    s, jid = make(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "exit1")
    run_job(s, jid, FORM, FAKE)
    st = s.status(jid)
    assert st["state"] == "failed" and "not logged in" in st["error"]
    assert "bob@example.com" not in st["error"]


def test_timeout(tmp_path, monkeypatch):
    s, jid = make(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "sleep")
    run_job(s, jid, FORM, FAKE, timeout=1)
    st = s.status(jid)
    assert st["state"] == "failed" and "Timeout" in st["error"]


def test_no_spec(tmp_path, monkeypatch):
    s, jid = make(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "nospec")
    run_job(s, jid, FORM, FAKE)
    st = s.status(jid)
    assert st["state"] == "failed" and "spec.json" in st["error"]


def test_no_fsd(tmp_path):
    s, jid = make(tmp_path, upload=False)
    run_job(s, jid, FORM, FAKE)
    assert s.status(jid)["state"] == "failed"


def test_missing_claude(tmp_path):
    s, jid = make(tmp_path)
    run_job(s, jid, FORM, ["/nonexistent/claude"])
    assert s.status(jid)["state"] == "failed"


def test_prompt():
    p = build_prompt(JobForm(dev=1, test=2, title="x"), ["fsd_1.md"])
    assert "Perlu verifikasi" in p and "fsd_1.md" in p and "DATA" in p
    p2 = build_prompt(JobForm(dev=1, test=2, title="x", figma_urls=["https://figma.com/design/a", "https://figma.com/design/b"],
                              git_repos={"git_1": "app"}), ["fsd_1.md", "fsd_2.md"])
    assert "https://figma.com/design/a" in p2 and "https://figma.com/design/b" in p2
    assert "fsd_2.md" in p2 and "`git_1/`" in p2 and '"app"' in p2
    p3 = build_prompt(JobForm(dev=1, test=2, title="x", roles="Admin, Staff"), ["fsd_1.md"])
    assert '"Admin, Staff"' in p3 and "non-interaktif" in p3


def test_stage_and_clean():
    ev = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash",
          "input": {"command": "secret@x.com"}}]}}
    assert stage_of(ev) == "Validasi"
    assert stage_of({"type": "user"}) is None
    out = clean("a@b.com " + "x" * 500)
    assert "@" not in out and len(out) <= 300


def test_claude_args_model(monkeypatch, tmp_path):
    from app.runner import claude_args
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    a = claude_args("p", tmp_path)
    assert a[a.index("--model") + 1] == "opus"
    monkeypatch.setenv("CLAUDE_MODEL", "sonnet")
    a = claude_args("p", tmp_path)
    assert a[a.index("--model") + 1] == "sonnet"


def test_allowed_tools_read_only_for_git():
    from app.runner import allowed_tools
    t = allowed_tools(Path("/j"))
    assert "Grep" in t and "Glob" in t
    assert not any(x.startswith("Edit") or x == "Bash" for x in t)


def test_multi_fsd_converted(tmp_path, monkeypatch):
    s, jid = make(tmp_path)
    doc = Document()
    doc.add_paragraph("FSD kedua")
    doc.save(s.dir(jid) / "other.docx")
    monkeypatch.setenv("FAKE_MODE", "ok")
    run_job(s, jid, FORM, FAKE)
    assert s.status(jid)["state"] == "done"
    texts = {(s.dir(jid) / f"fsd_{i}.md").read_text().strip() for i in (1, 2)}
    assert texts == {"FSD contoh", "FSD kedua"}
