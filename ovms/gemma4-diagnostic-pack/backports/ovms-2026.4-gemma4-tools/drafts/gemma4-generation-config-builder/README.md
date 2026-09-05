# Draft: Gemma4GenerationConfigBuilder

Status: **draft overlay**. Not applied by `apply-backport.ps1`. Not enabled in `vlm-stable`. Parser backport remains the correctness baseline.

This version is intentionally different from the original Hermes3-style draft: live probing showed that Gemma4 `auto` tool calling is already healthy, while `required`/named choice need a stronger decode constraint than `TriggeredTags` can provide.

| File | Role |
|---|---|
| [PROMPT.md](PROMPT.md) | Implementation/acceptance handoff |
| [overlay/src/llm/io_processing/gemma4/generation_config_builder.hpp](overlay/src/llm/io_processing/gemma4/generation_config_builder.hpp) | Class and mode policy |
| [overlay/src/llm/io_processing/gemma4/generation_config_builder.cpp](overlay/src/llm/io_processing/gemma4/generation_config_builder.cpp) | Hard + auto structured-output mapping |
| [overlay/src/llm/io_processing/generation_config_builder.hpp.snippet](overlay/src/llm/io_processing/generation_config_builder.hpp.snippet) | Factory `toolParserName == "gemma4"` |
| [overlay/src/llm/BUILD.snippet](overlay/src/llm/BUILD.snippet) | Bazel `generation_config_builders` srcs/hdrs |

## Evidence that drives the design

Live Windows GPU probe against `gemma4-26-heretic` on 2026-09-05 ran 17 sequential OpenAI chat cases. Fourteen returned structured `message.tool_calls`; the remaining prose cases were `tool_choice=none`, a deliberately conflicting named-tool request, and the post-tool round trip. There were zero raw `<|tool_call>` leaks in `content`.

Important observations:

- ordinary `tool_choice=auto` is already reliable, including nested objects, parallel calls, Cyrillic, streaming and agent-style tools;
- first-turn Russian `tool_choice=required` happened to work unconstrained, so the NovaClaw failure is not a basic parser failure;
- named `tool_choice={type:function,...}` is **not enforced** by the current runtime: the model may answer in prose instead;
- the parser can still produce a wrong JSON type for some native Gemma4 arrays containing Windows paths, so parser tests remain mandatory.

The generator therefore must not globally "fix" auto mode and risk regressing the path that already works.

## Generator policy

| Request mode | Generator behavior |
|---|---|
| no tools | base config only |
| `tool_choice=none` | base config only, even if graph guided generation is enabled |
| `auto`, guided=false | **unconstrained**; current parser/native model path is preserved |
| `auto`, guided=true | `TriggeredTags`; free-form text is allowed until `<|tool_call>` appears, then the call body is constrained |
| `required` | top-level `TagsWithSeparator(tags, "", at_least_one=true)` |
| named function | same hard top-level grammar; OVMS already filters `toolNameSchemaMap` to the named function |

The hard path deliberately does **not** use `TriggeredTags`. A trigger grammar cannot prevent the model from saying `сейчас запущу...` before it emits `<|tool_call>`. A top-level tag sequence begins the constrained generation at a tool tag and is the candidate mechanism for making token 48 (`<|tool_call>`) the first generated token.

That first-token property is an acceptance condition, not something this document pretends to prove by staring intensely at C++.

## Wire-format gate

The builder uses `JSONSchema` for tag content, so guided calls have standard JSON arguments:

```text
<|tool_call>call:get_weather{"city":"Berlin"}<tool_call|>
```

The local checkpoint normally emits Gemma4's native argument dialect:

```text
<|tool_call>call:get_weather{city:<|"|>Berlin<|"|>}<tool_call|><|tool_response>
```

Historical XGrammar PR #588 briefly implemented the standard-JSON structural tag form. **Do not treat that PR as current Gemma4 support.** Current XGrammar later disabled the Gemma4 registration because native string arguments use `<|"|>` instead of ordinary JSON quotes.

Therefore this builder has a non-negotiable parser gate: `Gemma4ToolParser` must accept both native Gemma4 arguments and guided standard JSON before the hard path is enabled in a runtime.

## How to apply for an experiment

1. Use a separate OVMS worktree based on the exact 2026.4 source used by the diagnostic pack. Do not modify the live checkout in place.
2. Copy `gemma4/generation_config_builder.{hpp,cpp}` next to `gemma4_tool_parser.*`.
3. Add the factory snippet before the final fallback `else` in `generation_config_builder.hpp`.
4. Add the BUILD snippet to `generation_config_builders`.
5. Add/finish parser dual-dialect tests before enabling the hard path.
6. Rebuild the **full Windows package**, not only `ovms.exe`.
7. Keep diagnostic `vlm-stable` graph-level guided generation off for the first test. Exercise hard behavior with request-level `tool_choice=required` and named tool choice.

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
- Treat source-string helper tests as a substitute for OVMS C++ parser/builder tests.
- Copy only `ovms.exe` after a rebuild.
