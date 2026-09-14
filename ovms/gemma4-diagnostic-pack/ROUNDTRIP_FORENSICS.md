# Gemma4 Roundtrip Forensics

`roundtrip_probe.py` is a focused diagnostic harness for the protocol boundary:

```text
user -> assistant tool_call -> tool result -> next assistant turn
```

It is intentionally separate from `toolcall_matrix.py`: the matrix answers
"does tool-calling basically work?" while this probe answers "why does the
second assistant turn die after a successful tool result?"

## What it captures

For every run the probe stores:

- exact turn1 request and raw/parsed response;
- exact assistant message returned by OVMS, including tool call IDs;
- exact turn2 message history;
- turn2 unary response;
- turn2 SSE response plus event timeline;
- response headers;
- request JSON sizes and message/tool-schema sizes;
- HTTP status, finish reason and tool call data;
- TTFB and total latency for unary requests;
- TTFB, first SSE event, real streaming TTFT, last event and total latency;
- prompt/completion/total token counts when OVMS reports `usage`;
- tokens/sec only when a server-reported token count exists;
- special-token leakage, including `<eos>`, `<pad>`, `<unusedN>` and `multimodal`;
- `/v1/models` and `/v3/models` snapshots;
- optional exact OVMS binary SHA256/size/mtime;
- optional source ref and run label;
- optional OVMS server-log copy and fault-pattern scan.

No token count or TTFT is fabricated. Unary requests cannot expose true TTFT,
so unary reports TTFB and total latency only.

## History variants

The default run executes turn2 three ways:

1. `exact`: use the assistant message exactly as OVMS returned it;
2. `clean-null`: replace assistant `content` with `null`;
3. `clean-empty`: replace assistant `content` with `""`.

Each variant is tested both unary and streaming. This directly distinguishes a
history-contamination bug from a deeper generation/session/template re-entry
failure.

Only the exact path determines PASS. Cleaned variants are diagnostic controls.

## Failure classes

Important emitted classes include:

- `SPECIAL_TOKEN_LEAK`
- `TURN1_NO_TOOL_CALL`
- `TOOL_ID_MISSING`
- `MALFORMED_TOOL_ARGS`
- `EMPTY_TURN2`
- `IMMEDIATE_EOS`
- `SSE_ZERO_DELTA`
- `SSE_NO_DONE`
- `HTTP_ERROR`
- `TRANSPORT_ERROR`
- `INVALID_JSON`
- `INVALID_SSE_JSON`

Cross-path localization adds:

- `GENERATION_OR_REENTRY_FAILURE`: unary and stream are both empty;
- `PARSER_DROPPED_OUTPUT`: unary is empty but stream has meaningful output;
- `STREAMING_PATH_FAILURE`: unary works but stream is empty;
- `HISTORY_CONTENT_CONTAMINATION`: exact fails but a cleaned history recovers;
- `CLEAN_HISTORY_STILL_FAILS`: exact and cleaned histories all fail;
- `TURN1_SPECIAL_TOKEN_LEAK`: first tool response itself contains a reserved token.

## RC2 reference signature

The RC2 acceptance run that motivated this probe showed:

```text
turn1 tool call: PASS
turn2 HTTP:      200
turn2 finish:    stop
turn2 content:   ""
turn2 tool_calls: []
completion_tokens: 1
```

The same empty turn2 was reproduced after replacing the turn1 assistant
`content` with both `null` and `""`. Separately, all successful tool-call
responses leaked `<eos>` through `content`.

That combination should localize as roughly:

```text
IMMEDIATE_EOS
EMPTY_TURN2 / SSE_ZERO_DELTA
GENERATION_OR_REENTRY_FAILURE
CLEAN_HISTORY_STILL_FAILS
TURN1_SPECIAL_TOKEN_LEAK
```

The two defects must be treated independently until evidence proves a shared
cause. Fixing `<eos>` filtering alone is not sufficient evidence that roundtrip
continuation works.

## Windows RC2 example

```powershell
python .\ovms\gemma4-diagnostic-pack\roundtrip_probe.py `
  --base-url http://127.0.0.1:18091/v3 `
  --model gemma4 `
  --run-label RC2 `
  --artifact-path C:\git\artifacts\ovms-908d6695-rc2-repacked-20260914\ovms\ovms.exe `
  --source-head a2eaeb783dfd66f80c50070bf7050dd184b01364 `
  --server-log C:\path\to\server.stdout.log `
  --output-dir C:\Users\testc\AppData\Local\Temp\opencode\rc2-roundtrip-forensics `
  --timeout 240 `
  --max-tokens 256
```

For repeated confirmation after a patch:

```powershell
python .\ovms\gemma4-diagnostic-pack\roundtrip_probe.py `
  --base-url http://127.0.0.1:18091/v3 `
  --model gemma4 `
  --repeat 5 `
  --output-dir C:\temp\gemma4-roundtrip-repeat
```

Exit code is zero only when every requested run passes the strict exact-history
unary and streaming roundtrip path without blocking protocol defects.

## Triage order

1. Confirm exact artifact provenance and `/models` health.
2. Confirm turn1 actually returns a valid `question` tool call with an ID.
3. Compare exact turn2 unary and streaming.
4. Compare exact with `clean-null` and `clean-empty`.
5. Inspect `usage.completion_tokens`, finish reason and streaming TTFT.
6. Use localization, not intuition, to choose the next subsystem:
   - both unary/stream empty + clean histories fail: session state, generation
     config, or tool-result chat-template re-entry;
   - stream has output but unary is empty: output parser/OpenAI serializer;
   - unary works but stream fails: streamer/stream parser;
   - cleaned history recovers: special-token/history serialization path.
7. After a code change, rerun the same probe against the same artifact lineage and
   preserve the before/after evidence directories.
