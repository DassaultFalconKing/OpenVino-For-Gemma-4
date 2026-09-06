# Gemma4 Parser/Generator V2 Windows Acceptance

This runbook validates the GEMMAMONSTER Gemma4 tool-calling implementation on the real Windows + Intel Arc host.

## Repositories

Runtime source:

```text
DassaultFalconKing/model_server
branch: main
```

Deployment/diagnostics:

```text
DassaultFalconKing/OpenVino-For-Gemma-4
branch: main
pack: ovms/gemma4-diagnostic-pack
```

Always record the exact resolved SHAs before building. Do not call a moving `main` accepted evidence.

## 1. Update clean checkouts

```powershell
git -C C:\git\model_server-gemma4 fetch --all --prune
git -C C:\git\model_server-gemma4 checkout main
git -C C:\git\model_server-gemma4 pull --ff-only
git -C C:\git\model_server-gemma4 status --short
git -C C:\git\model_server-gemma4 rev-parse HEAD

git -C C:\git\OpenVino-For-Gemma-4 fetch --all --prune
git -C C:\git\OpenVino-For-Gemma-4 checkout main
git -C C:\git\OpenVino-For-Gemma-4 pull --ff-only
git -C C:\git\OpenVino-For-Gemma-4 status --short
git -C C:\git\OpenVino-For-Gemma-4 rev-parse HEAD
```

If either checkout is dirty, stop and preserve the diff before changing anything.

## 2. Build OVMS

Use the existing Windows build environment already proven for this fork:

```powershell
cd C:\git\model_server-gemma4
cmd /c "windows_build.bat opt --with_python --with_tests"
if ($LASTEXITCODE -ne 0) { throw "OVMS build failed: $LASTEXITCODE" }

cmd /c "windows_create_package.bat opt --with_python"
if ($LASTEXITCODE -ne 0) { throw "OVMS package failed: $LASTEXITCODE" }
```

Record:

```powershell
Get-FileHash -Algorithm SHA256 <built-or-packaged-ovms.exe>
& <built-or-packaged-ovms.exe> --version
```

## 3. Parser/generator tests

At minimum run the generation-contract target and the ordinary OVMS unit-test target containing `gemma4_*output_parser_test.cpp`.

Dedicated generation target:

```powershell
bazel --output_user_root=C:\opt test `
  --config=win_mp_on_py_on `
  --action_env OpenVINO_DIR=C:\opt\openvino\runtime\cmake `
  --test_output=all `
  --test_timeout=600 `
  //src/test/llm/generation_config:gemma4_generation_contract_test
```

The output-parser suite is globbed into the regular OVMS test binary through `src/BUILD`. Run the same unit-test command used by the repository's Windows acceptance and confirm these tests execute:

```text
Gemma4V2ContractTest.ParsesOpenCodeQuestionArrayOfObjectsRecursively
Gemma4V2ContractTest.PreservesNestedScalarTypes
Gemma4V2ContractTest.AcceptsParenthesizedArgumentsWhenAnchoredByToolMarker
Gemma4V2ContractTest.AcceptsColonNameVariantWhenAnchoredByToolMarker
Gemma4V2ContractTest.AcceptsDirectCallImmediatelyAfterReasoningEnd
Gemma4V2ContractTest.DoesNotEmitUnknownToolAsExecutableCall
Gemma4V2ContractTest.MalformedCallIsBoundedAndLaterValidCallSurvives
```

Do not treat a test that was not discovered as PASS.

## 4. Start the model with canonical template

Example for the current Wondernutts model:

```powershell
$Pack = "C:\git\OpenVino-For-Gemma-4\ovms\gemma4-diagnostic-pack"
$Model = "C:\llm\models\OpenVINO\Wondernutts\gemma-4-26B-A4B-it-qat-q4_0-unquantized-uncensored-heretic-int4-ov"

& "$Pack\launch.ps1" `
  -OvmsExe C:\llm\ovms\ovms.exe `
  -ModelPath $Model `
  -ModelName gemma4-26-heretic `
  -Profile vlm-stable `
  -RestPort 9090 `
  -ChatTemplateMode JINJA `
  -MaxTokensLimit 65536
```

On first canonical-template implant the launcher should:

- fetch Google `google/gemma-4-12B-it` template at revision `711c1368e39f1712f48ff0eb7bcdbbb760d52db0`;
- validate Gemma4 markers;
- back up a differing existing template;
- write `.gemmamonster-chat-template.json` with installed SHA-256.

On subsequent launches the revision+SHA fast path should avoid network access.

For deliberate old/custom-template comparison only:

```powershell
-SkipCanonicalTemplate
```

## 5. Endpoint smoke

The graph-backed endpoint is `/v3/chat/completions`.

```powershell
python "$Pack\smoke_test.py" `
  --base-url http://127.0.0.1:9090/v3 `
  --model gemma4-26-heretic
```

A `/v1/chat/completions` request is not the diagnostic-pack graph endpoint and must not be used as evidence for this profile.

## 6. Full tool-call matrix

One command runs tokenizer diagnostics plus the runtime matrix and writes raw evidence:

```powershell
& "$Pack\run-toolcall-acceptance.ps1" `
  -BaseUrl http://127.0.0.1:9090/v3 `
  -Model gemma4-26-heretic `
  -ModelPath $Model `
  -Mode all
```

The matrix covers:

- none;
- auto optional no-call;
- auto expected call;
- required;
- named;
- OpenCode-like `question` schema in auto/required/named;
- parallel multi-call;
- streaming question call;
- tool-result roundtrip and post-tool recovery.

It fails on observed `<unusedNN>`, `<pad>` or isolated `multimodal` garbage and stores exact request/response/SSE evidence under `runtime/acceptance/<timestamp>`.

Focused reproduction of the original failure:

```powershell
& "$Pack\run-toolcall-acceptance.ps1" `
  -BaseUrl http://127.0.0.1:9090/v3 `
  -Model gemma4-26-heretic `
  -ModelPath $Model `
  -Mode question
```

## 7. Real OpenCode dogfood

Only after raw HTTP acceptance, configure OpenCode to the same `/v3` base and exact model name.

Minimum conversation:

```text
какие инструменты есть у тебя?

derни question, задай мне один тестовый вопрос

скажи еще что-нибудь
```

Acceptance:

- `question` is actually invoked rather than explained;
- OpenCode receives valid question arguments;
- no reserved-token garbage appears;
- after the tool result the model continues normal conversation;
- raw OVMS boundary evidence is retained if OpenCode disagrees with direct HTTP behavior.

## 8. Failure classification

Classify the first wrong boundary, not the last visible symptom:

```text
G = generator / structural-output policy
T = template / rendered prompt
M = raw model generation
P = parser
W = repository wiring/provider path
```

Examples:

- raw OVMS response already contains `<unused45>` -> G/T/M investigation, not parser-only;
- raw OVMS has canonical tool syntax but OpenAI `tool_calls` is absent -> P/W;
- direct HTTP passes but OpenCode displays garbage -> provider/client boundary;
- `/v1/chat/completions` gives graph-not-found while `/v3/chat/completions` works -> wrong endpoint, not model failure.

## Required report

```text
RUNTIME_HEAD:
HELPER_HEAD:
OVMS_VERSION:
OVMS_BINARY_SHA256:
TEMPLATE_REVISION:
TEMPLATE_SHA256:
BUILD:
GENERATOR_TESTS:
PARSER_TESTS:
SMOKE_V3:
TOKENIZER_MARKERS:
AUTO:
REQUIRED:
NAMED:
QUESTION_AUTO:
QUESTION_REQUIRED:
QUESTION_NAMED:
PARALLEL:
STREAMING:
ROUNDTRIP:
RESERVED_TOKEN_GARBAGE:
REAL_OPENCODE:
POST_TOOL_RECOVERY:
OVERALL:
EVIDENCE_DIRECTORY:
```

`OVERALL=PASS` is forbidden if build/test discovery was skipped or if the real OpenCode question/recovery sequence was not exercised.
