# GEMMAMONSTER Gemma4 portable OVMS tester handoff

This is an acceptance session, not a development session. Build a fresh OVMS source tree from the pinned baseline, apply the portable stack, run parser tests, then exercise the real Heretic model through the OpenAI-compatible API.

## Authority coordinates

- OVMS baseline: `530dc63f816507d18bc14629e8cffeb55e3985e6`
- upstream parser fixes: `503ff866278e9236d08bc9b6ddd18ec879660f72`, `95628b45a082bd3d9562a3ad2f3d0762d5883ca4`
- published streaming-hardening range: `6f5b48ece2078e32268b87402cc206e8b2772da8..721e13d12c0fd4820ccc4bd06a866963c6524da5`
- runtime-proven candidate range: `721e13d12c0fd4820ccc4bd06a866963c6524da5..fd0c86c77ce6812fd6c77d9c8ee16a7dd7cb973b`
- canonical model_server integration branch: `integration/gemmamonster-gemma4-portable-tools`
- deployment branch: `feature/gemmamonster-portable-gemma4-stack`

The experimental `hardening/gemma4-heretic-parser-streaming @ 3bbc47949eb35fe70cfd098d52dc62c306774396` is research evidence only. Do not apply its synthetic truncated-call closure logic in this acceptance run.

## 1. Fresh source checkout

Windows example:

```powershell
git clone https://github.com/openvinotoolkit/model_server.git C:\git\ovms-gemmamonster-acceptance
git -C C:\git\ovms-gemmamonster-acceptance checkout 530dc63f816507d18bc14629e8cffeb55e3985e6
git -C C:\git\ovms-gemmamonster-acceptance status --short
```

The final command must print nothing.

Do not reuse the old locally repaired worktree. The point of this run is reproducibility.

## 2. Apply the portable stack

From this deployment repository/branch:

```powershell
python .\ovms\gemma4-diagnostic-pack\backports\ovms-2026.4-gemma4-tools\apply_backport.py `
  --model-server C:\git\ovms-gemmamonster-acceptance
```

Expected characteristics:

- source checkout remains at the pinned baseline commit;
- parser/generator changes are ordinary unstaged source changes;
- no Windows build paths are written by the portable applier;
- `src/llm/io_processing/gemma4/generation_config_builder.cpp` exists;
- factory and Bazel wiring exist;
- parser contains reasoning→tool handling, structural holdback, recursive native values and guided JSON support on both streaming and unary paths.

If apply fails, stop and return the complete command output. Do not hand-edit the source tree to make the test continue.

## 3. Build a complete Windows package

The Windows build adapter is allowed to contain Windows-specific toolchain workarounds. Those are build policy, not parser/generation business logic.

On a fresh baseline you may let the wrapper call the portable applier itself:

```powershell
.\ovms\gemma4-diagnostic-pack\backports\ovms-2026.4-gemma4-tools\build-windows.ps1 `
  -ModelServerPath C:\git\ovms-gemmamonster-acceptance `
  -DependenciesRoot opt `
  -DeployTo C:\llm\ovms-gemmamonster-acceptance
```

If you already ran `apply_backport.py` in step 2, add `-SkipApply`.

Use `-InstallDependencies` only if that checkout does not already have the required OVMS Windows dependencies.

Acceptance requires the full package, not a copied `ovms.exe` over an older directory.

## 4. Parser regression gate

After build and model preparation, run explicitly:

```powershell
C:\git\ovms-gemmamonster-acceptance\bazel-bin\src\ovms_test.exe `
  --gtest_filter="Gemma4OutputParserTest.*:Gemma4StreamingHardeningTest.*:*Gemma4MarkerSplitTest*"
```

Record exact test count and exit code. Required: zero failures.

Particularly inspect failures involving:

- every byte split of `<|tool_call>`, `<tool_call|>`, `<channel|>`, `<turn|>`, `<|tool_response>`;
- reasoning→tool without `<channel|>`;
- nested object and arrays;
- Windows-style path escaping;
- 4KB multiline arguments;
- two consecutive tool calls;
- guided JSON in streaming and unary parsing;
- finish during a partial structural token without inventing a tool call.

## 5. Launch the real model

Use the packaged/deployed OVMS from this run and the normal `vlm-stable` graph.

Model used by the previous acceptance:

```text
gemma4-26-heretic
```

Keep graph-level `enable_tool_guided_generation` OFF. Request-level `required` and named choice are the hard-generation acceptance path.

For token evidence, capture a second run with OVMS TRACE and verbose response logging enabled.

## 6. Fast smoke

```powershell
python .\ovms\gemma4-diagnostic-pack\backports\ovms-2026.4-gemma4-tools\smoke_tool_call.py `
  --base-url http://127.0.0.1:8000 `
  --model gemma4-26-heretic `
  --mode all
```

Required:

- `auto` returns structured `tool_calls`;
- `required` returns a tool call with empty assistant prose;
- named conflicting choice actually calls the named tool;
- no raw Gemma tool markup reaches `content`.

Also verify `tool_choice=none` through the matrix below.

## 7. Adversarial runtime matrix

```powershell
python .\ovms\gemma4-diagnostic-pack\backports\ovms-2026.4-gemma4-tools\toolcall_matrix.py `
  --base-url http://127.0.0.1:8000 `
  --model gemma4-26-heretic `
  --output C:\llm\gemma4-toolcall-matrix.json
```

The matrix covers:

- `tool_choice_none`;
- `tool_choice_required`;
- `tool_choice_named_conflict`;
- nested object arguments;
- arrays of strings and path escaping;
- long multiline `write_file` payload;
- shell quoting/pipes/braces;
- parallel calls;
- streaming tool-call assembly;
- assistant→tool→assistant roundtrip.

A `WARN` is model-quality evidence, not automatically a parser failure. Example: named tool is correctly enforced but the model chooses a silly semantically valid argument. A `FAIL` is structural/runtime evidence.

### Issue taxonomy

- `PARSER_MARKUP_LEAK`: structural token leaked into OpenAI content.
- `HARD_CHOICE_PROSE`: required/named emitted prose before the tool call.
- `TOOL_CHOICE_NOT_ENFORCED`: hard choice produced no tool call.
- `WRONG_TOOL_NAME`: named choice did not select the requested tool.
- `TOOL_NAME_MISSING`: tool event exists but function name was lost.
- `ARGUMENTS_INVALID_JSON`: parser emitted malformed JSON argument text.
- `ARGUMENT_TYPE_DRIFT`: object/array became a string or otherwise changed JSON type.
- `STREAMING_STRUCTURE_LOSS`: streaming never exposed both tool identity and argument data.
- `ROUNDTRIP_RECALL`: model called the tool again after its result instead of continuing.
- `MODEL_ARGUMENT_QUALITY`: protocol is valid but model selected a poor argument value.
- `MODEL_PARALLEL_CALL_QUALITY`: protocol is valid but the model did not produce both requested calls.

## 8. TRACE hard-choice gate

For each of these requests capture the generated token sequence:

1. `tool_choice="required"`
2. named `tool_choice={"type":"function","function":{"name":"get_weather"}}`

Required first generated token:

```text
48  ==  <|tool_call>
```

Control witness:

```text
tool_choice="none" must not start with token 48
```

If required/named begins with prose/reasoning and only later reaches token 48, hard generation is a FAIL even if a later parser event looks correct.

## 9. Later-turn agent witness

Run at least one conversation shaped like:

```text
user -> assistant tool call -> tool result -> assistant -> user asks for another action -> required/named tool call
```

Required on the second tool turn:

- empty assistant prose;
- structured tool event immediately;
- correct function name;
- valid JSON arguments;
- no repeated old tool;
- TRACE begins with token 48.

This is the NovaClaw-style witness. First-turn-only success is not sufficient.

## 10. Return report

Return exactly these coordinates and outcomes:

```text
GEMMAMONSTER GEMMA4 PORTABLE ACCEPTANCE

DEPLOY_BRANCH_HEAD:
OVMS_BASE:
APPLIED_CANDIDATE:
BUILD:
PACKAGE_PATH:

PARSER_GTEST_COUNT:
PARSER_GTEST_RESULT:

SMOKE_AUTO:
SMOKE_NONE:
SMOKE_REQUIRED:
SMOKE_NAMED:

MATRIX_PASS:
MATRIX_WARN:
MATRIX_FAIL:
MATRIX_REPORT_PATH:

TRACE_REQUIRED_FIRST_TOKEN:
TRACE_NAMED_FIRST_TOKEN:
TRACE_NONE_FIRST_TOKEN:

LATER_TURN:

TYPICAL_PROBLEMS:
- case:
  classification:
  request:
  actual:
  expected:
  relevant log:

VERDICT:
PASS / FAIL / BLOCKED
```

Do not call the candidate PASS when only compilation succeeded. Build, parser tests, runtime matrix and hard-choice token evidence are separate gates.
