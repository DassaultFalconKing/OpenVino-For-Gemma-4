# Gemma4GenerationConfigBuilder overlay

Status: **integrated by `apply-backport.ps1`** through `apply-gemma4-generation-config.ps1`. The source files still live in this folder so the local delta remains inspectable and portable. Diagnostic `vlm-stable` still keeps graph-level guided generation off by default.

This version is intentionally different from the original Hermes3-style draft: live probing showed that Gemma4 `auto` tool calling is already healthy, while `required`/named choice need a stronger decode constraint than `TriggeredTags` can provide.

| File | Role |
|---|---|
| [PROMPT.md](PROMPT.md) | Implementation/acceptance handoff |
| [overlay/src/llm/io_processing/gemma4/generation_config_builder.hpp](overlay/src/llm/io_processing/gemma4/generation_config_builder.hpp) | Class and mode policy |
| [overlay/src/llm/io_processing/gemma4/generation_config_builder.cpp](overlay/src/llm/io_processing/gemma4/generation_config_builder.cpp) | Hard + auto structured-output mapping |
| [overlay/src/llm/io_processing/generation_config_builder.hpp.snippet](overlay/src/llm/io_processing/generation_config_builder.hpp.snippet) | Factory reference |
| [overlay/src/llm/BUILD.snippet](overlay/src/llm/BUILD.snippet) | Bazel reference |

## Evidence that drives the design

Live Windows GPU probe against `gemma4-26-heretic` on 2026-09-05 ran 17 sequential OpenAI chat cases. Fourteen returned structured `message.tool_calls`; the remaining prose cases were `tool_choice=none`, a deliberately conflicting named-tool request, and the post-tool round trip. There were zero raw `<|tool_call>` leaks in `content`.

Important observations:

- ordinary `tool_choice=auto` is already reliable, including nested objects, parallel calls, Cyrillic, streaming and agent-style tools;
- first-turn Russian `tool_choice=required` happened to work unconstrained, so the NovaClaw failure is not a basic parser failure;
- named `tool_choice={type:function,...}` is **not enforced** by the unpatched runtime;
- the native parser can produce a wrong JSON type for some Windows-path arrays.

The generator therefore does not globally constrain auto mode.

## Generator policy

| Request mode | Generator behavior |
|---|---|
| no tools | base config only |
| `tool_choice=none` | base config only, even if graph guided generation is enabled |
| `auto`, guided=false | **unconstrained**; current parser/native model path is preserved |
| `auto`, guided=true | `TriggeredTags`; free-form text is allowed until `<|tool_call>` appears, then the call body is constrained |
| `required` | top-level `TagsWithSeparator(tags, "", at_least_one=true)` |
| named function | same hard top-level grammar; OVMS already filters `toolNameSchemaMap` to the named function |

The hard path deliberately does **not** use `TriggeredTags`. A trigger grammar cannot prevent the model from saying `сейчас запущу...` before it emits `<|tool_call>`. A top-level tag sequence begins constrained generation at a tool tag and is the candidate mechanism for making token 48 (`<|tool_call>`) the first generated token.

## Wire formats

The builder uses `JSONSchema` for tag content, so guided calls have standard JSON arguments:

```text
<|tool_call>call:get_weather{"city":"Berlin"}<tool_call|>
```

The local checkpoint normally emits Gemma4's native argument dialect:

```text
<|tool_call>call:get_weather{city:<|"|>Berlin<|"|>}<tool_call|><|tool_response>
```

`apply-gemma4-generation-config.ps1` patches `Gemma4ToolParser` with a dual-dialect fast path: complete valid JSON objects are accepted directly and serialized canonically; invalid-as-JSON content falls back to the existing native `<|"|>` parser. The patcher also injects a `Gemma4OutputParserTest` covering guided JSON, nested values and Windows path arrays.

Historical XGrammar PR #588 briefly implemented the standard-JSON structural tag form. Do not treat that PR as current Gemma4 support; current XGrammar later disabled Gemma4 registration because native string arguments use `<|"|>` instead of ordinary JSON quotes.

## How it is applied

From a clean pinned OVMS source checkout, run the normal wrapper:

```powershell
.\apply-backport.ps1 -ModelServerPath C:\git\model_server-gemma4
```

The wrapper:

1. applies the two pinned upstream Gemma4 parser commits with `git cherry-pick --no-commit`;
2. copies this builder into `src/llm/io_processing/gemma4/`;
3. wires the builder into the factory and `src/llm/BUILD`;
4. adds dual-dialect parser support and its regression test;
5. unstages the combined result, leaving no Git commit.

`build-windows.ps1` verifies those integration points before compilation, including when `-SkipApply` is used.

## Acceptance

The implementation is not accepted until all of these are demonstrated on the rebuilt package:

- current 17-case `auto` probe has no regression;
- `tool_choice=none` never emits a tool;
- conflicting named `get_weather` request emits `get_weather`, not prose/math;
- later-turn NovaClaw-style `required` prompts emit a tool call without a textual promise first;
- TRACE/token capture shows first generated token `48` for hard choice;
- native `<|"|>` and guided JSON argument forms both become valid OpenAI `arguments` JSON;
- nested objects, arrays, Windows paths, booleans and parallel calls retain their JSON types;
- streaming still yields structured `delta.tool_calls` and `finish_reason=tool_calls` with no markup leak.

## Do not

- Enable `enable_tool_guided_generation` globally just because the builder compiles.
- Treat historical XGrammar Gemma4 support as current ground truth.
- Treat source-string helper tests as a substitute for OVMS C++ tests and live TRACE acceptance.
- Copy only `ovms.exe` after a rebuild.
