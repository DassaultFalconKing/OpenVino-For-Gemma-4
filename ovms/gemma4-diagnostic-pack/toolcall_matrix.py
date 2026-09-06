#!/usr/bin/env python3
"""Gemma4/OVMS tool-calling acceptance matrix.

Stdlib-only on purpose: copy the diagnostic pack to a Windows host and run it
with whatever Python is already available. Every case stores its exact request,
raw response (or SSE stream), and a machine-readable summary.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BAD_TOKEN_RE = re.compile(r"<unused\d+>|<pad>|(?:^|\s)multimodal(?:\s|$)", re.IGNORECASE)

ECHO_TOOL = {
    "type": "function",
    "function": {
        "name": "echo",
        "description": "Return the provided text to the caller.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
}

ECHO_SECOND_TOOL = {
    "type": "function",
    "function": {
        "name": "echo_second",
        "description": "Return a second independent text value to the caller.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
}

QUESTION_TOOL = {
    "type": "function",
    "function": {
        "name": "question",
        "description": "Ask the user one or more interactive questions.",
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "header": {"type": "string"},
                            "options": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                    "required": ["label", "description"],
                                    "additionalProperties": False,
                                },
                            },
                            "multiple": {"type": "boolean"},
                            "custom": {"type": "boolean"},
                        },
                        "required": ["question", "header", "options"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["questions"],
            "additionalProperties": False,
        },
    },
}


def endpoint_urls(base_url: str) -> tuple[str, str]:
    base = base_url.rstrip("/")
    parsed = urllib.parse.urlparse(base)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"invalid --base-url: {base_url!r}")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        chat = base
    elif path.endswith("/v1") or path.endswith("/v3"):
        chat = base + "/chat/completions"
    elif not path:
        chat = origin + "/v3/chat/completions"
    else:
        raise ValueError(
            "--base-url must be an origin, an OpenAI base ending in /v1 or /v3, "
            "or a full .../chat/completions URL"
        )
    return chat, origin + "/v1/models"


def http_json(url: str, payload: dict[str, Any] | None, timeout: float) -> tuple[int, str]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer unused"},
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def http_sse(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer unused"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            chunks: list[str] = []
            while True:
                line = response.readline()
                if not line:
                    break
                chunks.append(line.decode("utf-8", errors="replace"))
            return response.status, "".join(chunks)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def base_payload(model: str, prompt: str, tools: list[dict[str, Any]], choice: Any, max_tokens: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = choice
    return payload


def response_message(obj: dict[str, Any]) -> dict[str, Any]:
    try:
        message = obj["choices"][0]["message"]
        return message if isinstance(message, dict) else {}
    except (KeyError, IndexError, TypeError):
        return {}


def tool_calls(obj: dict[str, Any]) -> list[dict[str, Any]]:
    value = response_message(obj).get("tool_calls")
    return value if isinstance(value, list) else []


def finish_reason(obj: dict[str, Any]) -> str | None:
    try:
        value = obj["choices"][0].get("finish_reason")
        return str(value) if value is not None else None
    except (KeyError, IndexError, TypeError, AttributeError):
        return None


def tool_names(calls: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for call in calls:
        try:
            names.append(str(call["function"]["name"]))
        except (KeyError, TypeError):
            names.append("")
    return names


def validate_arguments(calls: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for idx, call in enumerate(calls):
        try:
            args = call["function"]["arguments"]
            if isinstance(args, dict):
                continue
            if not isinstance(args, str):
                errors.append(f"tool_calls[{idx}].function.arguments is not a string/object")
                continue
            parsed = json.loads(args)
            if not isinstance(parsed, dict):
                errors.append(f"tool_calls[{idx}].function.arguments is not a JSON object")
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"tool_calls[{idx}] invalid arguments: {exc}")
    return errors


def bad_tokens(raw: str) -> list[str]:
    return sorted(set(m.group(0).strip() for m in BAD_TOKEN_RE.finditer(raw)))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_unary_case(
    case_dir: Path,
    chat_url: str,
    payload: dict[str, Any],
    timeout: float,
    *,
    expect_tool: str | None,
    expect_no_tools: bool = False,
    min_tool_calls: int = 1,
) -> dict[str, Any]:
    write_json(case_dir / "request.json", payload)
    status, raw = http_json(chat_url, payload, timeout)
    (case_dir / "response.raw.txt").write_text(raw, encoding="utf-8")

    errors: list[str] = []
    obj: dict[str, Any] = {}
    if status != 200:
        errors.append(f"HTTP {status}")
    else:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                obj = parsed
            else:
                errors.append("response is not a JSON object")
        except json.JSONDecodeError as exc:
            errors.append(f"invalid response JSON: {exc}")

    calls = tool_calls(obj)
    names = tool_names(calls)
    errors.extend(validate_arguments(calls))
    garbage = bad_tokens(raw)
    if garbage:
        errors.append("reserved-token garbage: " + ", ".join(garbage))
    if expect_no_tools and calls:
        errors.append(f"expected no tool calls, got {names}")
    if expect_tool is not None:
        if len(calls) < min_tool_calls:
            errors.append(f"expected at least {min_tool_calls} tool call(s), got {len(calls)}")
        if expect_tool not in names:
            errors.append(f"expected tool {expect_tool!r}, got {names}")

    summary = {
        "pass": not errors,
        "http_status": status,
        "finish_reason": finish_reason(obj),
        "tool_names": names,
        "tool_count": len(calls),
        "bad_tokens": garbage,
        "errors": errors,
    }
    write_json(case_dir / "summary.json", summary)
    return summary


def run_stream_case(case_dir: Path, chat_url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    payload = dict(payload)
    payload["stream"] = True
    write_json(case_dir / "request.json", payload)
    status, raw = http_sse(chat_url, payload, timeout)
    (case_dir / "response.sse.txt").write_text(raw, encoding="utf-8")

    errors: list[str] = []
    if status != 200:
        errors.append(f"HTTP {status}")
    if "data: [DONE]" not in raw:
        errors.append("SSE stream has no [DONE]")
    garbage = bad_tokens(raw)
    if garbage:
        errors.append("reserved-token garbage: " + ", ".join(garbage))
    if '"tool_calls"' not in raw:
        errors.append("SSE stream contains no tool_calls delta")

    summary = {
        "pass": not errors,
        "http_status": status,
        "bad_tokens": garbage,
        "errors": errors,
    }
    write_json(case_dir / "summary.json", summary)
    return summary


def run_roundtrip(case_dir: Path, chat_url: str, model: str, timeout: float, max_tokens: int) -> dict[str, Any]:
    first_payload = base_payload(
        model,
        "Ask me one simple test question using the question tool.",
        [QUESTION_TOOL],
        "required",
        max_tokens,
    )
    first_dir = case_dir / "turn1"
    first_dir.mkdir(parents=True)
    first = run_unary_case(first_dir, chat_url, first_payload, timeout, expect_tool="question")
    if not first["pass"]:
        summary = {"pass": False, "errors": ["turn1 failed"], "turn1": first}
        write_json(case_dir / "summary.json", summary)
        return summary

    first_obj = json.loads((first_dir / "response.raw.txt").read_text(encoding="utf-8"))
    assistant = response_message(first_obj)
    calls = tool_calls(first_obj)
    tool_id = calls[0].get("id") if calls else None
    if not tool_id:
        summary = {"pass": False, "errors": ["turn1 tool call has no id"], "turn1": first}
        write_json(case_dir / "summary.json", summary)
        return summary

    second_payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Ask me one simple test question using the question tool."},
            assistant,
            {"role": "tool", "tool_call_id": tool_id, "content": json.dumps({"answer": "A"})},
        ],
        "tools": [QUESTION_TOOL],
        "tool_choice": "auto",
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "stream": False,
    }
    second_dir = case_dir / "turn2"
    second_dir.mkdir(parents=True)
    write_json(second_dir / "request.json", second_payload)
    status, raw = http_json(chat_url, second_payload, timeout)
    (second_dir / "response.raw.txt").write_text(raw, encoding="utf-8")
    errors: list[str] = []
    if status != 200:
        errors.append(f"turn2 HTTP {status}")
    garbage = bad_tokens(raw)
    if garbage:
        errors.append("turn2 reserved-token garbage: " + ", ".join(garbage))
    try:
        obj = json.loads(raw) if status == 200 else {}
    except json.JSONDecodeError as exc:
        obj = {}
        errors.append(f"turn2 invalid JSON: {exc}")
    message = response_message(obj)
    if not str(message.get("content") or "").strip() and not tool_calls(obj):
        errors.append("turn2 produced neither content nor a tool call")

    summary = {
        "pass": not errors,
        "turn1": first,
        "turn2_http_status": status,
        "turn2_finish_reason": finish_reason(obj),
        "turn2_tool_names": tool_names(tool_calls(obj)),
        "bad_tokens": garbage,
        "errors": errors,
    }
    write_json(second_dir / "summary.json", summary)
    write_json(case_dir / "summary.json", summary)
    return summary


def selected_cases(mode: str) -> list[str]:
    groups = {
        "none": ["none"],
        "auto": ["auto_optional", "auto_expected"],
        "required": ["required"],
        "named": ["named"],
        "question": ["question_auto", "question_required", "question_named"],
        "parallel": ["parallel_required"],
        "stream": ["question_stream"],
        "roundtrip": ["question_roundtrip"],
    }
    if mode == "all":
        return [name for names in groups.values() for name in names]
    return groups[mode]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Gemma4 tool-calling acceptance cases against OVMS")
    parser.add_argument("--base-url", default="http://127.0.0.1:9090/v3")
    parser.add_argument("--model", default="gemma4")
    parser.add_argument("--mode", choices=["all", "none", "auto", "required", "named", "question", "parallel", "stream", "roundtrip"], default="all")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--max-tokens", type=int, default=256)
    args = parser.parse_args()

    chat_url, models_url = endpoint_urls(args.base_url)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = args.output_dir or (Path(__file__).resolve().parent / "runtime" / "acceptance" / stamp)
    out.mkdir(parents=True, exist_ok=True)

    print(f"chat endpoint: {chat_url}")
    print(f"model: {args.model}")
    print(f"mode: {args.mode}")
    print(f"evidence: {out}")

    models_status, models_raw = http_json(models_url, None, min(args.timeout, 30.0))
    (out / "models.raw.txt").write_text(models_raw, encoding="utf-8")
    if models_status != 200:
        print(f"FAIL: GET {models_url} -> HTTP {models_status}", file=sys.stderr)
        return 2

    results: dict[str, Any] = {}
    for name in selected_cases(args.mode):
        case_dir = out / name
        case_dir.mkdir(parents=True, exist_ok=True)
        print(f"[{name}]", end=" ", flush=True)

        if name == "none":
            payload = base_payload(args.model, "Reply with exactly READY and do not use tools.", [ECHO_TOOL], "none", args.max_tokens)
            summary = run_unary_case(case_dir, chat_url, payload, args.timeout, expect_tool=None, expect_no_tools=True)
        elif name == "auto_optional":
            payload = base_payload(args.model, "Reply with exactly READY. Do not call a tool.", [ECHO_TOOL], "auto", args.max_tokens)
            summary = run_unary_case(case_dir, chat_url, payload, args.timeout, expect_tool=None, expect_no_tools=True)
        elif name == "auto_expected":
            payload = base_payload(args.model, "Use the echo tool with text test-auto. Do not explain instead.", [ECHO_TOOL], "auto", args.max_tokens)
            summary = run_unary_case(case_dir, chat_url, payload, args.timeout, expect_tool="echo")
        elif name == "required":
            payload = base_payload(args.model, "Call the available tool with text required-test.", [ECHO_TOOL], "required", args.max_tokens)
            summary = run_unary_case(case_dir, chat_url, payload, args.timeout, expect_tool="echo")
        elif name == "named":
            choice = {"type": "function", "function": {"name": "echo"}}
            payload = base_payload(args.model, "Call echo with text named-test.", [ECHO_TOOL], choice, args.max_tokens)
            summary = run_unary_case(case_dir, chat_url, payload, args.timeout, expect_tool="echo")
        elif name == "parallel_required":
            payload = base_payload(
                args.model,
                "Call BOTH tools in this same assistant turn: echo with text first, and echo_second with text second. Do not explain instead.",
                [ECHO_TOOL, ECHO_SECOND_TOOL],
                "required",
                args.max_tokens,
            )
            summary = run_unary_case(case_dir, chat_url, payload, args.timeout, expect_tool="echo", min_tool_calls=2)
            if "echo_second" not in summary.get("tool_names", []):
                summary["errors"].append(f"expected second tool 'echo_second', got {summary.get('tool_names', [])}")
                summary["pass"] = False
                write_json(case_dir / "summary.json", summary)
        elif name.startswith("question_") and name != "question_roundtrip":
            choice: Any = "auto"
            if name == "question_required" or name == "question_stream":
                choice = "required"
            elif name == "question_named":
                choice = {"type": "function", "function": {"name": "question"}}
            payload = base_payload(args.model, "Ask me one simple test question using the question tool. Do not explain instead.", [QUESTION_TOOL], choice, args.max_tokens)
            if name == "question_stream":
                summary = run_stream_case(case_dir, chat_url, payload, args.timeout)
            else:
                summary = run_unary_case(case_dir, chat_url, payload, args.timeout, expect_tool="question")
        elif name == "question_roundtrip":
            summary = run_roundtrip(case_dir, chat_url, args.model, args.timeout, args.max_tokens)
        else:
            raise AssertionError(name)

        results[name] = summary
        print("PASS" if summary.get("pass") else "FAIL")
        for error in summary.get("errors", []):
            print(f"  - {error}")

    overall = {
        "pass": all(bool(result.get("pass")) for result in results.values()),
        "base_url": args.base_url,
        "chat_url": chat_url,
        "model": args.model,
        "mode": args.mode,
        "results": results,
    }
    write_json(out / "matrix-summary.json", overall)
    print(f"OVERALL: {'PASS' if overall['pass'] else 'FAIL'}")
    return 0 if overall["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
