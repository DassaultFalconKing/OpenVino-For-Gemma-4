from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
BACKPORT = ROOT / "backports" / "ovms-2026.4-gemma4-tools"
BASE = "530dc63f816507d18bc14629e8cffeb55e3985e6"
COMMITS = [
    "503ff866278e9236d08bc9b6ddd18ec879660f72",
    "95628b45a082bd3d9562a3ad2f3d0762d5883ca4",
]


def test_backport_manifest_pins_rc1_and_upstream_fixes():
    data = json.loads((BACKPORT / "manifest.json").read_text(encoding="utf-8"))
    assert data["repository"] == "openvinotoolkit/model_server"
    assert data["base_commit"] == BASE
    assert data["upstream_commits"] == COMMITS


def test_apply_script_refuses_wrong_base_and_cherry_picks_exact_commits():
    text = (BACKPORT / "apply-backport.ps1").read_text(encoding="utf-8")
    assert BASE in text
    for commit in COMMITS:
        assert commit in text
    assert "git status --porcelain" in text
    assert "git cherry-pick" in text
    assert "git rev-parse HEAD" in text


def test_windows_build_script_builds_ovms_after_backport():
    text = (BACKPORT / "build-windows.ps1").read_text(encoding="utf-8")
    assert "apply-backport.ps1" in text
    assert "windows_build.bat" in text
    assert "--with_python" in text
    assert "--with_tests" in text
    assert "Gemma4OutputParserTest.*" in text
    assert "ovms.exe" in text.lower()


def test_tool_smoke_requires_openai_tool_calls_not_raw_markup():
    text = (BACKPORT / "smoke_tool_call.py").read_text(encoding="utf-8")
    compile(text, str(BACKPORT / "smoke_tool_call.py"), "exec")
    assert '"tool_choice": "auto"' in text
    assert "tool_calls" in text
    assert "<|tool_call>" in text
    assert "get_weather" in text


def test_backport_readme_documents_required_limitation():
    text = (BACKPORT / "README.md").read_text(encoding="utf-8")
    assert BASE in text
    assert "tool_choice=required" in text
    assert "not an acceptance criterion" in text
