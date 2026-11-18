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


def gitgen(c, paths):
    return c.post("/api/generate", data={**FORM, "git_path": paths}, files=[("fsd", ("a.docx", docx_bytes()))])


@pytest.fixture
def roots(tmp_path, monkeypatch):
    root = tmp_path / "git"
    (root / "app" / ".git").mkdir(parents=True)
    (root / "lib").mkdir()
    (tmp_path / "secret").mkdir()
    (root / "evil").symlink_to(tmp_path / "secret")
    monkeypatch.setenv("GIT_ROOTS", str(root))
    return root


def test_git_folder_selected(client, roots, tmp_path):
    login(client)
    r = gitgen(client, [str(roots / "app")])
    assert r.status_code == 200
    d = tmp_path / "jobs" / r.json()["job_id"]
    assert json.loads((d / "form.json").read_text())["git_repos"] == {str((roots / "app").resolve()): "app"}
    assert not any(d.glob("git_*"))  # tidak ada file repo yang disalin


@pytest.mark.parametrize("bad", ["/etc", "relatif/app", "ROOT/../secret", "ROOT/evil", "ROOT/tidak-ada", "ROOT", "ROOT/lib"])
def test_git_folder_rejected(client, roots, bad):
    login(client)
    assert gitgen(client, [bad.replace("ROOT", str(roots))]).status_code == 422


def test_git_folder_too_many(client, roots):
    login(client)
    assert gitgen(client, [str(roots / "app")] * 11).status_code == 422


def test_git_folder_roots_empty(client, monkeypatch, tmp_path):
    monkeypatch.delenv("GIT_ROOTS", raising=False)
    login(client)
    assert gitgen(client, [str(tmp_path)]).status_code == 422


def test_git_dirs_listing(client, roots):
    assert client.get("/api/git/dirs").status_code == 401
    login(client)
    top = client.get("/api/git/dirs").json()
    assert top["dirs"][0]["path"] == str(roots.resolve()) and top["parent"] == ""
    sub = client.get("/api/git/dirs", params={"path": str(roots)}).json()
    assert {(d["name"], d["repo"]) for d in sub["dirs"]} == {("app", True), ("lib", False)}  # symlink keluar root disembunyikan
    assert sub["parent"] == "" and sub["repo"] is False
    assert client.get("/api/git/dirs", params={"path": str(roots / "app")}).json()["repo"] is True
    assert client.get("/api/git/dirs", params={"path": "/etc"}).status_code == 422
