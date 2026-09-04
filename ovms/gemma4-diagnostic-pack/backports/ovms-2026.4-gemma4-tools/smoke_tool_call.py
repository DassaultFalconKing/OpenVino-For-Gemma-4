#!/usr/bin/env python3
import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Gemma4 native tool markup is exposed as OpenAI message.tool_calls."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default="gemma4-26-heretic")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    body = {
        "model": args.model,
        "messages": [
            {
                "role": "user",
                "content": "Use the get_weather tool to get the weather for Berlin. Do not answer from memory.",
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather for a city.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {
                                "type": "string",
                                "description": "City name",
                            }
                        },
                        "required": ["city"],
                    },
                },
            }
        ],
        "tool_choice": "auto",
        "temperature": 0,
        "max_tokens": 256,
        "stream": False,
    }

    request = Request(
        args.base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=args.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        print(f"FAIL: OVMS returned HTTP {exc.code}: {details}", file=sys.stderr)
        return 2
    except (URLError, TimeoutError) as exc:
        print(f"FAIL: could not reach OVMS: {exc}", file=sys.stderr)
        return 2

    try:
        choice = payload["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError):
        print("FAIL: malformed chat completion response", file=sys.stderr)
        print(json.dumps(payload, indent=2, ensure_ascii=False), file=sys.stderr)
        return 3

    content = message.get("content") or ""
    if "<|tool_call>" in content or "<tool_call|>" in content:
        print("FAIL: Gemma4 raw tool markup leaked into message.content", file=sys.stderr)
        print(content, file=sys.stderr)
        return 4

    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        print("FAIL: response contains no message.tool_calls", file=sys.stderr)
        print(json.dumps(payload, indent=2, ensure_ascii=False), file=sys.stderr)
        return 5

    function = tool_calls[0].get("function") or {}
    if function.get("name") != "get_weather":
        print(f"FAIL: unexpected tool name: {function.get('name')!r}", file=sys.stderr)
        return 6

    raw_arguments = function.get("arguments", "")
    try:
        arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
    except json.JSONDecodeError:
        print(f"FAIL: tool arguments are not valid JSON: {raw_arguments!r}", file=sys.stderr)
        return 7

    if not isinstance(arguments, dict) or "city" not in arguments:
        print(f"FAIL: tool arguments do not contain city: {arguments!r}", file=sys.stderr)
        return 8

    if choice.get("finish_reason") != "tool_calls":
        print(f"FAIL: expected finish_reason='tool_calls', got {choice.get('finish_reason')!r}", file=sys.stderr)
        return 9

    print("PASS: Gemma4 tool call was exposed as OpenAI message.tool_calls")
    print(json.dumps(tool_calls, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
