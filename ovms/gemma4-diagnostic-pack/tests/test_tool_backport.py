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


def test_apply_script_applies_exact_commits_without_creating_git_commits():
    text = (BACKPORT / "apply-backport.ps1").read_text(encoding="utf-8")
    assert BASE in text
    for commit in COMMITS:
        assert commit in text
    assert "git status --porcelain" in text
    assert "git rev-parse HEAD" in text
    assert "git cherry-pick --no-commit" in text
    assert "git reset --mixed HEAD" in text
    assert "git cherry-pick $commit" not in text
    assert "git config --global" not in text
    assert "git config user." not in text


def test_windows_build_script_builds_self_contained_package_and_can_deploy_elsewhere():
    text = (BACKPORT / "build-windows.ps1").read_text(encoding="utf-8")
    assert "apply-backport.ps1" in text
    assert "windows_build.bat" in text
    assert "--with_python" in text
    assert "--with_tests" in text
    assert "Gemma4OutputParserTest.*" in text
    assert "windows_create_package.bat" in text
    assert "$DeployTo" in text
    assert "$ForceDeploy" in text
    assert "dist\\windows\\ovms" in text
    assert "Copy-Item" in text


def test_windows_build_detects_visual_studio_buildtools_in_both_program_files_roots():
    text = (BACKPORT / "build-windows.ps1").read_text(encoding="utf-8")
    assert '[Environment]::GetEnvironmentVariable("ProgramFiles")' in text
    assert '[Environment]::GetEnvironmentVariable("ProgramFiles(x86)")' in text
    assert "Microsoft Visual Studio\\2022\\BuildTools" in text
    assert "$VisualStudioPath" in text
    assert "VC\\Tools\\MSVC" in text


def test_windows_build_temporarily_overrides_upstream_hardcoded_vs_path_and_restores_scripts():
    text = (BACKPORT / "build-windows.ps1").read_text(encoding="utf-8")
    assert "VS_2022_BT" in text
    assert "windows_install_build_dependencies.bat" in text
    assert "windows_build.bat" in text
    assert "Set-Content" in text
    assert "finally" in text
    assert "Restore" in text or "restore" in text


def test_tool_smoke_requires_openai_tool_calls_not_raw_markup():
    text = (BACKPORT / "smoke_tool_call.py").read_text(encoding="utf-8")
    compile(text, str(BACKPORT / "smoke_tool_call.py"), "exec")
    assert '"tool_choice": "auto"' in text
    assert "tool_calls" in text
    assert "<|tool_call>" in text
    assert "get_weather" in text


def test_backport_readme_documents_local_patch_and_separate_deploy_path():
    text = (BACKPORT / "README.md").read_text(encoding="utf-8")
    assert BASE in text
    assert "tool_choice=required" in text
    assert "not an acceptance criterion" in text
    assert "no Git commit" in text
    assert "-DeployTo" in text
    assert "source checkout" in text
    assert "prebuilt ovms.exe" in text
