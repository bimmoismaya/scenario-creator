from pathlib import Path

ROOT = Path(__file__).parent.parent
HTML = (ROOT / "app" / "static" / "index.html").read_text()
TS = (ROOT / "src" / "ui" / "main.ts").read_text()


def test_static_ui_has_required_elements():
    for needle in ['id="fsd"', 'id="swagger_url"', 'id="figma_url"', 'id="git_path"', 'id="generate"', "Duplicate to drafts", 'id="roles"', 'id="figma_file"', 'id="figma_quota"', 'name="figma_mode"']:
        assert needle in HTML
    assert "Peringatan mutu" in TS and "Kuota Figma MCP habis" in TS


def test_ui_no_raw_innerhtml():
    assert "innerHTML" not in HTML + TS
