#!/usr/bin/env python3
"""Dump Gemma4 structural/reserved token IDs from an exported model.

The script prefers tokenizer.json because it is dependency-free and gives the
exact vocabulary IDs stored with the model. If tokenizer.json is absent, it
tries openvino_genai.Tokenizer. Failure to inspect is reported as SKIP (exit 4),
not as a false parser failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_MARKERS = [
    '<|tool_call>',
    '<tool_call|>',
    '<|tool_response>',
    '<tool_response|>',
    '<|channel>',
    '<channel|>',
    '<|turn>',
    '<turn|>',
    '<|"|>',
    '<unused0>',
    '<unused1>',
    '<unused27>',
    '<unused45>',
    'multimodal',
]


def load_tokenizer_json(path: Path) -> dict[str, int] | None:
    candidate = path / 'tokenizer.json'
    if not candidate.is_file():
        return None
    data = json.loads(candidate.read_text(encoding='utf-8'))
    vocab: dict[str, int] = {}

    model = data.get('model')
    if isinstance(model, dict):
        model_vocab = model.get('vocab')
        if isinstance(model_vocab, dict):
            for token, token_id in model_vocab.items():
                if isinstance(token, str) and isinstance(token_id, int):
                    vocab[token] = token_id
        elif isinstance(model_vocab, list):
            # Some tokenizer JSON formats use [[token, score], ...] and rely on
            # list position as the token ID.
            for token_id, entry in enumerate(model_vocab):
                token = entry[0] if isinstance(entry, list) and entry else entry
                if isinstance(token, str):
                    vocab[token] = token_id

    added = data.get('added_tokens')
    if isinstance(added, list):
        for entry in added:
            if not isinstance(entry, dict):
                continue
            token = entry.get('content')
            token_id = entry.get('id')
            if isinstance(token, str) and isinstance(token_id, int):
                vocab[token] = token_id

    return vocab


def tensor_ids(value: Any) -> list[int]:
    if hasattr(value, 'input_ids'):
        value = value.input_ids
    if hasattr(value, 'data'):
        try:
            return [int(x) for x in value.data]
        except Exception:
            pass
    if hasattr(value, 'tolist'):
        raw = value.tolist()
        while isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], list):
            raw = raw[0]
        if isinstance(raw, list):
            return [int(x) for x in raw]
    try:
        return [int(x) for x in value]
    except Exception as exc:
        raise TypeError(f'cannot extract token IDs from {type(value)!r}: {exc}') from exc


def inspect_openvino_genai(model_path: Path, markers: list[str]) -> dict[str, Any]:
    import openvino_genai  # type: ignore

    tokenizer = openvino_genai.Tokenizer(str(model_path))
    result: dict[str, Any] = {}
    for marker in markers:
        encoded = None
        errors: list[str] = []
        for call in (
            lambda: tokenizer.encode(marker, add_special_tokens=False),
            lambda: tokenizer.encode(marker),
        ):
            try:
                encoded = call()
                break
            except TypeError as exc:
                errors.append(str(exc))
        if encoded is None:
            result[marker] = {'ids': [], 'error': '; '.join(errors) or 'encode failed'}
            continue
        try:
            ids = tensor_ids(encoded)
            result[marker] = {'ids': ids, 'single_token': len(ids) == 1}
        except Exception as exc:
            result[marker] = {'ids': [], 'error': str(exc)}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='Dump Gemma4 tokenizer IDs for structural and suspicious tokens')
    parser.add_argument('--model-path', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--marker', action='append', dest='markers', help='Additional marker to inspect; may be repeated')
    args = parser.parse_args()

    model_path = args.model_path.resolve()
    if not model_path.is_dir():
        parser.error(f'model path is not a directory: {model_path}')

    markers = list(DEFAULT_MARKERS)
    for marker in args.markers or []:
        if marker not in markers:
            markers.append(marker)

    payload: dict[str, Any] = {'model_path': str(model_path), 'markers': {}}
    vocab = load_tokenizer_json(model_path)
    if vocab is not None:
        payload['source'] = 'tokenizer.json'
        payload['markers'] = {
            marker: {'id': vocab.get(marker), 'present': marker in vocab}
            for marker in markers
        }
    else:
        try:
            payload['source'] = 'openvino_genai.Tokenizer'
            payload['markers'] = inspect_openvino_genai(model_path, markers)
        except Exception as exc:
            payload['source'] = 'unavailable'
            payload['error'] = str(exc)
            text = json.dumps(payload, indent=2, ensure_ascii=False) + '\n'
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text, encoding='utf-8')
            print(text, end='')
            print('SKIP: no tokenizer.json and openvino_genai tokenizer inspection failed.', file=sys.stderr)
            return 4

    text = json.dumps(payload, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding='utf-8')
    print(text, end='')

    # Structural markers should be single vocabulary entries in the canonical
    # Gemma4 tokenizer. Do not fail on reserved-token absence; those are merely
    # diagnostic witnesses from the corrupted generation trace.
    structural = ['<|tool_call>', '<tool_call|>', '<|channel>', '<channel|>']
    missing = []
    for marker in structural:
        entry = payload['markers'].get(marker, {})
        present = entry.get('present') if payload['source'] == 'tokenizer.json' else entry.get('single_token')
        if not present:
            missing.append(marker)
    if missing:
        print('FAIL: structural markers not resolved as single vocabulary entries: ' + ', '.join(missing), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
