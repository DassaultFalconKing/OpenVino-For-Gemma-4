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


def test_apply_script_integrates_local_gemma4_generation_overlay():
    apply = (BACKPORT / "apply-backport.ps1").read_text(encoding="utf-8")
    local = (BACKPORT / "apply-gemma4-generation-config.ps1").read_text(encoding="utf-8")

    assert "apply-gemma4-generation-config.ps1" in apply
    assert "Gemma4GenerationConfigBuilder" in local
    assert 'toolParserName == "gemma4"' in local
    assert "io_processing/gemma4/generation_config_builder.hpp" in local
    assert "io_processing/gemma4/generation_config_builder.cpp" in local
    assert "TagsWithSeparator" in local
    assert "guidedArgsDoc" in local
    assert "guidedArgsDoc.IsObject()" in local
    assert "ParseToolCallOutputWithGuidedJsonArguments" in local
    assert "git add --" in local


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
    assert "C:\\BuildTools" in text
    assert "Invoke-NativeProcess" in text
    assert "Assert-WindowsBuildSucceeded" in text
    assert "OPENCV_PYTHON_SKIP_DETECTION" in text
    assert "python3.exe" in text


def test_windows_build_refuses_parser_only_tree_when_guidance_overlay_is_expected():
    text = (BACKPORT / "build-windows.ps1").read_text(encoding="utf-8")
    assert "Assert-Gemma4GuidanceIntegrated" in text
    assert "generation_config_builder.cpp" in text
    assert 'toolParserName == "gemma4"' in text
    assert "guidedArgsDoc" in text


def test_windows_build_detects_visual_studio_buildtools_in_both_program_files_roots():
    text = (BACKPORT / "build-windows.ps1").read_text(encoding="utf-8")
    assert '[Environment]::GetEnvironmentVariable("ProgramFiles")' in text
    assert '[Environment]::GetEnvironmentVariable("ProgramFiles(x86)")' in text
    assert "Microsoft Visual Studio\\2022\\BuildTools" in text
    assert "$VisualStudioPath" in text
    assert "VC\\Tools\\MSVC" in text


def test_windows_build_uses_detected_msvc_version_instead_of_rc1_hardcode():
    text = (BACKPORT / "build-windows.ps1").read_text(encoding="utf-8")
    assert "MsvcVersion" in text
    assert "BAZEL_VC_FULL_VERSION" in text
    assert "14.44.35207" in text
    assert "Directory.Parent.Parent.Parent.Name" in text


def test_windows_build_temporarily_overrides_upstream_hardcoded_vs_path_and_restores_scripts():
    text = (BACKPORT / "build-windows.ps1").read_text(encoding="utf-8")
    assert "VS_2022_BT" in text
    assert "windows_install_build_dependencies.bat" in text
    assert "windows_build.bat" in text
    assert "WriteAllText" in text
    assert "ReadAllBytes" in text
    assert "WriteAllBytes" in text
    assert "finally" in text
    assert "Restore-OvmsWindowsBuildScripts" in text


def test_tool_smoke_covers_auto_required_and_named_hard_choice():
    text = (BACKPORT / "smoke_tool_call.py").read_text(encoding="utf-8")
    compile(text, str(BACKPORT / "smoke_tool_call.py"), "exec")
    assert '"auto": ProbeCase' in text
    assert '"required": ProbeCase' in text
    assert '"named": ProbeCase' in text
    assert 'default="all"' in text
    assert '"type": "function"' in text
    assert '"function": {"name": "get_weather"}' in text
    assert "require_empty_content=True" in text
    assert "tool_calls" in text
    assert "<|tool_call>" in text
    assert "get_weather" in text


def test_backport_readme_documents_local_patch_and_separate_deploy_path():
    text = (BACKPORT / "README.md").read_text(encoding="utf-8")
    assert BASE in text
    assert "tool_choice=required" in text
    assert "no Git commit" in text
    assert "-DeployTo" in text
    assert "source checkout" in text
    assert "prebuilt" in text
    assert "ovms.exe" in text
    assert "TagsWithSeparator" in text
    assert "named" in text.lower()


def test_launch_script_writes_utf8_without_bom():
    text = (ROOT / "launch.ps1").read_text(encoding="utf-8")
    assert "UTF8Encoding" in text
    assert "WriteAllText" in text
    assert "Set-Content -Path $RuntimeConfig" not in text


def test_install_docs_cover_manual_and_agent_paths():
    install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
    agents = (ROOT.parents[1] / "AGENTS.md").read_text(encoding="utf-8")
    assert BASE in install
    assert "-SkipApply" in install
    assert "smoke_tool_call.py" in install
    assert "git reset --hard" in install
    assert "C:\\llm\\ovms-gemma4-patched" in install
    assert "tool_choice=required" in install
    assert "named" in install.lower()
    assert "build-windows.ps1" in agents
    assert "-SkipApply" in agents
    assert "Gemma4OutputParserTest" in agents
    assert "tool_choice=required" in agents


def test_gemma4_generation_config_builder_is_documented_and_auto_applied():
    draft = BACKPORT / "drafts" / "gemma4-generation-config-builder"
    header = (draft / "overlay" / "src" / "llm" / "io_processing" / "gemma4" / "generation_config_builder.hpp").read_text(encoding="utf-8")
    source = (draft / "overlay" / "src" / "llm" / "io_processing" / "gemma4" / "generation_config_builder.cpp").read_text(encoding="utf-8")
    factory = (draft / "overlay" / "src" / "llm" / "io_processing" / "generation_config_builder.hpp.snippet").read_text(encoding="utf-8")
    prompt = (draft / "PROMPT.md").read_text(encoding="utf-8")
    apply = (BACKPORT / "apply-backport.ps1").read_text(encoding="utf-8")
    assert "class Gemma4GenerationConfigBuilder" in header
    assert '<|tool_call>call:' in source
    assert "<tool_call|>" in source
    assert "TagsWithSeparator" in source
    assert "JSONSchema" in source
    assert 'toolParserName == "gemma4"' in factory
    assert "XGrammar" in prompt or "xgrammar" in prompt
    assert "apply-gemma4-generation-config.ps1" in apply


def test_gemma4_generation_config_builder_separates_hard_and_auto_tool_choice():
    draft = BACKPORT / "drafts" / "gemma4-generation-config-builder"
    source = (draft / "overlay" / "src" / "llm" / "io_processing" / "gemma4" / "generation_config_builder.cpp").read_text(encoding="utf-8")

    # `required` and named tool_choice must constrain from token zero rather than
    # waiting for the model to emit the trigger on its own.
    assert "hardToolChoice" in source
    assert "isHardToolChoice" in source
    assert 'toolChoice == "required"' in source
    assert 'toolChoice != "auto"' in source
    assert 'toolChoice != "none"' in source
    assert "TagsWithSeparator" in source
    assert 'requiredTags->separator = ""' in source
    assert "requiredTags->at_least_one = true" in source

    # `none` must never regain tools through graph-level guided generation.
    assert 'if (request.toolChoice == "none")' in source

    # Auto mode keeps the existing successful unconstrained path unless the
    # graph explicitly enables guided generation.
    assert "TriggeredTags" in source
    assert "enableToolGuidedGeneration" in source
