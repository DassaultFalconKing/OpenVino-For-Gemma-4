# Frozen Gemma4 tool-calling RC1 baseline

Date: 2026-09-05.

`0a537f08987a3df4c0254c1614162c06ac20b968` is the **accepted Gemma4 tool-calling RC1 baseline**.

Do not reopen this SHA as an unproven candidate. Later tool-stack work must land **on top of** this commit and prove **no regression** against the acceptance below. Reconstruction from `530dc63f` remains `git diff 0a537f0 -- src/llm src/test` (empty).

## Exact identities

| Item | Value |
| --- | --- |
| Source base | `530dc63f816507d18bc14629e8cffeb55e3985e6` |
| Accepted candidate | `0a537f08987a3df4c0254c1614162c06ac20b968` (`integration/gemma4-2026.4-rc1-contiguous`) |
| Runtime binary | `C:\llm\ovms-gemma4-candidate\ovms.exe` |
| Binary SHA256 | `A9DEB1FD68040298CEE03B80353D25CCF604AC5E725AD5B538C1A0B3A0A4B148` |
| Pack branch at freeze | `fix/gemma4-candidate-local-acceptance` |

This freeze does **not** patch or rebuild `0a537f0`. Parser gtest `Gemma4OutputParserTest` was 39/39 PASS before runtime probes.

## Split verdict

```text
GEMMA4_TOOL_STACK: PASS
PARSER_STREAMING: PASS
HARD_GENERATION: PASS
LATER_TURN_AGENT: PASS

MULTILINE_BOUNDED: PASS

GPU_LONG_GENERATION_STABILITY: FAIL
OVMS_FATAL_GPU_RECOVERY: FAIL / upstream #4469

OVERALL_GEMMA4_TOOL_CANDIDATE:
PASS, subject to bounded multiline witness
```

## What main acceptance must keep proving

Relative to this baseline, a later tool-stack delta is a regression if it loses any of:

- smoke `auto` / `required` / `named` structured `get_weather` with no raw markup in `message.content`;
- `required` and named hard choice: empty `content`, `message.tool_calls` present, no `HARD_CHOICE_PROSE`, no `TOOL_CHOICE_NOT_ENFORCED`;
- `tool_choice=none` content-only (no tool call);
- matrix cases other than unbounded write stress: nested object, arrays, shell quoting, parallel calls, streaming `delta.tool_calls`, roundtrip after tool;
- TRACE: `required` and named `get_weather` first generated token id `48` (`<|tool_call>`); `none` first token is not `48`;
- NovaClaw later-turn: second assistant event is `read_file` with empty content (no promise prose);
- **bounded** `multiline_write`: ~1–1.5 KB body, `max_tokens=2048`, structured `write_file`, non-empty valid JSON arguments, `finish_reason=tool_calls`.

Do **not** put the old ~4.6 KB / 2048-token write stress in the main acceptance gate. That path is GPU long-generation stability, already **FAIL** here (`finish_reason=length`, then `CL_OUT_OF_RESOURCES` / HTTP 400, OVMS does not recover; upstream #4469).

## Runtime evidence (2026-09-05, Arc 140V)

- Smoke 3/3 PASS (`smoke_tool_call.py --mode all`).
- Matrix 9/10 PASS; unbounded `multiline_write` FAIL `ARGUMENTS_INVALID_JSON` + `TRUNCATION` at 2048 tokens (empty content, `write_file` name present, first token 48 — not a hard-choice prose miss).
- Bounded rerun after a fresh restart: 1200-byte body, `write_file`, valid JSON `{path, content}`, `finish_reason=tool_calls` (`C:\llm\gemma4-multiline-bounded-rc1.json`).
- Streaming: matrix `streaming_weather` PASS (no `PARSER_MARKUP_LEAK` / `STREAMING_STRUCTURE_LOSS`).
- NovaClaw later-turn PASS after the GPU-wedge restart.
- Named smoke reconstructed `<|tool_call>` from sub-tokens (`236820…`) once; `required` and matrix named started at atomic token `48`. Token id 48 is diagnostic only; decoded output beginning with `<|tool_call>` (atomic or fragmented) is `HARD_GENERATION: PASS`.

## Regression rule

New parser, grammar, streaming, or hard-choice changes:

1. start from accepted `0a537f0` (or an already-accepted descendant);
2. keep identities exact (SHA / binary hash / tested HEAD);
3. rerun smoke `--mode all`, the bounded matrix (not 4.6 KB write stress), TRACE first-token gate, streaming, and later-turn;
4. do not weaken, skip, or xfail those gates to promote the delta.
