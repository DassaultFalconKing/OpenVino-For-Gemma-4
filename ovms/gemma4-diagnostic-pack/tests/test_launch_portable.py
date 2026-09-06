import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[3]
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")
pytestmark = pytest.mark.skipif(not POWERSHELL, reason="PowerShell is required")

CANONICAL_REVISION = "711c1368e39f1712f48ff0eb7bcdbbb760d52db0"


def run_script(script, *args, cwd, env=None):
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *map(str, args)],
        cwd=cwd, env=env, capture_output=True, text=True, errors="replace", timeout=30,
    )


@pytest.fixture
def package(tmp_path):
    root = tmp_path / "Gemma4 Server with spaces"
    pack = root / "ovms" / "gemma4-diagnostic-pack"
    shutil.copytree(REPO / "ovms" / "gemma4-diagnostic-pack", pack, ignore=shutil.ignore_patterns("runtime", "__pycache__"))
    if (REPO / "Start-Server.ps1").exists():
        shutil.copy2(REPO / "Start-Server.ps1", root)
    model = root / "models" / "gemma4"
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}")

    # Minimal canonical-marker fixture plus matching sidecar: launcher tests must
    # exercise the idempotent fast path without relying on external network.
    template_text = """{# Template: Google Gemma 4 Canonical Chat Template #}\n{%- macro format_argument(x) -%}{{ x }}{%- endmacro -%}\n<|tool_call><tool_call|><|tool_response><tool_response|>\n"""
    template = model / "chat_template.jinja"
    template.write_text(template_text, encoding="utf-8")
    digest = hashlib.sha256(template.read_bytes()).hexdigest().upper()
    (model / ".gemmamonster-chat-template.json").write_text(
        json.dumps({"revision": CANONICAL_REVISION, "sha256": digest}), encoding="utf-8"
    )
    return root


def test_downloaded_package_runs_from_an_unrelated_directory(package, tmp_path):
    result = run_script(package / "Start-Server.ps1", "-NoLaunch", cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Canonical Gemma-4 template already installed" in result.stdout
    config_path = package / "generated-config" / "gemma4" / "config.json"
    assert not config_path.read_bytes().startswith(b"\xef\xbb\xbf")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    entry = config["mediapipe_config_list"][0]
    assert entry["name"] == "gemma4"
    graph = Path(entry["graph_path"])
    text = graph.read_text(encoding="utf-8")
    assert not graph.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "# OVMS_GRAPH_QUEUE_MAX_SIZE: 0" in text
    assert (package / "models" / "gemma4").as_posix() in text
    assert "__MODEL_PATH__" not in text
    assert "http://127.0.0.1:9090/v3" in result.stdout


def test_launcher_sets_bundled_python_and_preserves_exit_code(package, tmp_path):
    server = package / "server"
    (server / "python" / "Lib").mkdir(parents=True)
    (server / "python" / "python.exe").touch()
    exe = server / "ovms.ps1"
    capture = server / "capture.json"
    exe.write_text(
        "@{ args = @($args); pythonHome = $env:PYTHONHOME; pythonPath = $env:PYTHONPATH; "
        "path = $env:PATH } | ConvertTo-Json | Set-Content -LiteralPath "
        "(Join-Path $PSScriptRoot 'capture.json'); exit 23", encoding="utf-8"
    )
    env = dict(os.environ, PYTHONHOME="wrong-python", PYTHONPATH="wrong-python")
    result = run_script(package / "Start-Server.ps1", "-OvmsExe", exe, cwd=tmp_path, env=env)
    assert result.returncode == 23, result.stdout + result.stderr
    recorded = json.loads(capture.read_text(encoding="utf-8-sig"))
    assert Path(recorded["pythonHome"]) == server / "python"
    assert Path(recorded["pythonPath"]) == server / "python"
    assert recorded["path"].startswith(str(server) + ";")
    assert list(map(str, recorded["args"][-4:])) == ["--rest_port", "9090", "--rest_workers", "1"]


def test_skip_canonical_template_allows_offline_custom_template(package, tmp_path):
    model = package / "models" / "gemma4"
    custom = model / "chat_template.jinja"
    custom.write_text("custom experimental template", encoding="utf-8")
    (model / ".gemmamonster-chat-template.json").unlink(missing_ok=True)

    result = run_script(package / "Start-Server.ps1", "-SkipCanonicalTemplate", "-NoLaunch", cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert custom.read_text(encoding="utf-8") == "custom experimental template"
    assert "SkipCanonicalTemplate requested" in (result.stdout + result.stderr)


def test_model_name_cannot_escape_generated_directory(package, tmp_path):
    result = run_script(package / "Start-Server.ps1", "-ModelName", "../outside", "-NoLaunch", cwd=tmp_path)
    assert result.returncode != 0
    assert not (package / "outside").exists()
