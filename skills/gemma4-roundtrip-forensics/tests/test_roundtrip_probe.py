import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "roundtrip_probe.py"

spec = importlib.util.spec_from_file_location("roundtrip_probe", MODULE_PATH)
probe = importlib.util.module_from_spec(spec)
sys.modules["roundtrip_probe"] = probe
spec.loader.exec_module(probe)


class RoundtripProbeUnitTests(unittest.TestCase):
    def test_special_token_scan_includes_eos_and_existing_reserved_tokens(self):
        text = 'before <eos> <unused42> <pad> multimodal after'
        self.assertEqual(
            probe.find_special_tokens(text),
            ["<eos>", "<pad>", "<unused42>", "multimodal"],
        )

    def test_empty_turn2_with_single_completion_token_is_classified_as_immediate_eos(self):
        response = {
            "choices": [{"message": {"role": "assistant", "content": "", "tool_calls": []}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 111, "completion_tokens": 1, "total_tokens": 112},
        }
        classes = probe.classify_response(response, raw=json.dumps(response), phase="turn2")
        self.assertIn("EMPTY_TURN2", classes)
        self.assertIn("IMMEDIATE_EOS", classes)
        self.assertNotIn("SPECIAL_TOKEN_LEAK", classes)

    def test_eos_leak_is_protocol_defect_even_when_tool_call_is_valid(self):
        response = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "<eos>",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "question", "arguments": '{"questions":[]}'},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"completion_tokens": 10},
        }
        classes = probe.classify_response(response, raw=json.dumps(response), phase="turn1")
        self.assertIn("SPECIAL_TOKEN_LEAK", classes)
        self.assertNotIn("EMPTY_TURN2", classes)

    def test_turn2_payload_preserves_exact_assistant_and_tool_call_id(self):
        assistant = {
            "role": "assistant",
            "content": "<eos>",
            "tool_calls": [{
                "id": "call_xyz",
                "type": "function",
                "function": {"name": "question", "arguments": '{"questions":[{"question":"Q"}]}'},
            }],
        }
        payload = probe.build_turn2_payload(
            model="gemma4",
            user_prompt="Ask me a question",
            assistant=assistant,
            tool_result={"answer": "A"},
            tools=[probe.QUESTION_TOOL],
            max_tokens=256,
        )
        self.assertEqual(payload["messages"][1], assistant)
        self.assertEqual(payload["messages"][2]["role"], "tool")
        self.assertEqual(payload["messages"][2]["tool_call_id"], "call_xyz")
        self.assertEqual(json.loads(payload["messages"][2]["content"]), {"answer": "A"})
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertFalse(payload["stream"])

    def test_throughput_uses_usage_only_and_never_guesses_tokens(self):
        usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
        m = probe.throughput_metrics(usage, total_s=4.0, ttft_s=2.0)
        self.assertEqual(m["prompt_tokens"], 100)
        self.assertEqual(m["completion_tokens"], 20)
        self.assertEqual(m["total_tokens"], 120)
        self.assertAlmostEqual(m["tokens_per_second_wall"], 5.0)
        self.assertAlmostEqual(m["tokens_per_second_after_ttft"], 10.0)

        missing = probe.throughput_metrics({}, total_s=4.0, ttft_s=2.0)
        self.assertIsNone(missing["completion_tokens"])
        self.assertIsNone(missing["tokens_per_second_wall"])
        self.assertIsNone(missing["tokens_per_second_after_ttft"])

    def test_artifact_metadata_hashes_exact_binary_bytes(self):
        import hashlib
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "ovms.exe"
            artifact.write_bytes(b"abc")
            meta = probe.artifact_metadata(artifact)
            self.assertEqual(meta["path"], str(artifact.resolve()))
            self.assertEqual(meta["size_bytes"], 3)
            self.assertEqual(meta["sha256"], hashlib.sha256(b"abc").hexdigest())
            self.assertIsNotNone(meta["mtime_utc"])

    def test_sse_parser_reconstructs_content_tool_calls_usage_and_done(self):
        raw = "\n".join([
            'data: {"choices":[{"delta":{"role":"assistant","tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"question","arguments":"{\\\"questions\\\":"}}]}}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"[]}"}}]},"finish_reason":"tool_calls"}]}',
            'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":4,"total_tokens":14}}',
            'data: [DONE]',
            '',
        ])
        parsed = probe.parse_sse_text(raw)
        self.assertTrue(parsed["done"])
        self.assertEqual(parsed["finish_reason"], "tool_calls")
        self.assertEqual(parsed["usage"]["total_tokens"], 14)
        self.assertEqual(parsed["tool_calls"][0]["id"], "call_1")
        self.assertEqual(parsed["tool_calls"][0]["function"]["name"], "question")
        self.assertEqual(parsed["tool_calls"][0]["function"]["arguments"], '{"questions":[]}')


if __name__ == "__main__":
    unittest.main()
