from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKPORT = ROOT / "backports" / "ovms-2026.4-gemma4-tools"
APPLIER = BACKPORT / "apply_backport.py"
MANIFEST = BACKPORT / "manifest.json"
MATRIX = BACKPORT / "toolcall_matrix.py"


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("portable_backport", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_portable_applier_exists_and_has_no_platform_build_policy():
    assert APPLIER.is_file()
    text = APPLIER.read_text(encoding="utf-8")
    lowered = text.lower()
    for forbidden in ("powershell", "windows_build.bat", "c:\\\\buildtools", "opencv 4.14"):
        assert forbidden not in lowered


def test_manifest_describes_exact_contiguous_candidate_deltas():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 3
    assert manifest["base_commit"] == "530dc63f816507d18bc14629e8cffeb55e3985e6"
    assert manifest["upstream_commits"] == []
    assert manifest["selected_candidate_head"] == "0a537f08987a3df4c0254c1614162c06ac20b968"

    deltas = manifest["candidate_deltas"]
    assert deltas == [
        {
            "id": "ovms-2026.4-rc1-gemma4-contiguous-candidate",
            "repository": "https://github.com/DassaultFalconKing/model_server.git",
            "base": "530dc63f816507d18bc14629e8cffeb55e3985e6",
            "head": "0a537f08987a3df4c0254c1614162c06ac20b968",
        },
    ]


def test_manifest_freezes_accepted_rc1_runtime_baseline():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    accepted = manifest["accepted_runtime"]
    assert accepted["status"] == "accepted_gemma4_tool_calling_rc1_baseline"
    assert accepted["candidate_head"] == manifest["selected_candidate_head"]
    assert accepted["source_base"] == manifest["base_commit"]
    assert accepted["verdicts"]["MULTILINE_BOUNDED"] == "PASS"
    assert accepted["verdicts"]["GPU_LONG_GENERATION_STABILITY"] == "FAIL"
    assert "RC1-ACCEPTANCE.md" in accepted["evidence"]


def test_manifest_records_rejected_heretic_experiments_instead_of_applying_them():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rejected = {item["head"]: item["reason"] for item in manifest["rejected_experiments"]}
    assert "3bbc47949eb35fe70cfd098d52dc62c306774396" in rejected
    assert "synthetic" in rejected["3bbc47949eb35fe70cfd098d52dc62c306774396"].lower()


def test_validate_manifest_rejects_broken_delta_chain(tmp_path: Path):
    module = load_module(APPLIER)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["candidate_deltas"].append(
        {
            "id": "broken-follow-on",
            "repository": manifest["candidate_deltas"][0]["repository"],
            "base": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "head": "cafebabecafebabecafebabecafebabecafebabe",
        }
    )
    bad = tmp_path / "manifest.json"
    bad.write_text(json.dumps(manifest), encoding="utf-8")

    try:
        module.load_manifest(bad)
    except ValueError as exc:
        assert "candidate delta chain" in str(exc).lower()
    else:
        raise AssertionError("broken candidate delta chain was accepted")


def test_toolcall_matrix_is_portable_and_has_adversarial_cases():
    assert MATRIX.is_file()
    text = MATRIX.read_text(encoding="utf-8")
    lowered = text.lower()
    for forbidden in ("powershell", "cmd.exe", "c:\\\\llm"):
        assert forbidden not in lowered
    for required in (
        "tool_choice_none",
        "tool_choice_required",
        "tool_choice_named_conflict",
        "nested_object",
        "array_strings",
        "multiline_write",
        "shell_quoting",
        "parallel_calls",
        "streaming_weather",
        "roundtrip_after_tool",
    ):
        assert required in text
    assert "[:1200]" in text
    assert "[:4600]" not in text
