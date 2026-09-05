# Install patched OVMS 2026.4 for Gemma4 tool calling (Windows)

This procedure builds a **self-contained** OVMS runtime at `C:\llm\ovms-gemma4-patched` (or another `-DeployTo` directory) with both Gemma4 output parsing and hard request-level tool choice.

The C++ changes are compiled into OVMS. A prebuilt `ovms.exe` cannot be patched in place.

## Pinned inputs

| Item | Value |
|---|---|
| OVMS source baseline | `530dc63f816507d18bc14629e8cffeb55e3985e6` (2026.4 RC1) |
| Accepted tool-calling candidate | `0a537f08987a3df4c0254c1614162c06ac20b968` ([RC1-ACCEPTANCE.md](backports/ovms-2026.4-gemma4-tools/RC1-ACCEPTANCE.md)) |
| Upstream parser fixes | `503ff866…`, `95628b45…` |
| Local generation overlay | `Gemma4GenerationConfigBuilder` + factory/BUILD wiring + guided-JSON parser fast path |
| Deployed runtime | `C:\llm\ovms-gemma4-patched` |
| Parser tests | `Gemma4OutputParserTest.*`, including guided JSON regression |
| Runtime smoke | `auto`, `tool_choice=required`, conflicting named `get_weather` |

## Hard rules

1. **Do not** `git reset --hard` in a correctly patched OVMS checkout. The patcher itself performs a rollback only if application fails.
2. **Do not** apply the backport twice. `-SkipApply` is valid only when the **complete** parser + generation overlay is already present. `build-windows.ps1` now verifies this and rejects an older parser-only tree.
3. **Do not** create commits or push from `C:\git\model_server-gemma4` unless an OVMS PR is explicitly being prepared from a separate worktree.
4. **Do not** copy only `ovms.exe`. Deploy the full package with matching OpenVINO/GenAI/tokenizer DLLs and bundled Python.
5. **Do not** skip `Gemma4OutputParserTest.*` for acceptance.
6. Keep graph-level `enable_tool_guided_generation` **off** in the diagnostic `vlm-stable` baseline. Healthy `auto` remains unconstrained.
7. `tool_choice=required` and named function choice are now explicit acceptance criteria for the rebuilt runtime.

## What the patcher applies

`apply-backport.ps1` requires a clean source tree at the pinned baseline and then:

1. applies the two upstream Gemma4 parser commits with `git cherry-pick --no-commit`;
2. invokes `apply-gemma4-generation-config.ps1`;
3. copies `Gemma4GenerationConfigBuilder` into `src/llm/io_processing/gemma4/`;
4. wires `toolParserName == "gemma4"` into the generation-config factory;
5. adds the builder to `src/llm/BUILD`;
6. adds a dual-dialect parser path: complete valid guided JSON is accepted directly, otherwise native `<|"|>` parsing remains the fallback;
7. injects a guided-JSON `Gemma4OutputParserTest` with nested data and Windows path arrays;
8. unstages everything, leaving ordinary local source changes and no Git commit.

Generator policy:

- no tools -> base config;
- `none` -> no tool structural config;
- `auto` + graph guided=false -> existing unconstrained path;
- `auto` + graph guided=true -> `TriggeredTags`;
- `required` -> top-level `TagsWithSeparator(..., at_least_one=true)`;
- named function -> the same hard grammar after OVMS filters the tool map to the selected function.

## Prerequisites

- Windows 10/11 x64 and enough free space for OVMS/Bazel/OpenCV;
- Git and curl;
- Visual Studio 2022 Build Tools with Desktop C++;
- MSVC v143 x64, Windows SDK, CMake tools;
- MSVC v142 (`14.29.x`) for the pinned OpenCV configure path;
- Intel Arc GPU and driver for the target GPU deployment;
- the Gemma4 OpenVINO model directory.

The wrapper searches:

```text
C:\Program Files\Microsoft Visual Studio\2022\BuildTools
C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools
C:\BuildTools
```

Use `-VisualStudioPath` for another location.

## 1. Clone helper and OVMS source

```powershell
git clone https://github.com/DassaultFalconKing/OpenVino-For-Gemma-4.git
cd OpenVino-For-Gemma-4

git clone https://github.com/openvinotoolkit/model_server.git C:\git\model_server-gemma4
git -C C:\git\model_server-gemma4 checkout 530dc63f816507d18bc14629e8cffeb55e3985e6
git -C C:\git\model_server-gemma4 status --short
git -C C:\git\model_server-gemma4 rev-parse HEAD
```

Before first apply, status must be empty and HEAD must equal the pinned SHA.

## 2. Build and deploy

From:

```text
ovms\gemma4-diagnostic-pack\backports\ovms-2026.4-gemma4-tools
```

run:

```powershell
.\build-windows.ps1 `
  -ModelServerPath C:\git\model_server-gemma4 `
  -DependenciesRoot opt `
  -InstallDependencies `
  -DeployTo C:\llm\ovms-gemma4-patched
```

If `C:\opt` already contains the matching dependencies, omit `-InstallDependencies`.

For a source tree on which this **complete** backport was already applied:

```powershell
.\build-windows.ps1 `
  -ModelServerPath C:\git\model_server-gemma4 `
  -DependenciesRoot opt `
  -SkipApply `
  -DeployTo C:\llm\ovms-gemma4-patched
```

`-SkipApply` does not bypass validation: the wrapper checks builder files, factory wiring, Bazel wiring and `guidedArgsDoc` parser support before compiling.

The build wrapper also:

- detects the real `cl.exe` and MSVC toolset;
- temporarily patches Intel's hard-coded Visual Studio paths and restores the original bytes in `finally`;
- avoids OpenCV's broken Python detection with `OPENCV_PYTHON_SKIP_DETECTION=ON`;
- creates `C:\opt\Python312\python3.exe` so Bazel does not mix Python 3.14 with `PYTHONHOME` 3.12;
- checks `win_build.log` for Bazel failure hidden by `| tee`;
- builds with `--with_python --with_tests`;
- runs `Gemma4OutputParserTest.*` unless `-SkipParserTests` is explicitly supplied;
- packages and deploys the complete runtime.

## 3. Launch

```powershell
$runtime = "C:\llm\ovms-gemma4-patched"
$env:PYTHONHOME = Join-Path $runtime "python"
$env:PATH = "$runtime;$env:PYTHONHOME;$env:PYTHONHOME\Scripts;" + $env:PATH

cd <this-repo>\ovms\gemma4-diagnostic-pack
.\launch.ps1 `
  -OvmsExe "$runtime\ovms.exe" `
  -ModelPath "C:\llm\models\OpenVINO\Wondernutts\gemma-4-26B-A4B-it-qat-q4_0-unquantized-uncensored-heretic-int4-ov" `
  -ModelName gemma4-26-heretic `
  -Profile vlm-stable `
  -RestPort 8000 `
  -ChatTemplateMode JINJA
```

The diagnostic baseline deliberately does not enable graph-level guided generation. Request-level hard choice is enforced by the Gemma4 builder itself.

## 4. Runtime smoke

Run the complete three-case suite:

```powershell
python .\backports\ovms-2026.4-gemma4-tools\smoke_tool_call.py `
  --base-url http://127.0.0.1:8000 `
  --model gemma4-26-heretic `
  --mode all
```

It verifies:

1. `auto` still emits structured `get_weather`;
2. `tool_choice=required` emits a tool call with no preceding prose;
3. a deliberately conflicting named `get_weather` choice is enforced instead of letting the model answer the arithmetic prompt directly.

Expected final line:

```text
PASS: Gemma4 auto + hard tool-choice smoke suite
```

For isolated diagnosis use `--mode auto`, `--mode required`, or `--mode named`.

## 5. Final hard-choice acceptance

The REST smoke is necessary but not sufficient. Capture OVMS TRACE/token output and verify that hard choice starts with token `48` (`<|tool_call>`) as the first generated token. Then rerun the full 17-case probe and NovaClaw later-turn scenario.

Acceptance requires:

- no regression in the existing auto matrix;
- `none` remains tool-free;
- `required` has no textual promise before the call;
- named choice is actually forced;
- native `<|"|>` and guided JSON arguments both parse into valid OpenAI `arguments`;
- nested objects and arrays retain their types;
- streaming remains structured and leak-free;
- TRACE proves token 48 first for hard choice.

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| `-SkipApply` rejected | source has only old parser patch or partial builder wiring | use a clean pinned checkout and apply the complete backport |
| PowerShell aborts on curl progress | native stderr under `$ErrorActionPreference=Stop` | wrapper uses `Invoke-NativeProcess` |
| OpenCV `find_package(Python3 "OFF")` | pinned OpenCV detection bug | wrapper uses `OPENCV_PYTHON_SKIP_DETECTION=ON` |
| Bazel `SRE module mismatch` | PATH `python3` does not match `PYTHONHOME` | wrapper supplies Python 3.12 `python3.exe` |
| batch exits 0 but no `ovms.exe` | Bazel exit hidden by `tee` | inspect `win_build.log`; wrapper checks `FAILED:` |
| `config.json` invalid | UTF-8 BOM | `launch.ps1` writes UTF-8 without BOM |
| hard choice returns prose | builder not active or grammar validation fell back | inspect factory wiring and OVMS structured-output logs/TRACE |
| guided call has malformed arguments | parser fast path missing or structured config mismatch | require `guidedArgsDoc` path and run `Gemma4OutputParserTest.*` |

Logs: `C:\git\model_server-gemma4\win_build.log`, `win_environment.log`.

## Agent handoff

Agents must follow this file and repository `AGENTS.md`. A recommendations-only response is not an installation result. Report exact helper HEAD, OVMS HEAD/status, build/test output, deployed runtime version, smoke output, and TRACE result as `PASS` or `BLOCKED`.
