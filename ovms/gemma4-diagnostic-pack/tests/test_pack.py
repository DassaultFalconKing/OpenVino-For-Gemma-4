from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def test_expected_files_exist():
    expected = [
        ROOT / "profiles" / "vlm-stable" / "graph.pbtxt",
        ROOT / "profiles" / "vlm-cb-experimental" / "graph.pbtxt",
        ROOT / "launch.ps1",
        ROOT / "smoke_test.py",
        ROOT / "README.md",
        ROOT / "config.template.json",
    ]
    missing = [str(p.relative_to(ROOT)) for p in expected if not p.exists()]
    assert not missing, f"missing files: {missing}"


def test_stable_profile_is_stateful_and_dq0():
    text = (ROOT / "profiles" / "vlm-stable" / "graph.pbtxt").read_text(encoding="utf-8")
    assert "pipeline_type: VLM" in text
    assert "pipeline_type: VLM_CB" not in text
    assert "DYNAMIC_QUANTIZATION_GROUP_SIZE" in text
    assert '"0"' in text
    assert "enable_prefix_caching: false" in text


def test_cb_profile_is_single_sequence_and_dq0():
    text = (ROOT / "profiles" / "vlm-cb-experimental" / "graph.pbtxt").read_text(encoding="utf-8")
    assert "pipeline_type: VLM_CB" in text
    assert "max_num_seqs: 1" in text
    assert "DYNAMIC_QUANTIZATION_GROUP_SIZE" in text
    assert '"0"' in text
    assert "enable_prefix_caching: false" in text


def test_both_profiles_keep_required_llm_side_packets():
    for rel in [
        "profiles/vlm-stable/graph.pbtxt",
        "profiles/vlm-cb-experimental/graph.pbtxt",
    ]:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert 'input_side_packet: "LLM_NODE_RESOURCES:llm"' in text
        assert 'input_side_packet: "LLM_NODE_EXECUTION_CONTEXTS:llm_ctx"' in text


def test_runtime_config_template_is_valid_json():
    data = json.loads((ROOT / "config.template.json").read_text(encoding="utf-8"))
    assert data["model_config_list"] == []
    entry = data["mediapipe_config_list"][0]
    assert entry["name"] == "__MODEL_NAME__"
    assert entry["graph_path"] == "__GRAPH_PATH__"


def test_smoke_test_is_syntax_valid():
    path = ROOT / "smoke_test.py"
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_launcher_exposes_required_profile_switches():
    text = (ROOT / "launch.ps1").read_text(encoding="utf-8")
    assert '"vlm-stable", "vlm-cb-experimental"' in text
    assert 'ValidateSet("JINJA", "MINJA")' in text
    assert "--rest_workers 1" in text
    assert "[string]$SessionStoreDir" in text
    assert '$env:OVMS_SESSION_STORE_DIR = $ResolvedSessionStoreDir' in text
    assert "X-OVMS-Session-Store" not in text


def test_profiles_use_runtime_max_tokens_placeholder():
    for rel in [
        "profiles/vlm-stable/graph.pbtxt",
        "profiles/vlm-cb-experimental/graph.pbtxt",
    ]:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "max_tokens_limit: __MAX_TOKENS_LIMIT__" in text
        assert "max_tokens_limit: 8192" not in text


def test_launcher_defaults_to_64k_and_injects_override():
    text = (ROOT / "launch.ps1").read_text(encoding="utf-8")
    assert re.search(r"\[int\]\$MaxTokensLimit\s*=\s*65536", text)
    assert "ValidateRange(1, 2147483647)" in text
    assert '$graphText.Replace("__MAX_TOKENS_LIMIT__", $MaxTokensLimit.ToString())' in text
    assert "max tokens:    $MaxTokensLimit" in text
