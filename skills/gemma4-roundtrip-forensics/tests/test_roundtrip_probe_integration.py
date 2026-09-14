import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "roundtrip_probe.py"
spec = importlib.util.spec_from_file_location("roundtrip_probe_integration", MODULE_PATH)
probe = importlib.util.module_from_spec(spec)
sys.modules["roundtrip_probe_integration"] = probe
spec.loader.exec_module(probe)


def tool_call_response(content="", completion_tokens=12):
    return {
        "id": "chatcmpl-turn1",
        "model": "gemma4",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content,
                "tool_calls": [{
                    "id": "call_question_1",
                    "type": "function",
                    "function": {
                        "name": "question",
                        "arguments": json.dumps({
                            "questions": [{
                                "question": "Pick A",
                                "header": "Test",
                                "options": [{"label": "A", "description": "A"}],
                            }]
                        }, separators=(",", ":")),
                    },
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 80, "completion_tokens": completion_tokens, "total_tokens": 80 + completion_tokens},
    }


class ProbeHandler(BaseHTTPRequestHandler):
    mode = "rc2"

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, obj, status=200):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.endswith("/models"):
            self._send_json({"data": [{"id": "gemma4"}]})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        messages = payload.get("messages", [])
        stream = bool(payload.get("stream"))
        if len(messages) == 1:
            self._send_json(tool_call_response("<eos>" if self.mode == "rc2" else ""))
            return

        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if self.mode == "rc2":
                events = [
                    {"choices": [{"delta": {}, "finish_reason": "stop"}]},
                    {"choices": [], "usage": {"prompt_tokens": 120, "completion_tokens": 1, "total_tokens": 121}},
                ]
            else:
                events = [
                    {"choices": [{"delta": {"content": "Thanks"}, "finish_reason": None}]},
                    {"choices": [{"delta": {"content": ", done."}, "finish_reason": "stop"}]},
                    {"choices": [], "usage": {"prompt_tokens": 120, "completion_tokens": 3, "total_tokens": 123}},
                ]
            for event in events:
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return

        if self.mode == "rc2":
            self._send_json({
                "id": "chatcmpl-turn2",
                "model": "gemma4",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "", "tool_calls": []}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 1, "total_tokens": 121},
            })
        else:
            self._send_json({
                "id": "chatcmpl-turn2",
                "model": "gemma4",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Thanks, done."}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 3, "total_tokens": 123},
            })


class Server:
    def __init__(self, mode):
        handler = type("ModeHandler", (ProbeHandler,), {"mode": mode})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/v3"

    def __exit__(self, exc_type, exc, tb):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)


class RoundtripProbeIntegrationTests(unittest.TestCase):
    def test_rc2_signature_is_localized_and_evidence_is_persisted(self):
        with Server("rc2") as base_url, tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            urls = probe.endpoint_urls(base_url)
            result = probe.run_iteration(
                out,
                urls=urls,
                model="gemma4",
                prompt=probe.DEFAULT_PROMPT,
                tool_result={"answer": "A"},
                timeout=5,
                max_tokens=256,
                variants=["exact", "clean-null", "clean-empty"],
            )
            self.assertFalse(result["pass"])
            self.assertIn("SPECIAL_TOKEN_LEAK", result["turn1"]["failure_classes"])
            exact_u = result["variants"]["exact"]["unary"]
            exact_s = result["variants"]["exact"]["stream"]
            self.assertIn("EMPTY_TURN2", exact_u["failure_classes"])
            self.assertIn("IMMEDIATE_EOS", exact_u["failure_classes"])
            self.assertIn("SSE_ZERO_DELTA", exact_s["failure_classes"])
            self.assertIn("IMMEDIATE_EOS", exact_s["failure_classes"])
            loc = result["localization"]["classification"]
            self.assertIn("GENERATION_OR_REENTRY_FAILURE", loc)
            self.assertIn("CLEAN_HISTORY_STILL_FAILS", loc)
            self.assertIn("TURN1_SPECIAL_TOKEN_LEAK", loc)
            self.assertTrue((out / "turn1" / "request.json").exists())
            self.assertTrue((out / "turn2-exact" / "stream" / "sse-timeline.json").exists())
            self.assertTrue((out / "turn2-clean-empty" / "unary" / "summary.json").exists())

    def test_healthy_roundtrip_passes_strict_exact_path(self):
        with Server("healthy") as base_url, tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = probe.run_iteration(
                out,
                urls=probe.endpoint_urls(base_url),
                model="gemma4",
                prompt=probe.DEFAULT_PROMPT,
                tool_result={"answer": "A"},
                timeout=5,
                max_tokens=256,
                variants=["exact"],
            )
            self.assertTrue(result["pass"])
            self.assertEqual(result["localization"]["classification"], [])
            self.assertEqual(result["variants"]["exact"]["stream"]["content"], "Thanks, done.")


if __name__ == "__main__":
    unittest.main()
