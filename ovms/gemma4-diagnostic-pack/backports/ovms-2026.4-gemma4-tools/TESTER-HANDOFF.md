# GEMMAMONSTER Gemma4 OVMS RC1 tester handoff

This is an acceptance session, not a development session. Do not patch the OVMS candidate while running this handoff unless a new source-level defect is proven independently from generation limits or GPU context failures.

## Authority coordinates

- OVMS baseline: `530dc63f816507d18bc14629e8cffeb55e3985e6`
- canonical model_server candidate branch: `integration/gemma4-2026.4-rc1-contiguous`
- **Accepted Gemma4 tool-calling RC1 candidate HEAD:** `0a537f08987a3df4c0254c1614162c06ac20b968`
- Freeze and regression rule: [`RC1-ACCEPTANCE.md`](RC1-ACCEPTANCE.md)
- deployment/backport branch: `fix/gemma4-candidate-local-acceptance`
- portable manifest: `ovms/gemma4-diagnostic-pack/backports/ovms-2026.4-gemma4-tools/manifest.json`

The portable manifest contains one contiguous delta:

```text
530dc63f816507d18bc14629e8cffeb55e3985e6
  ->
0a537f08987a3df4c0254c1614162c06ac20b968
```

`upstream_commits` is intentionally empty. The selected candidate already contains the relevant post-refactor Gemma4 parser state. Do not re-apply the old pre-refactor `721e13d..fd0c86c` lineage.

This SHA is frozen as the accepted Gemma4 tool-calling RC1 baseline. Later tool-stack work starts from `0a537f0` and must prove no regression against the freeze. Main `multiline_write` is bounded (~1–1.5 KB, `max_tokens=2048`); do not use ~4.6 KB write stress as a promotion gate.

## 1. Fresh source checkout

Use a clean OVMS checkout at the exact baseline:

```powershell
git clone https://github.com/openvinotoolkit/model_server.git C:\git\ovms-gemmamonster-acceptance
git -C C:\git\ovms-gemmamonster-acceptance checkout --detach 530dc63f816507d18bc14629e8cffeb55e3985e6
git -C C:\git\ovms-gemmamonster-acceptance status --short
```

The final command must print nothing.

## 2. Apply the portable candidate

From this deployment repository/branch:

```powershell
python .\ovms\gemma4-diagnostic-pack\backports\ovms-2026.4-gemma4-tools\apply_backport.py `
  --model-server C:\git\ovms-gemmamonster-acceptance
```

The parameter is `--model-server`, not `--model-server-path`.

After apply, `git diff --name-only` must show only:

```text
src/llm/io_processing/gemma4/gemma4_tool_parser.cpp
src/llm/io_processing/gemma4/gemma4_tool_parser.hpp
src/llm/io_processing/generation_config_builder.hpp
src/llm/io_processing/output_parser.cpp
```

If legacy `base_output_parser.hpp` or `gemma4_reasoning_parser.*` conflicts appear, stop: the wrong candidate/manifest is being used.

## 3. Build a fresh Windows package

Build from the patched source tree and deploy into a new directory. Do not copy a new `ovms.exe` over an old package and do not reuse a stale server process.

Record:

```text
OVMS_BASE
APPLIED_CANDIDATE
PACKAGE_PATH
ovms.exe SHA256
git diff --name-only
git diff --stat
```

`ovms.exe --version` is supplementary evidence only; it does not prove the working-tree candidate delta.

## 4. Gemma4 functional acceptance

Keep `tool_parser=gemma4`, `reasoning_parser=gemma4` and graph-level `enable_tool_guided_generation=false`.

Required runtime cases:

- `tool_choice=auto`: structured tool call when appropriate, no raw Gemma markup in content;
- `tool_choice=none`: content-only answer, no tool calls;
- `tool_choice=required`: empty assistant prose and structured tool call;
- named `tool_choice`: empty assistant prose and the requested tool name;
- nested objects preserve object structure;
- arrays preserve array structure and scalar types;
- shell quoting/braces/pipes survive as valid JSON arguments;
- streaming exposes both tool name and argument deltas without marker leakage;
- assistant -> tool result -> later assistant tool turn works without prefatory prose.

## 5. Correct hard-generation gate

Hard generation is a **decoded-output semantic gate**, not an exact token-ID gate.

For `required` and named hard choice, the first decoded output must begin immediately with:

```text
<|tool_call>
```

before any prose or reasoning.

Both of these are valid witnesses:

```text
48  -> "<|tool_call>"
```

and a fragmented tokenization such as:

```text
"<", "|", "tool", "_", "call", ">"
```

provided the concatenated decoded bytes begin exactly with `<|tool_call>` and the OpenAI result contains an empty `content` plus structured `tool_calls`.

Token ID `48` remains useful diagnostic evidence because it is Gemma4's atomic tool-start special token, but structured-output grammar constrains the generated text/structure and does not contractually require one particular tokenizer path for that text.

A hard-generation FAIL is instead any of:

- prose/reasoning appears before `<|tool_call>`;
- no tool call is produced;
- named choice selects the wrong tool;
- raw tool markup leaks to visible `content`.

Control: `tool_choice=none` must not begin with `<|tool_call>`.

## 6. Multiline runtime lane versus parser stress lane

Do not use a 4.6 KB model-generated `write_file` body with `max_tokens=2048` as a parser acceptance gate. If generation reaches `finish_reason=length`, the model output is truncated by definition. An empty/incomplete tool argument at that point must be classified as `TRUNCATION`, not as proof that the parser emitted invalid JSON.

For the live Heretic runtime matrix, use a bounded multiline payload that still exercises newlines, quotes, commas, braces and backslashes but is comfortably below the generation ceiling (roughly 1-1.5 KB is sufficient for this lane).

Keep the 4 KB+ adversarial payload as a parser-only/unit stress test or as a separate capacity/stability stress test with its own outcome. Do not synthesize missing JSON closure when generation is truncated.

## 7. CL_OUT_OF_RESOURCES handling

If the GPU reports `CL_OUT_OF_RESOURCES`, stop interpreting all later requests from that server process. The OpenCL context may be unusable and OVMS can remain falsely `AVAILABLE` while every inference returns HTTP 400 until restart.

This is already tracked upstream as `openvinotoolkit/model_server#4469`: permanent `LLMExecutor` wedge after `CL_OUT_OF_RESOURCES` with readiness still reporting healthy. It is separate from Gemma4 tool parser/generation correctness.

After any `CL_OUT_OF_RESOURCES` during acceptance:

1. preserve the failure log;
2. terminate/restart OVMS;
3. verify one tiny tool-free inference succeeds;
4. resume only independent cases;
5. record the GPU failure under runtime stability, not parser correctness.

## 8. Verdict dimensions

Return separate verdicts instead of collapsing unrelated evidence into one word:

```text
GEMMA4_TOOL_STACK: PASS / FAIL / BLOCKED
PARSER_STREAMING: PASS / FAIL / BLOCKED
HARD_GENERATION: PASS / FAIL / BLOCKED
LATER_TURN_AGENT: PASS / FAIL / BLOCKED
MULTILINE_BOUNDED: PASS / FAIL / BLOCKED
GPU_LONG_GENERATION_STABILITY: PASS / FAIL / BLOCKED
OVMS_FATAL_GPU_RECOVERY: PASS / FAIL / BLOCKED
OVERALL_GEMMA4_TOOL_CANDIDATE: PASS / FAIL / BLOCKED
```

A candidate may be accepted for the Gemma4 tool stack while retaining a separate known upstream GPU recovery defect. Do not move the model_server candidate SHA merely to work around `CL_OUT_OF_RESOURCES` unless a source-level regression in the candidate is demonstrated.
