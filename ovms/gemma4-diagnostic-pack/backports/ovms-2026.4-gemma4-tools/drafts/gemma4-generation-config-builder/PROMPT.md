You are validating and hardening the integrated `Gemma4GenerationConfigBuilder` backport for OpenVINO Model Server 2026.4.

The builder source lives in this folder and is now applied automatically by `apply-backport.ps1` through `apply-gemma4-generation-config.ps1`. Do not replace the existing Gemma4 output parser, do not enable guided generation globally, and do not copy the Hermes3 builder mechanically.

## Goal

Make request-level hard tool choice actually constrain Gemma4 decoding:

- `tool_choice=required` must begin generation with a tool-call tag, not prose;
- named `tool_choice={type:function,function:{name:...}}` must force the selected function;
- `tool_choice=none` must remain tool-free;
- healthy `tool_choice=auto` behavior must not regress.

The relevant failure is NovaClaw later-turn behavior where Gemma4 may say `сейчас запущу` / `я использую` instead of emitting a tool call soon enough. An output parser cannot manufacture a tool call from prose.

## Live evidence, 2026-09-05

Sequential Windows GPU probe against `gemma4-26-heretic` at `127.0.0.1:8000`, temperature 0, max_tokens 256:

- 17 HTTP 200 cases;
- 14 structured `message.tool_calls`;
- zero raw tool markup leaks in `content`;
- ordinary `auto` calls work for strings, numbers, enums, nested objects, arrays, Cyrillic, parallel calls, streaming, file writes and shell commands;
- `tool_choice=none` works;
- first-turn Russian `required` works unconstrained;
- a conflicting named `get_weather` choice is ignored by the unpatched runtime and returns prose/math instead;
- one native Windows-path array arrived with the wrong JSON type.

Conclusion: **do not globally constrain auto mode just because a builder now exists.**

## Integrated OVMS delta

The backport now installs all of the following from a clean pinned source baseline:

1. the two pinned upstream Gemma4 parser commits;
2. `Gemma4GenerationConfigBuilder` source/header;
3. factory `toolParserName == "gemma4"` wiring;
4. Bazel `generation_config_builders` entries;
5. a parser fast path that accepts complete guided standard-JSON argument objects before falling back to native Gemma4 parsing;
6. a `Gemma4OutputParserTest` regression for guided JSON, nested values and Windows path arrays.

`build-windows.ps1` refuses to build a parser-only tree when this integrated overlay is expected, including under `-SkipApply`.

## Generator policy

### 1. `auto`, guided=false

Do nothing beyond the base config. The live model already emits healthy native Gemma4 tool calls and the parser converts them to OpenAI `message.tool_calls`.

### 2. `auto`, guided=true

Use `TriggeredTags`:

- trigger: `<|tool_call>`
- tag begin: `<|tool_call>call:` + tool name
- content: `JSONSchema(parameters)`
- tag end: `<tool_call|>`

This allows normal prose/content until the model chooses the tool trigger, then constrains the call body.

### 3. `required` and named tool choice

Use a **top-level `TagsWithSeparator`**, not `TriggeredTags`:

- tags: all currently allowed tool tags;
- separator: empty string;
- `at_least_one=true`;
- `stop_after_first=false`.

Reason: `TriggeredTags` only constrains generation *after* the model emits the trigger. It cannot prevent `сейчас запущу...` before `<|tool_call>`. A top-level tag sequence constrains output from grammar start and is the candidate mechanism for forcing token 48 (`<|tool_call>`) as the first generated token.

OVMS `OpenAIApiHandler` normalizes a named tool choice to the function name and filters `toolNameSchemaMap` to that function. Therefore every non-reserved (`auto`/`none`/`required`) value can be treated as a named hard choice.

### 4. `none`

Return without installing tool structured output even if graph-level `enable_tool_guided_generation=true`.

## Pinned GenAI support

The OVMS 2026.4 dependency exposes:

- `JSONSchema`
- `EBNF`
- `Concat`
- `Union`
- `Tag`
- `TriggeredTags`
- `TagsWithSeparator`

`TagsWithSeparator` has `separator`, `at_least_one`, and `stop_after_first` and is exercised by OpenVINO GenAI structured-output tests. Do not rewrite the hard path back to `TriggeredTags` merely to resemble Hermes3.

## Wire formats

Hard/generated tag bodies use standard `JSONSchema`, therefore expected guided output is:

```text
<|tool_call>call:get_weather{"city":"Berlin"}<tool_call|>
```

The checkpoint's unconstrained native format is:

```text
<|tool_call>call:get_weather{city:<|"|>Berlin<|"|>}<tool_call|>
```

The integrated patcher now supports **both**. `Gemma4ToolParser` reconstructs the complete outer object and, when it is valid JSON, passes it through canonically. Otherwise it falls back to the existing native `<|"|>` parser. Do not translate valid JSON back into Gemma syntax.

The injected C++ regression covers guided JSON with nested objects and Windows path arrays. Continue to expand coverage if live traces expose additional shapes.

## XGrammar warning

Historical XGrammar PR #588 added a Gemma4 structural tag using standard JSON arguments. That PR is useful historical evidence for tag boundaries, **not current ground truth**.

Current XGrammar later disabled Gemma4 registration because Gemma4's native parameter format wraps strings with `<|"|>` rather than ordinary JSON quotes. Do not cite #588 as proof that current XGrammar supports Gemma4 native parameter grammar.

## Required acceptance

Builder/config behavior:

1. no tools -> no structural config;
2. `none` -> no tool structural config even with graph guided=true;
3. `auto`, guided=false -> no structural config;
4. `auto`, guided=true -> `TriggeredTags`;
5. `required`, guided=false -> top-level `TagsWithSeparator`, at least one;
6. named tool, guided=false -> top-level `TagsWithSeparator` containing only selected tool.

Parser behavior:

- native scalar strings/numbers/bool/null;
- guided standard JSON object;
- nested object;
- arrays;
- Windows paths/backslashes;
- strings containing commas/colons/braces;
- multiple tool calls;
- streaming splits around `<|tool_call>`, braces, quotes / `<|"|>`, and `<tool_call|>`.

End-to-end on rebuilt Windows package:

- rerun the existing 17-case auto probe with no regression;
- conflicting named `get_weather` request must emit `get_weather` instead of answering the math;
- later-turn NovaClaw-style `required` prompts must emit `message.tool_calls` without a preceding textual promise;
- TRACE/token capture must demonstrate first generated token `48` for hard choice;
- `tool_choice=none` remains content-only;
- streaming remains structured and leak-free.

## Deployment rules

- Apply from a clean pinned OVMS source checkout; the wrapper is deliberately strict about the base SHA.
- Do not enable `enable_tool_guided_generation` in diagnostic `vlm-stable` as part of this change.
- Do not treat helper Python source-string tests as C++ acceptance.
- Rebuild and deploy the full OVMS Windows package, not `ovms.exe` alone.
- Keep the existing unconstrained auto path as the control group throughout testing.
