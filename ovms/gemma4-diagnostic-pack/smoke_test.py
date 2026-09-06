#!/usr/bin/env python3
"""Minimal OpenAI-compatible smoke test for the Gemma-4 OVMS diagnostic pack.

The diagnostic pack serves a MediaPipe/GenAI graph. OVMS exposes graph-backed
chat completions at /v3/chat/completions. A base URL that already ends in /v1
or /v3 is respected; a host-only base defaults to /v3 for this pack.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def chat_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    parsed = urllib.parse.urlparse(base)
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        return base
    if path.endswith("/v1") or path.endswith("/v3"):
        return base + "/chat/completions"
    return base + "/v3/chat/completions"


def post_json(url: str, payload: dict, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def extract_content(response: dict) -> str:
    try:
        message = response["choices"][0]["message"]
        content = message.get("content")
        if content is None:
            content = message.get("reasoning_content", "")
        return str(content or "")
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the Gemma4 OVMS graph endpoint")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v3",
                        help="OVMS OpenAI base URL. Host-only values default to /v3 for this diagnostic pack.")
    parser.add_argument("--model", default="gemma4")
    parser.add_argument(
        "--prompt",
        default="Answer in one short sentence: why is the sky blue?",
    )
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    url = chat_url(args.base_url)
    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "stream": False,
    }

    print(f"POST {url}")
    print(f"model={args.model!r} temperature={args.temperature} max_tokens={args.max_tokens}")

    try:
        response = post_json(url, payload, args.timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {body}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"request failed: {exc}", file=sys.stderr)
        return 2

    content = extract_content(response)
    print("\n--- assistant content ---")
    print(content)
    print("--- end content ---\n")

    if not content.strip():
        print("FAIL: response contained no assistant content.", file=sys.stderr)
        print(json.dumps(response, indent=2, ensure_ascii=False), file=sys.stderr)
        return 3

    print("PASS: endpoint returned non-empty assistant content.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
