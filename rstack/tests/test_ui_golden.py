"""Synthetic screenshots only; no household state or images enter the repository."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest

Image = pytest.importorskip("PIL.Image")

TOOL = Path(__file__).resolve().parents[1] / "tools/ui-golden"


def run(*args):
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)],
                          text=True, capture_output=True, timeout=60)


def picture(path, color="white", size=(20, 10)):
    Image.new("RGB", size, color).save(path)
    return path


def test_equal_different_threshold_and_diff(tmp_path):
    golden = picture(tmp_path / "golden.png")
    actual = picture(tmp_path / "actual.png")
    result = run("compare", "--golden", golden, "--actual", actual)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["changed_pixel_fraction"] == 0
    with Image.open(actual) as source:
        source.putpixel((0, 0), (0, 0, 0))
        source.save(actual)
    result = run("compare", "--golden", golden, "--actual", actual, "--threshold", "0")
    assert result.returncode == 1, result.stderr
    data = json.loads(result.stdout)
    assert data["changed_pixel_fraction"] == 1 / 200
    assert Path(data["diff"]).is_file()
    assert run("compare", "--golden", golden, "--actual", actual, "--threshold", ".005").returncode == 0
    assert golden.read_bytes() != actual.read_bytes()  # Comparison never approves.


def test_missing_golden_requires_explicit_approve(tmp_path):
    actual = picture(tmp_path / "actual.png", "blue")
    golden = tmp_path / "new/home.png"
    result = run("compare", "--golden", golden, "--actual", actual)
    assert result.returncode != 0
    assert "approve a golden first: ui-golden approve" in result.stderr
    assert not golden.exists()
    assert run("approve", "--golden", golden, "--actual", actual).returncode == 0
    assert golden.read_bytes() == actual.read_bytes()


def test_masks_exclude_pixels_from_numerator_and_denominator(tmp_path):
    golden = picture(tmp_path / "golden.png")
    actual = picture(tmp_path / "actual.png")
    with Image.open(actual) as source:
        source.putpixel((0, 0), (0, 0, 0))
        source.putpixel((1, 0), (0, 0, 0))
        source.save(actual)
    mask = tmp_path / "mask.json"
    mask.write_text(json.dumps([dict(x=0, y=0, width=1, height=1)]))
    args = ["compare", "--golden", golden, "--actual", actual, "--mask", mask, "--threshold", "0"]
    result = run(*args)
    assert result.returncode == 1
    assert json.loads(result.stdout)["changed_pixel_fraction"] == 1 / 199
    mask.write_text(json.dumps([dict(x=0, y=0, width=2, height=1)]))
    assert run(*args).returncode == 0
    mask.write_text(json.dumps([dict(x=0, y=0, width=20, height=10)]))
    assert run(*args).returncode == 2


def test_dimensions_and_invalid_input_refuse(tmp_path):
    golden = picture(tmp_path / "golden.png")
    actual = picture(tmp_path / "actual.png", size=(21, 10))
    result = run("compare", "--golden", golden, "--actual", actual)
    assert result.returncode == 1
    assert json.loads(result.stdout)["same_size"] is False
    for threshold in ("nan", "-1", "2"):
        assert run("compare", "--golden", golden, "--actual", actual, "--threshold", threshold).returncode == 2
    assert run("compare", "--golden", golden, "--actual", actual, "--diff", golden).returncode == 2


@pytest.fixture
def page():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(404 if self.path == "/missing" else 200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b'''<!doctype html><style>body{margin:0;background:white}</style><body>
                <script>document.body.style.background=localStorage.getItem('color')||'white';</script>''')

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def test_playwright_renders_viewport_and_storage_state(page, tmp_path):
    pytest.importorskip("playwright")
    origin = page
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"cookies": [], "origins": [{"origin": origin, "localStorage": [{"name": "color", "value": "blue"}]}]}))
    actual = tmp_path / "actual.png"
    result = run("render", "--url", page, "--viewport", "40x20", "--storage-state", state, "--out", actual)
    assert result.returncode == 0, result.stderr
    with Image.open(actual) as source:
        assert source.size == (40, 20)
        assert source.convert("RGB").getpixel((0, 0)) == (0, 0, 255)
    result = run("render", "--url", page + "/missing", "--viewport", "40x20", "--out", tmp_path / "bad.png")
    assert result.returncode != 0
    assert not (tmp_path / "bad.png").exists()


def test_first_screen_refuses_redirected_home(page, tmp_path):
    pytest.importorskip("playwright")
    actual = tmp_path / 'first.png'
    ok = run('render', '--url', page + '/#game', '--viewport', '40x20',
             '--expect-hash', '#game', '--out', actual)
    assert ok.returncode == 0, ok.stderr
    refused = run('render', '--url', page, '--viewport', '40x20',
                  '--expect-hash', '#game', '--out', tmp_path / 'home.png')
    assert refused.returncode == 2
    assert 'route changed' in refused.stderr
    assert not (tmp_path / 'home.png').exists()
