# OVMS 2026.4 RC1 Gemma4 tool-call + hard-choice backport

This backport targets the Windows OVMS **source checkout** at exact baseline:

`530dc63f816507d18bc14629e8cffeb55e3985e6`

`apply-backport.ps1` now applies one complete Gemma4 tool-calling stack:

1. `503ff866278e9236d08bc9b6ddd18ec879660f72` — upstream tool-parser finalization fixes, including Gemma4.
2. `95628b45a082bd3d9562a3ad2f3d0762d5883ca4` — upstream `Gemma4 parsing fixes (#4508)`.
3. the local `Gemma4GenerationConfigBuilder` overlay;
4. factory + Bazel `generation_config_builders` wiring;
5. a dual-dialect parser fast path for standard JSON arguments produced by guided generation;
6. a `Gemma4OutputParserTest` regression covering guided JSON with nested values and Windows path arrays.

The apply step creates **no Git commit**. It leaves one ordinary locally modified OVMS tree that can be built and packaged by `build-windows.ps1`.

## Generation policy

The builder deliberately preserves the live behavior that already works:

| Request mode | Behavior |
|---|---|
| no tools | base config only |
| `tool_choice=none` | no tool structural output, even if graph guided generation is enabled |
| `auto`, guided=false | existing unconstrained Gemma4 path |
| `auto`, guided=true | `TriggeredTags` after `<|tool_call>` |
| `required` | top-level `TagsWithSeparator(tags, "", at_least_one=true)` |
| named function | same hard top-level grammar; OVMS has already filtered the tool map to the named function |

`required` and named choice do **not** use `TriggeredTags`. Triggered generation only takes control after the model emits `<|tool_call>` itself, which still permits textual promises such as `сейчас запущу` before the tool call. The hard path constrains generation from grammar start.

The diagnostic `vlm-stable` graph still keeps graph-level `enable_tool_guided_generation` off by default. Request-level `required` and named choice are the first acceptance targets; healthy `auto` is kept as the control path.

## Dual argument dialects

Unconstrained Gemma4 commonly emits native arguments such as:

```text
<|tool_call>call:get_weather{city:<|"|>Berlin<|"|>}<tool_call|>
```

The hard builder uses OpenVINO GenAI `JSONSchema`, so guided output uses ordinary JSON:

```text
<|tool_call>call:get_weather{"city":"Berlin"}<tool_call|>
```

The patched parser accepts both. A complete valid JSON object is parsed and serialized canonically first; if that fails, the existing native Gemma4 `<|"|>` parser remains the fallback. This also prevents guided arrays such as Windows path lists from being converted into JSON strings.

Historical XGrammar PR #588 is useful for tag-boundary history, but it is not current Gemma4 grammar support. Current XGrammar later disabled Gemma4 registration because the native parameter dialect is not ordinary JSON.

## Important path distinction

There are two completely separate locations:

- `-ModelServerPath` points to an OVMS **source checkout** used only to apply the C++ patch and build.
- `-DeployTo` points to the directory where you actually want to run the patched OVMS package.

A prebuilt `ovms.exe` cannot be source-patched in place. The source checkout is required for rebuilding but does not become the runtime directory.

## Apply and build on Windows

Use a clean checkout at the pinned baseline:

```powershell
git clone https://github.com/openvinotoolkit/model_server.git C:\git\model_server-gemma4
git -C C:\git\model_server-gemma4 checkout 530dc63f816507d18bc14629e8cffeb55e3985e6
```

Or verify an existing checkout before reuse:

```powershell
git -C C:\git\model_server-gemma4 status --short
git -C C:\git\model_server-gemma4 rev-parse HEAD
```

The second command must print the pinned SHA and the first must be empty before applying.

Build and deploy a complete package:

```powershell
.\build-windows.ps1 `
  -ModelServerPath C:\git\model_server-gemma4 `
  -DependenciesRoot opt `
  -InstallDependencies `
  -DeployTo C:\llm\ovms-gemma4-patched
```

If dependencies already exist under `C:\opt`, omit `-InstallDependencies`.

If this **complete** backport was already applied to the source checkout, use `-SkipApply`. `build-windows.ps1` now validates builder files, factory wiring, Bazel wiring, and the guided-JSON parser fast path even when `-SkipApply` is used. A parser-only older checkout is rejected instead of silently building the wrong runtime.

The wrapper supports Visual Studio 2022 Build Tools under either Program Files root or `C:\BuildTools`. A non-standard location can be supplied with `-VisualStudioPath`.

The build uses `--with_python` for JINJA and `--with_tests`. Unless `-SkipParserTests` is supplied, the complete `Gemma4OutputParserTest.*` suite runs, including the locally injected guided-JSON regression.

`windows_create_package.bat` then creates the matching self-contained runtime under:

```text
<ModelServerPath>\dist\windows\ovms
```

Do not copy only `ovms.exe` over another unpacked runtime. The matching OpenVINO/GenAI/tokenizer DLLs and embedded Python belong to the package too. Apparently ABI skew was not exciting enough the first time.

## Replacing an existing runtime

Stop OVMS first. Then use `-ForceDeploy`:

```powershell
.\build-windows.ps1 `
  -ModelServerPath C:\git\model_server-gemma4 `
  -DependenciesRoot opt `
  -SkipApply `
  -DeployTo C:\llm\ovms `
  -ForceDeploy
```

The old runtime is renamed to a timestamped backup before the new package is copied.

## Runtime acceptance

First rerun the ordinary auto smoke test:

```powershell
python .\smoke_tool_call.py `
  --base-url http://127.0.0.1:8000 `
  --model gemma4-26-heretic
```

Then rerun the full 17-case probe and explicitly cover hard-choice behavior.

Acceptance requires:

- the existing `auto` matrix does not regress;
- `tool_choice=none` stays content-only;
- `tool_choice=required` produces structured `message.tool_calls` without preceding prose;
- conflicting named `get_weather` choice emits `get_weather` instead of answering the conflicting prompt directly;
- guided JSON arguments stay valid JSON with correct nested/array types;
- native `<|"|>` calls still parse correctly;
- streaming remains `delta.tool_calls` + `finish_reason=tool_calls` with no raw markup leak;
- TRACE/token capture shows token `48` (`<|tool_call>`) as the first generated token for hard choice.

The last item is the decisive proof that top-level `TagsWithSeparator` is actually constraining from token zero. Compilation is necessary, not clairvoyance.
