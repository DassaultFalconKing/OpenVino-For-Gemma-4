#!/usr/bin/env python3
import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TOOL = {
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


@dataclass(frozen=True)
class ProbeCase:
    name: str
    prompt: str
    tool_choice: Any
    require_empty_content: bool = False


CASES = {
    "auto": ProbeCase(
        name="auto",
        prompt="Use the get_weather tool to get the weather for Berlin. Do not answer from memory.",
        tool_choice="auto",
    ),
    "required": ProbeCase(
        name="required",
        prompt="Проверь погоду в Berlin через доступный инструмент. Не обещай запустить инструмент, а вызови его.",
        tool_choice="required",
        require_empty_content=True,
    ),
    "named": ProbeCase(
        name="named",
        prompt=(
            "Calculate 9*9 and answer directly. Do not call weather unless the API forces you. "
            "If a weather tool is forced, use city Berlin."
        ),
        tool_choice={
            "type": "function",
            "function": {"name": "get_weather"},
        },
        require_empty_content=True,
    ),
}


def request_completion(base_url: str, model: str, timeout: float, case: ProbeCase) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": case.prompt}],
        "tools": [TOOL],
        "tool_choice": case.tool_choice,
        "temperature": 0,
        "max_tokens": 256,
        "stream": False,
    }

    request = Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def validate_case(case: ProbeCase, payload: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        choice = payload["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AssertionError("malformed chat completion response") from exc

    content = message.get("content") or ""
    if "<|tool_call>" in content or "<tool_call|>" in content:
        raise AssertionError("Gemma4 raw tool markup leaked into message.content")
    if case.require_empty_content and content.strip():
        raise AssertionError(f"hard tool choice emitted prose before/around the call: {content!r}")

    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        raise AssertionError("response contains no message.tool_calls")

    function = tool_calls[0].get("function") or {}
    if function.get("name") != "get_weather":
        raise AssertionError(f"unexpected tool name: {function.get('name')!r}")

    raw_arguments = function.get("arguments", "")
    try:
        arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
    except json.JSONDecodeError as exc:
        raise AssertionError(f"tool arguments are not valid JSON: {raw_arguments!r}") from exc

    if not isinstance(arguments, dict) or "city" not in arguments:
        raise AssertionError(f"tool arguments do not contain city: {arguments!r}")
    if str(arguments["city"]).casefold() != "berlin":
        raise AssertionError(f"unexpected city argument: {arguments['city']!r}")

    if choice.get("finish_reason") != "tool_calls":
        raise AssertionError(
            f"expected finish_reason='tool_calls', got {choice.get('finish_reason')!r}"
        )

    return tool_calls


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify Gemma4 OpenAI tool calling for the healthy auto path plus hard required/named choice."
        )
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default="gemma4-26-heretic")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--mode",
        choices=("auto", "required", "named", "all"),
        default="all",
        help="Probe one tool-choice mode or run the complete three-case smoke suite.",
    )
    args = parser.parse_args()

    selected = ("auto", "required", "named") if args.mode == "all" else (args.mode,)

    for name in selected:
        case = CASES[name]
        try:
            payload = request_completion(args.base_url, args.model, args.timeout, case)
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            print(f"FAIL [{case.name}]: OVMS returned HTTP {exc.code}: {details}", file=sys.stderr)
            return 2
        except (URLError, TimeoutError) as exc:
            print(f"FAIL [{case.name}]: could not reach OVMS: {exc}", file=sys.stderr)
            return 2

        try:
            tool_calls = validate_case(case, payload)
        except AssertionError as exc:
            print(f"FAIL [{case.name}]: {exc}", file=sys.stderr)
            print(json.dumps(payload, indent=2, ensure_ascii=False), file=sys.stderr)
            return 3

        print(f"PASS [{case.name}]: structured get_weather tool call")
        print(json.dumps(tool_calls, indent=2, ensure_ascii=False))

    print("PASS: Gemma4 auto + hard tool-choice smoke suite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
