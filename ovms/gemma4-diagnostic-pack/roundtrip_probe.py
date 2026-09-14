#!/usr/bin/env python3
"""Gemma4/OVMS roundtrip forensics probe.

Stdlib-only diagnostic harness for the failure boundary:

    user -> assistant tool_call -> tool result -> next assistant turn

It captures exact requests/responses, unary and SSE behavior, timings, usage,
context/token counts when the server reports them, special-token leakage, and a
small failure-classification/localization report. It deliberately never guesses
token counts that OVMS did not report.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SPECIAL_TOKEN_RE = re.compile(r"<eos>|<unused\d+>|<pad>|(?:^|\s)(multimodal)(?:\s|$)", re.IGNORECASE)
SERVER_LOG_PATTERNS = [
    "ERROR",
    "FATAL",
    "exception",
    "CL_OUT_OF_RESOURCES",
    "GPU_CONTEXT_FATAL",
    "quarantine",
    "timeout",
    "xgrammar",
    "grammar",
    "tool",
    "stream",
    "executor",
]

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

DEFAULT_PROMPT = "Ask me one simple test question using the question tool."
DEFAULT_TOOL_RESULT = {"answer": "A"}


def artifact_metadata(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    stat = resolved.stat()
    h = hashlib.sha256()
    with resolved.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    mtime = dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.timezone.utc).isoformat()
    return {
        "path": str(resolved),
        "size_bytes": stat.st_size,
        "mtime_utc": mtime,
        "sha256": h.hexdigest(),
    }


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def endpoint_urls(base_url: str) -> dict[str, str]:
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
            "--base-url must be an origin, a base ending in /v1 or /v3, "
            "or a full .../chat/completions URL"
        )
    return {
        "origin": origin,
        "chat": chat,
        "models_v1": origin + "/v1/models",
        "models_v3": origin + "/v3/models",
    }


def find_special_tokens(text: str) -> list[str]:
    found: set[str] = set()
    for match in SPECIAL_TOKEN_RE.finditer(text or ""):
        token = match.group(1) or match.group(0).strip()
        if token.lower() == "multimodal":
            token = "multimodal"
        elif token.lower() == "<eos>":
            token = "<eos>"
        elif token.lower() == "<pad>":
            token = "<pad>"
        found.add(token)
    return sorted(found)


def response_message(obj: dict[str, Any]) -> dict[str, Any]:
    try:
        value = obj["choices"][0]["message"]
        return value if isinstance(value, dict) else {}
    except (KeyError, IndexError, TypeError):
        return {}


def response_tool_calls(obj: dict[str, Any]) -> list[dict[str, Any]]:
    calls = response_message(obj).get("tool_calls")
    return calls if isinstance(calls, list) else []


def response_finish_reason(obj: dict[str, Any]) -> str | None:
    try:
        value = obj["choices"][0].get("finish_reason")
        return str(value) if value is not None else None
    except (KeyError, IndexError, TypeError, AttributeError):
        return None


def response_usage(obj: dict[str, Any]) -> dict[str, Any]:
    value = obj.get("usage") if isinstance(obj, dict) else None
    return value if isinstance(value, dict) else {}


def validate_tool_calls(calls: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for idx, call in enumerate(calls):
        if not isinstance(call, dict):
            errors.append(f"tool_calls[{idx}] is not an object")
            continue
        if not call.get("id"):
            errors.append(f"tool_calls[{idx}] has no id")
        fn = call.get("function")
        if not isinstance(fn, dict):
            errors.append(f"tool_calls[{idx}].function is not an object")
            continue
        if not fn.get("name"):
            errors.append(f"tool_calls[{idx}].function.name is empty")
        args = fn.get("arguments")
        if isinstance(args, dict):
            continue
        if not isinstance(args, str):
            errors.append(f"tool_calls[{idx}].function.arguments is not string/object")
            continue
        try:
            parsed = json.loads(args)
            if not isinstance(parsed, dict):
                errors.append(f"tool_calls[{idx}].function.arguments is not a JSON object")
        except json.JSONDecodeError as exc:
            errors.append(f"tool_calls[{idx}].function.arguments invalid JSON: {exc}")
    return errors


def classify_response(obj: dict[str, Any], *, raw: str, phase: str) -> list[str]:
    classes: list[str] = []
    if find_special_tokens(raw):
        classes.append("SPECIAL_TOKEN_LEAK")
    calls = response_tool_calls(obj)
    if validate_tool_calls(calls):
        classes.append("MALFORMED_TOOL_ARGS")
    if phase == "turn1":
        if not calls:
            classes.append("TURN1_NO_TOOL_CALL")
        elif not calls[0].get("id"):
            classes.append("TOOL_ID_MISSING")
    if phase == "turn2":
        content = str(response_message(obj).get("content") or "").strip()
        if not content and not calls:
            classes.append("EMPTY_TURN2")
            usage = response_usage(obj)
            completion_tokens = usage.get("completion_tokens")
            finish = response_finish_reason(obj)
            if isinstance(completion_tokens, int) and completion_tokens <= 1 and finish == "stop":
                classes.append("IMMEDIATE_EOS")
    return classes


def throughput_metrics(usage: dict[str, Any], *, total_s: float | None, ttft_s: float | None) -> dict[str, Any]:
    prompt_tokens = usage.get("prompt_tokens") if isinstance(usage.get("prompt_tokens"), int) else None
    completion_tokens = usage.get("completion_tokens") if isinstance(usage.get("completion_tokens"), int) else None
    total_tokens = usage.get("total_tokens") if isinstance(usage.get("total_tokens"), int) else None
    wall_tps = None
    after_ttft_tps = None
    if completion_tokens is not None and total_s is not None and total_s > 0:
        wall_tps = completion_tokens / total_s
    if completion_tokens is not None and total_s is not None and ttft_s is not None and total_s > ttft_s:
        after_ttft_tps = completion_tokens / (total_s - ttft_s)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "tokens_per_second_wall": wall_tps,
        "tokens_per_second_after_ttft": after_ttft_tps,
    }


def request_stats(payload: dict[str, Any]) -> dict[str, Any]:
    encoded = json_bytes(payload)
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    tools = payload.get("tools") if isinstance(payload.get("tools"), list) else []
    return {
        "request_json_bytes": len(encoded),
        "message_count": len(messages),
        "tool_count": len(tools),
        "messages_json_bytes": len(json_bytes(messages)),
        "tools_json_bytes": len(json_bytes(tools)),
    }


def headers_dict(headers: Any) -> dict[str, str]:
    try:
        return {str(k): str(v) for k, v in headers.items()}
    except Exception:
        return {}


def http_get_timed(url: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Authorization": "Bearer unused"}, method="GET")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            ttfb = time.perf_counter() - start
            raw = response.read().decode("utf-8", errors="replace")
            total = time.perf_counter() - start
            return {"status": response.status, "raw": raw, "headers": headers_dict(response.headers), "timing": {"ttfb_s": ttfb, "total_s": total}, "transport_error": None}
    except urllib.error.HTTPError as exc:
        ttfb = time.perf_counter() - start
        raw = exc.read().decode("utf-8", errors="replace")
        return {"status": exc.code, "raw": raw, "headers": headers_dict(exc.headers), "timing": {"ttfb_s": ttfb, "total_s": time.perf_counter() - start}, "transport_error": f"HTTPError: {exc}"}
    except Exception as exc:
        return {"status": None, "raw": "", "headers": {}, "timing": {"ttfb_s": None, "total_s": time.perf_counter() - start}, "transport_error": f"{type(exc).__name__}: {exc}"}


def http_json_timed(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json_bytes(payload)
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "Authorization": "Bearer unused"}, method="POST")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            ttfb = time.perf_counter() - start
            raw = response.read().decode("utf-8", errors="replace")
            total = time.perf_counter() - start
            return {"status": response.status, "raw": raw, "headers": headers_dict(response.headers), "timing": {"ttfb_s": ttfb, "ttft_s": None, "total_s": total}, "transport_error": None}
    except urllib.error.HTTPError as exc:
        ttfb = time.perf_counter() - start
        raw = exc.read().decode("utf-8", errors="replace")
        return {"status": exc.code, "raw": raw, "headers": headers_dict(exc.headers), "timing": {"ttfb_s": ttfb, "ttft_s": None, "total_s": time.perf_counter() - start}, "transport_error": f"HTTPError: {exc}"}
    except Exception as exc:
        return {"status": None, "raw": "", "headers": {}, "timing": {"ttfb_s": None, "ttft_s": None, "total_s": time.perf_counter() - start}, "transport_error": f"{type(exc).__name__}: {exc}"}


def _event_is_meaningful(obj: dict[str, Any]) -> bool:
    try:
        delta = obj["choices"][0]["delta"]
    except (KeyError, IndexError, TypeError):
        return False
    if not isinstance(delta, dict):
        return False
    if str(delta.get("content") or ""):
        return True
    if str(delta.get("reasoning_content") or ""):
        return True
    return bool(delta.get("tool_calls"))


def http_sse_timed(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json_bytes(payload)
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "Authorization": "Bearer unused"}, method="POST")
    start = time.perf_counter()
    lines: list[str] = []
    timeline: list[dict[str, Any]] = []
    first_event_s: float | None = None
    first_meaningful_s: float | None = None
    last_event_s: float | None = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            ttfb = time.perf_counter() - start
            while True:
                raw_line = response.readline()
                if not raw_line:
                    break
                now = time.perf_counter() - start
                line = raw_line.decode("utf-8", errors="replace")
                lines.append(line)
                stripped = line.strip()
                if not stripped.startswith("data:"):
                    continue
                data = stripped[5:].strip()
                if first_event_s is None:
                    first_event_s = now
                last_event_s = now
                event: dict[str, Any] = {"offset_s": now, "data": data}
                if data != "[DONE]":
                    try:
                        obj = json.loads(data)
                        event["json"] = obj
                        if first_meaningful_s is None and isinstance(obj, dict) and _event_is_meaningful(obj):
                            first_meaningful_s = now
                    except json.JSONDecodeError as exc:
                        event["json_error"] = str(exc)
                timeline.append(event)
            total = time.perf_counter() - start
            return {"status": response.status, "raw": "".join(lines), "headers": headers_dict(response.headers), "timing": {"ttfb_s": ttfb, "first_sse_event_s": first_event_s, "ttft_s": first_meaningful_s, "last_sse_event_s": last_event_s, "total_s": total}, "timeline": timeline, "transport_error": None}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {"status": exc.code, "raw": raw, "headers": headers_dict(exc.headers), "timing": {"ttfb_s": time.perf_counter() - start, "first_sse_event_s": first_event_s, "ttft_s": first_meaningful_s, "last_sse_event_s": last_event_s, "total_s": time.perf_counter() - start}, "timeline": timeline, "transport_error": f"HTTPError: {exc}"}
    except Exception as exc:
        return {"status": None, "raw": "".join(lines), "headers": {}, "timing": {"ttfb_s": None, "first_sse_event_s": first_event_s, "ttft_s": first_meaningful_s, "last_sse_event_s": last_event_s, "total_s": time.perf_counter() - start}, "timeline": timeline, "transport_error": f"{type(exc).__name__}: {exc}"}


def parse_sse_text(raw: str) -> dict[str, Any]:
    tool_calls_by_index: dict[int, dict[str, Any]] = {}
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    finish: str | None = None
    usage: dict[str, Any] = {}
    done = False
    parse_errors: list[str] = []
    event_count = 0
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        data = stripped[5:].strip()
        if data == "[DONE]":
            done = True
            continue
        if not data:
            continue
        event_count += 1
        try:
            obj = json.loads(data)
        except json.JSONDecodeError as exc:
            parse_errors.append(str(exc))
            continue
        if isinstance(obj.get("usage"), dict):
            usage = obj["usage"]
        choices = obj.get("choices")
        if not isinstance(choices, list) or not choices:
            continue
        choice = choices[0]
        if not isinstance(choice, dict):
            continue
        if choice.get("finish_reason") is not None:
            finish = str(choice["finish_reason"])
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            continue
        if delta.get("content") is not None:
            content_parts.append(str(delta.get("content") or ""))
        if delta.get("reasoning_content") is not None:
            reasoning_parts.append(str(delta.get("reasoning_content") or ""))
        tc_deltas = delta.get("tool_calls")
        if not isinstance(tc_deltas, list):
            continue
        for item in tc_deltas:
            if not isinstance(item, dict):
                continue
            idx = item.get("index") if isinstance(item.get("index"), int) else 0
            target = tool_calls_by_index.setdefault(idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
            if item.get("id"):
                target["id"] += str(item["id"])
            if item.get("type"):
                target["type"] = str(item["type"])
            fn = item.get("function")
            if isinstance(fn, dict):
                if fn.get("name"):
                    target["function"]["name"] += str(fn["name"])
                if fn.get("arguments") is not None:
                    target["function"]["arguments"] += str(fn.get("arguments") or "")
    return {"done": done, "event_count": event_count, "content": "".join(content_parts), "reasoning_content": "".join(reasoning_parts), "tool_calls": [tool_calls_by_index[k] for k in sorted(tool_calls_by_index)], "finish_reason": finish, "usage": usage, "parse_errors": parse_errors}


def base_turn1_payload(model: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    return {"model": model, "messages": [{"role": "user", "content": prompt}], "tools": [QUESTION_TOOL], "tool_choice": "required", "temperature": 0.0, "max_tokens": max_tokens, "stream": False}


def build_turn2_payload(*, model: str, user_prompt: str, assistant: dict[str, Any], tool_result: Any, tools: list[dict[str, Any]], max_tokens: int) -> dict[str, Any]:
    calls = assistant.get("tool_calls") if isinstance(assistant, dict) else None
    if not isinstance(calls, list) or not calls or not isinstance(calls[0], dict) or not calls[0].get("id"):
        raise ValueError("assistant has no first tool_call id")
    return {
        "model": model,
        "messages": [
            {"role": "user", "content": user_prompt},
            copy.deepcopy(assistant),
            {"role": "tool", "tool_call_id": calls[0]["id"], "content": json.dumps(tool_result, ensure_ascii=False, separators=(",", ":"))},
        ],
        "tools": copy.deepcopy(tools),
        "tool_choice": "auto",
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "stream": False,
    }


def history_variant(assistant: dict[str, Any], variant: str) -> dict[str, Any]:
    value = copy.deepcopy(assistant)
    if variant == "exact":
        return value
    if variant == "clean-null":
        value["content"] = None
        return value
    if variant == "clean-empty":
        value["content"] = ""
        return value
    raise ValueError(f"unknown history variant: {variant}")


def parse_json_object(raw: str) -> tuple[dict[str, Any], str | None]:
    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            return value, None
        return {}, "response JSON is not an object"
    except json.JSONDecodeError as exc:
        return {}, f"invalid JSON: {exc}"


def save_http_exchange(directory: Path, payload: dict[str, Any], result: dict[str, Any], *, sse: bool) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "request.json", payload)
    write_json(directory / "request-stats.json", request_stats(payload))
    write_json(directory / "response-headers.json", result.get("headers", {}))
    write_json(directory / "timing.json", result.get("timing", {}))
    if result.get("timeline") is not None:
        write_json(directory / "sse-timeline.json", result.get("timeline", []))
    name = "response.sse.txt" if sse else "response.raw.txt"
    (directory / name).write_text(str(result.get("raw") or ""), encoding="utf-8")


def unary_summary(result: dict[str, Any], *, phase: str) -> dict[str, Any]:
    raw = str(result.get("raw") or "")
    obj, json_error = parse_json_object(raw) if result.get("status") == 200 else ({}, None)
    classes: list[str] = []
    errors: list[str] = []
    if result.get("status") != 200:
        classes.append("HTTP_ERROR" if result.get("status") is not None else "TRANSPORT_ERROR")
        errors.append(f"status={result.get('status')} transport={result.get('transport_error')}")
    if json_error:
        classes.append("INVALID_JSON")
        errors.append(json_error)
    if obj:
        classes.extend(classify_response(obj, raw=raw, phase=phase))
        errors.extend(validate_tool_calls(response_tool_calls(obj)))
    timing = result.get("timing", {})
    usage = response_usage(obj)
    metrics = throughput_metrics(usage, total_s=timing.get("total_s"), ttft_s=None)
    return {"http_status": result.get("status"), "transport_error": result.get("transport_error"), "finish_reason": response_finish_reason(obj), "message": response_message(obj), "tool_calls": response_tool_calls(obj), "usage": usage, "timing": timing, "throughput": metrics, "special_tokens": find_special_tokens(raw), "failure_classes": sorted(set(classes)), "errors": errors, "parsed_response": obj}


def stream_summary(result: dict[str, Any], *, phase: str) -> dict[str, Any]:
    raw = str(result.get("raw") or "")
    parsed = parse_sse_text(raw)
    classes: list[str] = []
    errors: list[str] = []
    if result.get("status") != 200:
        classes.append("HTTP_ERROR" if result.get("status") is not None else "TRANSPORT_ERROR")
        errors.append(f"status={result.get('status')} transport={result.get('transport_error')}")
    if parsed["parse_errors"]:
        classes.append("INVALID_SSE_JSON")
        errors.extend(parsed["parse_errors"])
    if not parsed["done"]:
        classes.append("SSE_NO_DONE")
    special = find_special_tokens(raw)
    if special:
        classes.append("SPECIAL_TOKEN_LEAK")
    tc_errors = validate_tool_calls(parsed["tool_calls"])
    if tc_errors:
        classes.append("MALFORMED_TOOL_ARGS")
        errors.extend(tc_errors)
    if phase == "turn2" and not parsed["content"].strip() and not parsed["tool_calls"]:
        classes.append("SSE_ZERO_DELTA")
        completion_tokens = parsed["usage"].get("completion_tokens") if isinstance(parsed["usage"], dict) else None
        if isinstance(completion_tokens, int) and completion_tokens <= 1 and parsed["finish_reason"] == "stop":
            classes.append("IMMEDIATE_EOS")
    timing = result.get("timing", {})
    metrics = throughput_metrics(parsed["usage"], total_s=timing.get("total_s"), ttft_s=timing.get("ttft_s"))
    return {"http_status": result.get("status"), "transport_error": result.get("transport_error"), "finish_reason": parsed["finish_reason"], "content": parsed["content"], "reasoning_content": parsed["reasoning_content"], "tool_calls": parsed["tool_calls"], "usage": parsed["usage"], "timing": timing, "throughput": metrics, "special_tokens": special, "failure_classes": sorted(set(classes)), "errors": errors, "done": parsed["done"], "event_count": parsed["event_count"]}


def is_nonempty_unary(summary: dict[str, Any]) -> bool:
    msg = summary.get("message") if isinstance(summary.get("message"), dict) else {}
    return bool(str(msg.get("content") or "").strip() or summary.get("tool_calls"))


def is_nonempty_stream(summary: dict[str, Any]) -> bool:
    return bool(str(summary.get("content") or "").strip() or summary.get("tool_calls"))


def localize_roundtrip(variants: dict[str, Any], turn1_summary: dict[str, Any]) -> dict[str, Any]:
    exact = variants.get("exact", {})
    unary = exact.get("unary", {})
    stream = exact.get("stream", {})
    unary_nonempty = is_nonempty_unary(unary)
    stream_nonempty = is_nonempty_stream(stream)
    classifications: list[str] = []
    likely_subsystems: list[str] = []
    if not unary_nonempty and not stream_nonempty:
        classifications.append("GENERATION_OR_REENTRY_FAILURE")
        likely_subsystems.extend(["session_state", "generation_config", "chat_template_after_tool_result"])
    elif not unary_nonempty and stream_nonempty:
        classifications.append("PARSER_DROPPED_OUTPUT")
        likely_subsystems.extend(["output_parser", "openai_serializer"])
    elif unary_nonempty and not stream_nonempty:
        classifications.append("STREAMING_PATH_FAILURE")
        likely_subsystems.extend(["streamer", "streaming_parser", "openai_stream_serializer"])
    cleaned = []
    for name in ("clean-null", "clean-empty"):
        item = variants.get(name)
        if not item:
            continue
        if is_nonempty_unary(item.get("unary", {})) or is_nonempty_stream(item.get("stream", {})):
            cleaned.append(name)
    if not unary_nonempty and not stream_nonempty and cleaned:
        classifications.append("HISTORY_CONTENT_CONTAMINATION")
        likely_subsystems.extend(["special_token_filtering", "history_serialization"])
    elif not unary_nonempty and not stream_nonempty and variants and not cleaned:
        classifications.append("CLEAN_HISTORY_STILL_FAILS")
    if "SPECIAL_TOKEN_LEAK" in turn1_summary.get("failure_classes", []):
        classifications.append("TURN1_SPECIAL_TOKEN_LEAK")
        likely_subsystems.extend(["streamer", "output_parser_special_token_filtering"])
    return {"classification": sorted(set(classifications)), "likely_subsystems": list(dict.fromkeys(likely_subsystems)), "exact_unary_nonempty": unary_nonempty, "exact_stream_nonempty": stream_nonempty, "clean_variants_that_recover": cleaned}


def snapshot_models(urls: dict[str, str], timeout: float, out: Path) -> dict[str, Any]:
    snapshots: dict[str, Any] = {}
    for key in ("models_v1", "models_v3"):
        result = http_get_timed(urls[key], timeout)
        snapshots[key] = {"url": urls[key], "status": result["status"], "headers": result["headers"], "timing": result["timing"], "transport_error": result["transport_error"]}
        (out / f"{key}.raw.txt").write_text(result["raw"], encoding="utf-8")
    write_json(out / "models-snapshot.json", snapshots)
    return snapshots


def scan_server_log(path: Path, out: Path) -> dict[str, Any]:
    target = out / "server-log.txt"
    shutil.copy2(path, target)
    text = target.read_text(encoding="utf-8", errors="replace")
    counts: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    lines = text.splitlines()
    for pattern in SERVER_LOG_PATTERNS:
        matched = [line for line in lines if pattern.lower() in line.lower()]
        counts[pattern] = len(matched)
        samples[pattern] = matched[-5:]
    result = {"source": str(path), "copied_to": str(target), "counts": counts, "samples": samples}
    write_json(out / "server-log-scan.json", result)
    return result


def run_iteration(out: Path, *, urls: dict[str, str], model: str, prompt: str, tool_result: Any, timeout: float, max_tokens: int, variants: list[str]) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    turn1_payload = base_turn1_payload(model, prompt, max_tokens)
    turn1_result = http_json_timed(urls["chat"], turn1_payload, timeout)
    turn1_dir = out / "turn1"
    save_http_exchange(turn1_dir, turn1_payload, turn1_result, sse=False)
    turn1 = unary_summary(turn1_result, phase="turn1")
    write_json(turn1_dir / "parsed-response.json", turn1.get("parsed_response", {}))
    write_json(turn1_dir / "summary.json", {k: v for k, v in turn1.items() if k != "parsed_response"})
    calls = turn1.get("tool_calls") or []
    assistant = turn1.get("message") if isinstance(turn1.get("message"), dict) else {}
    turn1_usable = turn1.get("http_status") == 200 and bool(calls) and calls[0].get("id") and calls[0].get("function", {}).get("name") == "question" and "MALFORMED_TOOL_ARGS" not in turn1.get("failure_classes", [])
    if not turn1_usable:
        summary = {"pass": False, "turn1_usable": False, "turn1": {k: v for k, v in turn1.items() if k != "parsed_response"}, "variants": {}, "localization": {"classification": ["TURN1_BLOCKS_ROUNDTRIP"], "likely_subsystems": ["generation_config", "tool_parser", "openai_serializer"]}}
        write_json(out / "summary.json", summary)
        return summary
    write_json(out / "assistant-turn1-exact.json", assistant)
    variant_results: dict[str, Any] = {}
    for variant in variants:
        variant_dir = out / f"turn2-{variant}"
        assistant_variant = history_variant(assistant, variant)
        payload = build_turn2_payload(model=model, user_prompt=prompt, assistant=assistant_variant, tool_result=tool_result, tools=[QUESTION_TOOL], max_tokens=max_tokens)
        write_json(variant_dir / "history.json", payload["messages"])
        unary_result = http_json_timed(urls["chat"], payload, timeout)
        unary_dir = variant_dir / "unary"
        save_http_exchange(unary_dir, payload, unary_result, sse=False)
        unary = unary_summary(unary_result, phase="turn2")
        write_json(unary_dir / "parsed-response.json", unary.get("parsed_response", {}))
        write_json(unary_dir / "summary.json", {k: v for k, v in unary.items() if k != "parsed_response"})
        stream_payload = copy.deepcopy(payload)
        stream_payload["stream"] = True
        stream_result = http_sse_timed(urls["chat"], stream_payload, timeout)
        stream_dir = variant_dir / "stream"
        save_http_exchange(stream_dir, stream_payload, stream_result, sse=True)
        stream = stream_summary(stream_result, phase="turn2")
        write_json(stream_dir / "summary.json", stream)
        variant_results[variant] = {"unary": {k: v for k, v in unary.items() if k != "parsed_response"}, "stream": stream}
    localization = localize_roundtrip(variant_results, turn1)
    exact = variant_results.get("exact", {})
    exact_unary = exact.get("unary", {})
    exact_stream = exact.get("stream", {})
    blocking_classes = set(turn1.get("failure_classes", [])) | set(exact_unary.get("failure_classes", [])) | set(exact_stream.get("failure_classes", []))
    strict_pass = turn1_usable and is_nonempty_unary(exact_unary) and is_nonempty_stream(exact_stream) and exact_unary.get("http_status") == 200 and exact_stream.get("http_status") == 200 and exact_stream.get("done") is True and not (blocking_classes & {"SPECIAL_TOKEN_LEAK", "MALFORMED_TOOL_ARGS", "EMPTY_TURN2", "IMMEDIATE_EOS", "SSE_ZERO_DELTA", "HTTP_ERROR", "TRANSPORT_ERROR", "INVALID_JSON", "INVALID_SSE_JSON", "SSE_NO_DONE"})
    summary = {"pass": strict_pass, "turn1_usable": turn1_usable, "turn1": {k: v for k, v in turn1.items() if k != "parsed_response"}, "variants": variant_results, "localization": localization}
    write_json(out / "summary.json", summary)
    return summary


def md(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def write_report(path: Path, manifest: dict[str, Any], runs: list[dict[str, Any]]) -> None:
    lines = ["# Gemma4 Roundtrip Forensics Report", "", f"Generated: `{manifest['generated_at_utc']}`", f"Endpoint: `{manifest['chat_url']}`", f"Model: `{manifest['model']}`", f"Overall: `{'PASS' if manifest['pass'] else 'FAIL'}`", "", "## Run summary", "", "| Run | Result | Turn1 | Exact unary | Exact stream | Localization |", "|---:|---|---|---|---|---|"]
    for idx, run in enumerate(runs, 1):
        t1 = run.get("turn1", {})
        exact = run.get("variants", {}).get("exact", {})
        u = exact.get("unary", {})
        s = exact.get("stream", {})
        loc = ", ".join(run.get("localization", {}).get("classification", [])) or "none"
        lines.append(f"| {idx} | {'PASS' if run.get('pass') else 'FAIL'} | {','.join(t1.get('failure_classes', [])) or 'OK'} | {','.join(u.get('failure_classes', [])) or 'OK'} | {','.join(s.get('failure_classes', [])) or 'OK'} | {loc} |")
    lines.extend(["", "## Exact-path metrics", "", "| Run | Phase | HTTP | Finish | Prompt tok | Completion tok | TTFB s | TTFT s | Total s | tok/s wall | tok/s after TTFT |", "|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|"])
    for idx, run in enumerate(runs, 1):
        rows = [("turn1", run.get("turn1", {}))]
        exact = run.get("variants", {}).get("exact", {})
        rows.extend([("turn2 unary", exact.get("unary", {})), ("turn2 stream", exact.get("stream", {}))])
        for phase, item in rows:
            timing = item.get("timing", {})
            tp = item.get("throughput", {})
            lines.append(f"| {idx} | {phase} | {md(item.get('http_status'))} | {md(item.get('finish_reason'))} | {md(tp.get('prompt_tokens'))} | {md(tp.get('completion_tokens'))} | {md(timing.get('ttfb_s'))} | {md(timing.get('ttft_s'))} | {md(timing.get('total_s'))} | {md(tp.get('tokens_per_second_wall'))} | {md(tp.get('tokens_per_second_after_ttft'))} |")
    lines.extend(["", "## Interpretation", ""])
    for idx, run in enumerate(runs, 1):
        loc = run.get("localization", {})
        lines.extend([f"### Run {idx}", "", f"Classification: `{', '.join(loc.get('classification', [])) or 'none'}`", "", f"Likely subsystems: `{', '.join(loc.get('likely_subsystems', [])) or 'none'}`", ""])
        if loc.get("clean_variants_that_recover"):
            lines.extend(["Clean-history variants that recover: `" + ", ".join(loc["clean_variants_that_recover"]) + "`", ""])
    lines.extend(["## Evidence layout", "", "Each run contains the exact turn1 request/response and, for each history variant, both unary and streaming turn2 exchanges. Raw SSE, event timing, response headers, request sizes, parsed responses, and summaries are retained next to each exchange.", "", "`TTFT` is reported only for streaming, where a first meaningful delta can actually be observed. Unary requests report TTFB and total latency; no fake TTFT is synthesized.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Forensic Gemma4 tool-result roundtrip probe for OVMS")
    parser.add_argument("--base-url", default="http://127.0.0.1:9090/v3")
    parser.add_argument("--model", default="gemma4")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--tool-result", default=json.dumps(DEFAULT_TOOL_RESULT), help="JSON value returned by the synthetic question tool")
    parser.add_argument("--history-variants", default="exact,clean-null,clean-empty")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--server-log", type=Path)
    parser.add_argument("--artifact-path", type=Path, help="Exact ovms binary under test; records SHA256/size/mtime")
    parser.add_argument("--source-head", help="Optional source commit/ref provenance")
    parser.add_argument("--run-label", help="Optional human label such as RC2")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be >= 1")
    try:
        tool_result = json.loads(args.tool_result)
    except json.JSONDecodeError as exc:
        parser.error(f"--tool-result must be valid JSON: {exc}")
    variants = [v.strip() for v in args.history_variants.split(",") if v.strip()]
    allowed = {"exact", "clean-null", "clean-empty"}
    if "exact" not in variants:
        parser.error("--history-variants must include exact")
    unknown = [v for v in variants if v not in allowed]
    if unknown:
        parser.error("unknown history variants: " + ", ".join(unknown))
    urls = endpoint_urls(args.base_url)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = args.output_dir or (Path(__file__).resolve().parent / "runtime" / "roundtrip-forensics" / stamp)
    out.mkdir(parents=True, exist_ok=True)
    artifact = None
    if args.artifact_path:
        if not args.artifact_path.exists():
            parser.error(f"--artifact-path not found: {args.artifact_path}")
        artifact = artifact_metadata(args.artifact_path)
    environment = {
        "generated_at_utc": utc_now(), "argv": sys.argv, "python": sys.version, "python_executable": sys.executable, "platform": platform.platform(), "hostname": platform.node(), "pid": os.getpid(), "base_url": args.base_url, "chat_url": urls["chat"], "model": args.model, "timeout_s": args.timeout, "max_tokens": args.max_tokens, "prompt": args.prompt, "tool_result": tool_result, "history_variants": variants, "repeat": args.repeat, "run_label": args.run_label, "source_head": args.source_head, "artifact": artifact,
    }
    write_json(out / "environment.json", environment)
    snapshot_models(urls, min(args.timeout, 30.0), out)
    print(f"chat endpoint: {urls['chat']}")
    print(f"model: {args.model}")
    print(f"evidence: {out}")
    print(f"history variants: {', '.join(variants)}")
    runs: list[dict[str, Any]] = []
    for idx in range(1, args.repeat + 1):
        run_dir = out / f"run-{idx:03d}"
        print(f"[run {idx}/{args.repeat}]", end=" ", flush=True)
        result = run_iteration(run_dir, urls=urls, model=args.model, prompt=args.prompt, tool_result=tool_result, timeout=args.timeout, max_tokens=args.max_tokens, variants=variants)
        runs.append(result)
        loc = ",".join(result.get("localization", {}).get("classification", [])) or "none"
        print(("PASS" if result.get("pass") else "FAIL") + f" [{loc}]")
    server_log = None
    if args.server_log:
        if args.server_log.exists():
            server_log = scan_server_log(args.server_log, out)
        else:
            server_log = {"source": str(args.server_log), "error": "not found"}
            write_json(out / "server-log-scan.json", server_log)
    overall_pass = all(run.get("pass") for run in runs)
    manifest = {**environment, "pass": overall_pass, "runs": len(runs), "passed_runs": sum(1 for r in runs if r.get("pass")), "failed_runs": sum(1 for r in runs if not r.get("pass")), "server_log": server_log}
    write_json(out / "manifest.json", manifest)
    write_json(out / "summary.json", {"manifest": manifest, "runs": runs})
    write_report(out / "REPORT.md", manifest, runs)
    print(f"OVERALL: {'PASS' if overall_pass else 'FAIL'}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
