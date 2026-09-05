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
    assert manifest["upstream_commits"] == [
        "503ff866278e9236d08bc9b6ddd18ec879660f72",
        "95628b45a082bd3d9562a3ad2f3d0762d5883ca4",
    ]

    deltas = manifest["candidate_deltas"]
    assert deltas == [
        {
            "id": "parser-streaming-hardening",
            "repository": "https://github.com/DassaultFalconKing/model_server.git",
            "base": "6f5b48ece2078e32268b87402cc206e8b2772da8",
            "head": "721e13d12c0fd4820ccc4bd06a866963c6524da5",
        },
        {
            "id": "runtime-proven-parser-generation-candidate",
            "repository": "https://github.com/DassaultFalconKing/model_server.git",
            "base": "721e13d12c0fd4820ccc4bd06a866963c6524da5",
            "head": "fd0c86c77ce6812fd6c77d9c8ee16a7dd7cb973b",
        },
    ]


def test_manifest_records_rejected_heretic_experiments_instead_of_applying_them():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rejected = {item["head"]: item["reason"] for item in manifest["rejected_experiments"]}
    assert "3bbc47949eb35fe70cfd098d52dc62c306774396" in rejected
    assert "synthetic" in rejected["3bbc47949eb35fe70cfd098d52dc62c306774396"].lower()


def test_validate_manifest_rejects_broken_delta_chain(tmp_path: Path):
    module = load_module(APPLIER)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["candidate_deltas"][1]["base"] = "deadbeef"
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
