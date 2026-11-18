import io
import json
import time

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.server import create_app


def fake_run(store, job_id, form, claude_cmd=["claude"]):
    d = store.dir(job_id)
    (d / "spec.json").write_text(json.dumps({"sections": [{"cases": [{"type": "Positive"}]}]}))
    (d / "Scenario.xlsx").write_bytes(b"PK-fake")
    store.set_status(job_id, state="done", stage="selesai")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    return TestClient(create_app(run_job=fake_run))


def login(c):
    assert c.post("/api/login", data={"password": "pw"}).status_code == 200


def docx_bytes(text="Isi FSD"):
    b = io.BytesIO()
    d = Document()
    d.add_paragraph(text)
    d.save(b)
    return b.getvalue()


FORM = {"dev": "1", "test": "2", "title": "T"}


def gen(c, data=None, name="a.docx", content=None):
    content = docx_bytes() if content is None else content
    return c.post("/api/generate", data=FORM if data is None else data,
                  files={"fsd": (name, content)})


def test_empty_password_refuses_start(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "")
    with pytest.raises(RuntimeError):
        create_app(run_job=fake_run)


def test_generate_requires_login(client):
    assert gen(client).status_code == 401
    assert client.get("/api/jobs/abcdef012345").status_code == 401


def test_login_cookie_flags_and_wrong_password(client):
    r = client.post("/api/login", data={"password": "pw"})
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=lax" in sc
    c2 = TestClient(client.app)
    assert c2.post("/api/login", data={"password": "x"}).status_code == 401


def test_rate_limit(client):
    codes = [client.post("/api/login", data={"password": "x"}).status_code for _ in range(3)]
    assert codes == [401, 401, 429]
    assert client.post("/api/login", data={"password": "pw"}).status_code == 429


def test_too_large(client):
    login(client)
    assert gen(client, content=b"0" * (20 * 1024 * 1024 + 1)).status_code == 413


def test_bad_extension_and_fields(client):
    login(client)
    assert gen(client, name="a.txt").status_code == 422
    assert gen(client, data={**FORM, "title": ""}).status_code == 422
    assert gen(client, data={**FORM, "dev": "abc"}).status_code == 422
    assert gen(client, content=b"bukan docx").status_code == 422


def test_unknown_job_404(client):
    login(client)
    assert client.get("/api/jobs/..%2Fx").status_code == 404
    assert client.get("/api/jobs/abcdef012345").status_code == 404
    assert client.get("/api/jobs/abcdef012345/download").status_code == 404


def test_full_flow_and_safe_name(client, tmp_path):
    login(client)
    r = gen(client, name="../../x.docx")
    assert r.status_code == 200
    jid = r.json()["job_id"]
    for _ in range(50):
        j = client.get(f"/api/jobs/{jid}").json()
        if j["state"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert j["state"] == "done" and "skenario" in j["preview"]
    d = tmp_path / "jobs" / jid
    assert (d / "1_x.docx").exists() and (d / "fsd_1.md").read_text().strip() == "Isi FSD"
    assert not (tmp_path / "x.docx").exists()
    assert client.get(f"/api/jobs/{jid}/download").content == b"PK-fake"


def test_index(client):
    assert client.get("/").status_code == 200


def test_integration_real_runner(tmp_path, monkeypatch):
    import sys
    from functools import partial
    from pathlib import Path
    from app.runner import run_job
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    fake = [sys.executable, str(Path(__file__).parent / "fake_claude.py")]
    c = TestClient(create_app(run_job=partial(run_job, claude_cmd=fake)))
    login(c)
    jid = gen(c).json()["job_id"]
    for _ in range(300):
        j = c.get(f"/api/jobs/{jid}").json()
        if j["state"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert j["state"] == "done", j
    assert j["preview"]["skenario"]
    r = c.get(f"/api/jobs/{jid}/download")
    assert r.content[:2] == b"PK"


def test_roles_too_long_422(client):
    login(client)
    r = client.post("/api/generate", data={"dev": "1", "test": "2", "title": "t", "roles": "x" * 501},
                    files={"fsd": ("a.docx", b"x")})
    assert r.status_code == 422


def test_multi_sources(client, tmp_path):
    login(client)
    r = client.post("/api/generate", data={**FORM, "swagger_url": ["http://a/x", " ", "http://b/y"], "figma_url": "https://f/1"},
                    files=[("fsd", ("a.docx", docx_bytes("A"))), ("fsd", ("b.docx", docx_bytes("B")))])
    assert r.status_code == 200
    d = tmp_path / "jobs" / r.json()["job_id"]
    assert (d / "fsd_1.md").read_text().strip() == "A" and (d / "fsd_2.md").read_text().strip() == "B"
    form = json.loads((d / "form.json").read_text())
    assert form["swagger_urls"] == ["http://a/x", "http://b/y"] and form["figma_urls"] == ["https://f/1"]


def test_too_many_items(client):
    login(client)
    r = client.post("/api/generate", data={**FORM, "swagger_url": ["http://a"] * 11}, files={"fsd": ("a.docx", docx_bytes())})
    assert r.status_code == 422


def gitgen(c, rels, files=None, data=None):
    files = files or [("git_file", (f"f{i}", b"x = 1")) for i, _ in enumerate(rels)]
    return c.post("/api/generate", data={**FORM, "git_rel": rels, **(data or {})},
                  files=[("fsd", ("a.docx", docx_bytes())), *files])


def test_git_upload(client, tmp_path):
    login(client)
    r = gitgen(client, ["1/app/src/a.py", "1/app/README.md", "2/lib/b.py"],
               [("git_file", ("a", b"A")), ("git_file", ("r", b"R")), ("git_file", ("b", b"B"))])
    assert r.status_code == 200
    d = tmp_path / "jobs" / r.json()["job_id"]
    assert (d / "git_1/src/a.py").read_bytes() == b"A" and (d / "git_2/b.py").read_bytes() == b"B"
    assert json.loads((d / "form.json").read_text())["git_repos"] == {"git_1": "app", "git_2": "lib"}


@pytest.mark.parametrize("rel", ["1/app/../../x", "/etc/passwd", "1/app", "0/app/a", "11/app/a", "x/app/a", "1/app//a", "1/app/a\\b"])
def test_git_bad_path(client, rel):
    login(client)
    assert gitgen(client, [rel], [("git_file", ("a", b"A"))]).status_code == 422


def test_git_limits(client, monkeypatch):
    login(client)
    assert gitgen(client, ["1/a/b", "1/a/c"], [("git_file", ("a", b"A"))]).status_code == 422  # jumlah tidak cocok
    monkeypatch.setattr("app.server.GIT_MAX_FILE", 3)
    assert gitgen(client, ["1/a/b"], [("git_file", ("a", b"AAAA"))]).status_code == 413
    monkeypatch.setattr("app.server.GIT_MAX_FILES", 1)
    assert gitgen(client, ["1/a/b", "1/a/c"]).status_code == 422
