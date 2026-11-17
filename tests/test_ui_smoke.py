from pathlib import Path

HTML = (Path(__file__).parent.parent / "app" / "static" / "index.html").read_text()


def test_static_ui_has_required_elements():
    for needle in ['id="fsd"', 'id="swagger_url"', 'id="figma_url"', 'id="generate"', "Duplicate to drafts", 'id="roles"', "Peringatan mutu"]:
        assert needle in HTML


def test_ui_no_raw_innerhtml():
    assert "innerHTML" not in HTML
