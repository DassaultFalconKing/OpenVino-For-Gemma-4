# Draft: Gemma4GenerationConfigBuilder

Status: **draft overlay**. Not applied by `apply-backport.ps1`. Not enabled in `vlm-stable`. Parser backport remains the correctness baseline.

This folder is the handoff package for a stronger model (or a later PR): working C++ sibling of `Hermes3GenerationConfigBuilder`, plus the prompt that produced it.

| File | Role |
|---|---|
| [PROMPT.md](PROMPT.md) | Full implementation prompt (TRACE, xgrammar, gates, acceptance) |
| [overlay/src/llm/io_processing/gemma4/generation_config_builder.hpp](overlay/src/llm/io_processing/gemma4/generation_config_builder.hpp) | Class |
| [overlay/src/llm/io_processing/gemma4/generation_config_builder.cpp](overlay/src/llm/io_processing/gemma4/generation_config_builder.cpp) | TriggeredTags mapping |
| [overlay/src/llm/io_processing/generation_config_builder.hpp.snippet](overlay/src/llm/io_processing/generation_config_builder.hpp.snippet) | Factory `toolParserName == "gemma4"` |
| [overlay/src/llm/BUILD.snippet](overlay/src/llm/BUILD.snippet) | Bazel `generation_config_builders` srcs/hdrs |

## Why this exists

OVMS 2026.4 has a Gemma4 **output parser** and auto-detects `tool_parser: gemma4`. It does **not** have a Gemma4 `GenerationConfigBuilder`. `tool_choice=required` and `enable_tool_guided_generation` are no-ops: the factory falls through to `BaseGenerationConfigBuilder` and logs that guided generation will not be effective.

NovaClaw then sees Russian prose (`сейчас запущу`) instead of `message.tool_calls`. The parser cannot invent tool calls from prose.

## Tag mapping (xgrammar #588, not native dialect)

Guided output this builder asks XGrammar to enforce:

```text
<|tool_call>call:get_weather{"city":"Berlin"}<tool_call|>
```

Unconstrained TRACE of the local 26B checkpoint (2026-09-05) instead emitted:

```text
<|tool_call>call:get_weather{city:<|"|>Berlin<|"|>}<tool_call|><|tool_response>
```

That mismatch is gate B in `PROMPT.md`. Do not ship guided gen until `Gemma4ToolParser` accepts JSON-after-name **or** you prove GenAI can constrain the native `<|"|>` dialect (it currently cannot via `JSONSchema`).

`at_least_one` is set only for `tool_choice=required`. Thought `SequenceFormat` is **not** added: JINJA already prefixes an empty `<|channel>thought` block.

## How to apply (later, not now)

1. Copy the two `gemma4/generation_config_builder.*` files next to `gemma4_tool_parser.*` in an OVMS worktree that already has the parser backport.
2. Paste the factory snippet **before** the final `else` in `generation_config_builder.hpp`.
3. Add the BUILD snippet to `generation_config_builders`.
4. Rebuild. Do not `git reset --hard` a correctly patched parser tree. Do not apply this from `C:\git\model_server-gemma4` if that checkout is the live 530dc63 runtime; use a separate worktree.
5. Keep diagnostic `vlm-stable` with guided gen **off** until parser JSON pass-through is proven. NovaClaw can send `tool_choice=required` per request once the factory is wired.

## Do not

- Enable `enable_tool_guided_generation` in the default diagnostic graph as part of this overlay.
- Treat this overlay as a substitute for `Gemma4OutputParserTest.*`.
- Copy only `ovms.exe` after a rebuild.
