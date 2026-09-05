#!/usr/bin/env python3
"""Adversarial OpenAI-compatible tool-call matrix for a running Gemma4 OVMS."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


MARKERS = ("<|tool_call>", "<tool_call|>", "<|tool_response>", "<turn|>")

WEATHER = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}
CALCULATE = {
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "Evaluate an arithmetic expression",
        "parameters": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    },
}
LIST_FILES = {
    "type": "function",
    "function": {
        "name": "list_files",
        "description": "List files in a directory",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
}
WRITE_FILE = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Write text to a file",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
}
RUN_COMMAND = {
    "type": "function",
    "function": {
        "name": "run_command",
        "description": "Run a shell command",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
}
NESTED = {
    "type": "function",
    "function": {
        "name": "create_event",
        "description": "Create a calendar event",
        "parameters": {
            "type": "object",
            "properties": {
                "event": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "when": {
                            "type": "object",
                            "properties": {
                                "date": {"type": "string"},
                                "hour": {"type": "integer"},
                            },
                            "required": ["date", "hour"],
                        },
                        "attendees": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "when", "attendees"],
                }
            },
            "required": ["event"],
        },
    },
}
ARRAYS = {
    "type": "function",
    "function": {
        "name": "process_paths",
        "description": "Process path and tag arrays",
        "parameters": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["paths", "tags"],
        },
    },
}


@dataclass
class Result:
    case: str
    status: str
    issues: list[str]
    content: str
    tool_names: list[str]
    arguments: list[Any]
    finish_reason: str | None


def request_json(base_url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def request_stream(base_url: str, payload: dict[str, Any], timeout: float) -> list[dict[str, Any]]:
    payload = dict(payload)
    payload["stream"] = True
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    events: list[dict[str, Any]] = []
    with urllib.request.urlopen(req, timeout=timeout) as response:
        for raw in response:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            if data:
                events.append(json.loads(data))
    return events


def inspect_message(case: str, response: dict[str, Any], expected_tool: str | None, hard: bool) -> Result:
    choice = response.get("choices", [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    calls = message.get("tool_calls") or []
    issues: list[str] = []
    names: list[str] = []
    arguments: list[Any] = []

    if any(marker in content for marker in MARKERS):
        issues.append("PARSER_MARKUP_LEAK")
    if hard and content.strip():
        issues.append("HARD_CHOICE_PROSE")
    if expected_tool and not calls:
        issues.append("TOOL_CHOICE_NOT_ENFORCED")
    if expected_tool and calls:
        first_name = ((calls[0].get("function") or {}).get("name"))
        if first_name != expected_tool:
            issues.append("WRONG_TOOL_NAME")

    for call in calls:
        fn = call.get("function") or {}
        name = fn.get("name") or ""
        names.append(name)
        if not name:
            issues.append("TOOL_NAME_MISSING")
        raw_args = fn.get("arguments", "")
        try:
            arguments.append(json.loads(raw_args))
        except (TypeError, json.JSONDecodeError):
            arguments.append(raw_args)
            issues.append("ARGUMENTS_INVALID_JSON")

    status = "PASS" if not issues else "FAIL"
    return Result(case, status, sorted(set(issues)), content, names, arguments, choice.get("finish_reason"))


def base_payload(model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]], tool_choice: Any, max_tokens: int = 512) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": tool_choice,
        "temperature": 0,
        "max_tokens": max_tokens,
    }


def run_case(base_url: str, model: str, timeout: float, name: str) -> Result:
    sample_a = "C:\\sample\\alpha.txt"
    sample_b = "C:\\sample\\beta.json"
    multiline = ("function demo(x) { return {items: [1, 2, 3], text: \\\"a,b:{c}\\\"}; }\n" * 80)[:4600]

    if name == "tool_choice_none":
        payload = base_payload(model, [{"role": "user", "content": "Calculate 2+2."}], [CALCULATE], "none")
        result = inspect_message(name, request_json(base_url, payload, timeout), None, False)
        if result.tool_names:
            result.issues.append("UNEXPECTED_TOOL_CALL")
            result.status = "FAIL"
        return result

    if name == "tool_choice_required":
        payload = base_payload(model, [{"role": "user", "content": "List the current directory through the available tool. Call it now."}], [LIST_FILES], "required")
        return inspect_message(name, request_json(base_url, payload, timeout), "list_files", True)

    if name == "tool_choice_named_conflict":
        choice = {"type": "function", "function": {"name": "get_weather"}}
        payload = base_payload(model, [{"role": "user", "content": "The relevant city is Berlin. Compute 9*9. If a tool is forced, obey the forced tool."}], [WEATHER, CALCULATE], choice)
        result = inspect_message(name, request_json(base_url, payload, timeout), "get_weather", True)
        if result.arguments and isinstance(result.arguments[0], dict):
            if result.arguments[0].get("city", "").lower() != "berlin":
                result.issues.append("MODEL_ARGUMENT_QUALITY")
                result.status = "WARN"
        return result

    if name == "nested_object":
        prompt = "Create event Review on 2026-09-06 at hour 14 with attendees Ada and Linus. Use the tool."
        payload = base_payload(model, [{"role": "user", "content": prompt}], [NESTED], "required")
        result = inspect_message(name, request_json(base_url, payload, timeout), "create_event", True)
        if result.arguments and isinstance(result.arguments[0], dict):
            event = result.arguments[0].get("event")
            if not isinstance(event, dict) or not isinstance(event.get("when"), dict) or not isinstance(event.get("attendees"), list):
                result.issues.append("ARGUMENT_TYPE_DRIFT")
                result.status = "FAIL"
        return result

    if name == "array_strings":
        prompt = f"Call process_paths with paths exactly [{sample_a}, {sample_b}] and tags [runtime, windows]."
        payload = base_payload(model, [{"role": "user", "content": prompt}], [ARRAYS], "required")
        result = inspect_message(name, request_json(base_url, payload, timeout), "process_paths", True)
        if result.arguments and isinstance(result.arguments[0], dict):
            if not isinstance(result.arguments[0].get("paths"), list) or not isinstance(result.arguments[0].get("tags"), list):
                result.issues.append("ARGUMENT_TYPE_DRIFT")
                result.status = "FAIL"
        return result

    if name == "multiline_write":
        prompt = "Write the following code verbatim to output.txt using write_file:\n" + multiline
        payload = base_payload(model, [{"role": "user", "content": prompt}], [WRITE_FILE], "required", max_tokens=2048)
        result = inspect_message(name, request_json(base_url, payload, timeout), "write_file", True)
        if result.arguments and isinstance(result.arguments[0], dict):
            content = result.arguments[0].get("content")
            if not isinstance(content, str):
                result.issues.append("ARGUMENT_TYPE_DRIFT")
                result.status = "FAIL"
            elif len(content) < 1000:
                result.issues.append("MODEL_ARGUMENT_QUALITY")
                result.status = "WARN"
        return result

    if name == "shell_quoting":
        command = "python -c \"print({'a':[1,2,3]})\" | findstr a"
        payload = base_payload(model, [{"role": "user", "content": f"Call run_command with this exact command: {command}"}], [RUN_COMMAND], "required")
        return inspect_message(name, request_json(base_url, payload, timeout), "run_command", True)

    if name == "parallel_calls":
        payload = base_payload(model, [{"role": "user", "content": "Call get_weather separately for Berlin and Paris now."}], [WEATHER], "auto")
        result = inspect_message(name, request_json(base_url, payload, timeout), "get_weather", False)
        if len(result.tool_names) < 2 and result.status == "PASS":
            result.issues.append("MODEL_PARALLEL_CALL_QUALITY")
            result.status = "WARN"
        return result

    if name == "streaming_weather":
        payload = base_payload(model, [{"role": "user", "content": "Get the weather for Berlin using the tool."}], [WEATHER], "auto")
        events = request_stream(base_url, payload, timeout)
        content = ""
        saw_name = False
        saw_args = False
        leaked = False
        for event in events:
            choice = event.get("choices", [{}])[0]
            delta = choice.get("delta") or {}
            piece = delta.get("content") or ""
            content += piece
            leaked = leaked or any(marker in piece for marker in MARKERS)
            for call in delta.get("tool_calls") or []:
                fn = call.get("function") or {}
                saw_name = saw_name or bool(fn.get("name"))
                saw_args = saw_args or bool(fn.get("arguments"))
        issues = []
        if leaked:
            issues.append("PARSER_MARKUP_LEAK")
        if not saw_name or not saw_args:
            issues.append("STREAMING_STRUCTURE_LOSS")
        return Result(name, "PASS" if not issues else "FAIL", issues, content, ["get_weather"] if saw_name else [], [], None)

    if name == "roundtrip_after_tool":
        first_payload = base_payload(model, [{"role": "user", "content": "Get the weather for Berlin."}], [WEATHER], "required")
        first = request_json(base_url, first_payload, timeout)
        checked = inspect_message(name, first, "get_weather", True)
        if checked.status == "FAIL":
            return checked
        assistant = first["choices"][0]["message"]
        calls = assistant.get("tool_calls") or []
        if not calls:
            checked.issues.append("EMPTY_TOOL_CALLS")
            checked.status = "FAIL"
            return checked
        messages = [
            {"role": "user", "content": "Get the weather for Berlin."},
            assistant,
            {"role": "tool", "tool_call_id": calls[0]["id"], "content": "{\"city\":\"Berlin\",\"temperature_c\":21}"},
        ]
        second_payload = base_payload(model, messages, [WEATHER], "auto")
        second = inspect_message(name, request_json(base_url, second_payload, timeout), None, False)
        if second.tool_names:
            second.issues.append("ROUNDTRIP_RECALL")
            second.status = "FAIL"
        return second

    raise ValueError(f"unknown case: {name}")


CASES = [
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
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", required=True)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output", type=Path, default=Path("gemma4-toolcall-matrix.json"))
    args = parser.parse_args(argv or sys.argv[1:])

    results: list[Result] = []
    for case in CASES:
        try:
            result = run_case(args.base_url, args.model, args.timeout, case)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
            result = Result(case, "FAIL", [f"HARNESS_OR_TRANSPORT:{type(exc).__name__}:{exc}"], "", [], [], None)
        results.append(result)
        print(f"{result.status:4} {case}: {', '.join(result.issues) if result.issues else 'ok'}")

    payload = {
        "model": args.model,
        "base_url": args.base_url,
        "results": [asdict(item) for item in results],
        "summary": {
            "pass": sum(item.status == "PASS" for item in results),
            "warn": sum(item.status == "WARN" for item in results),
            "fail": sum(item.status == "FAIL" for item in results),
        },
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: {args.output}")
    return 1 if payload["summary"]["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
