You are finishing Gemma4GenerationConfigBuilder for OpenVINO Model Server 2026.4.

A draft already exists. Start from it. Do not rewrite Hermes3. Do not invent a second tag dialect.

Draft overlay (helper repo):
  ovms/gemma4-diagnostic-pack/backports/ovms-2026.4-gemma4-tools/drafts/gemma4-generation-config-builder/

Read that folder's README.md and overlay C++ first. Then continue from the gates below.

## Goal
Make `tool_choice=required` and graph option `enable_tool_guided_generation: true` actually constrain Gemma4 decoding via OpenVINO GenAI StructuredOutputConfig / XGrammar, the same way llama3/hermes3/phi4/devstral already do. Today `toolParserName == "gemma4"` falls through to BaseGenerationConfigBuilder and logs: "Option enable_tool_guided_generation is set, but will not be effective since no valid tool parser has been provided."

This is the missing piece for NovaClaw: after a few agent turns Gemma4 emits Russian prose ("сейчас запущу", "я использую") instead of native tool markup. The output parser cannot invent tool_calls from prose. Guided generation must force the first tool token (`<|tool_call>`, id 48).

## What already works (do not regress)
Gemma4ToolParser + Gemma4 reasoning parser already convert native markup into OpenAI `message.tool_calls`. TRACE on Windows GPU VLM-stable (2026-09-05, C:\llm\ovms-trace-gemma4.log) with temperature=0, tools present, OpenAI-style tool result messages:

Turn 1 generated tokens (skip_special=false):
  <|tool_call>call:get_weather{city:<|"|>Berlin<|"|>}<tool_call|><|tool_response>
  ids: [48, 6639, 236787, 828, 236779, 19323, 236782, 13319, 236787, 52, 89946, 52, 236783, 49, 50]
Phases: UNKNOWN token 48 "<|tool_call>" → TOOL_CALLS_PROCESSING_TOOL → parse name get_weather → args city:<|"|>Berlin<|"|> → TOOL_CALLS_WAITING_FOR_TOOL sees "<|tool_response>" (token 50) then STOP. Response: finish_reason=tool_calls, content="", arguments JSON {"city":"Berlin"}. Same pattern for Paris and London on later turns. Parser is fine on unconstrained native markup.

Jinja already prefixes the model turn with an EMPTY thought channel:
  <|turn>model
  <|channel>thought
  <channel|>
Do NOT also force a thinking SequenceFormat in the builder unless enable_thinking is actually on. The draft builder correctly omits thought tags.

Chat template adapter TRACE: supportsToolCalls=true, dry-run overrides requiresObjectArguments false → true. Keep that.

Graph for this runtime: pipeline_type VLM, device GPU, no CB, queue 1, JINJA, DYNAMIC_QUANTIZATION_GROUP_SIZE=0. tool_parser is auto-detected gemma4. enable_tool_guided_generation is currently false by policy in the diagnostic pack; implementing the builder is allowed, turning it on in the diagnostic baseline graph is a SEPARATE decision.

Checkout rules:
- OVMS source: C:\git\model_server-gemma4  (live patched 530dc63 — do not git reset --hard, do not commit/push from here)
- PR worktree if committing: C:\git\model_server-pr-gemma4 targeting main-2026.4
- Helper: this repository

## Clone this pattern
Files:
  src/llm/io_processing/hermes3/generation_config_builder.{hpp,cpp}
  src/llm/io_processing/llama3/generation_config_builder.cpp
  src/llm/io_processing/generation_config_builder.hpp
  src/llm/io_processing/base_generation_config_builder.{hpp,cpp}
  src/llm/io_processing/gemma4/gemma4_tool_parser.{hpp,cpp}
  src/llm/BUILD  (ovms_cc_library name = generation_config_builders)
  src/test/llm/output_parsers/gemma4_output_parser_test.cpp

Factory today (draft snippet adds gemma4 BEFORE the else that warns):
  llama3 → Llama3GenerationConfigBuilder
  qwen3/hermes3 → Hermes3GenerationConfigBuilder
  phi4 → Phi4GenerationConfigBuilder
  devstral → DevstralGenerationConfigBuilder
  else → BaseGenerationConfigBuilder + debug warning

Hermes3 logic the draft already copies:
  1. Call BaseGenerationConfigBuilder::parseConfigFromRequest(request) first.
  2. Return early if request.toolNameSchemaMap.empty().
  3. If enableToolGuidedGeneration || request.toolChoice == "required":
       TriggeredTags + per-tool Tag{begin, end, content=JSONSchema}
       if toolChoice == "required": at_least_one = true
       setStructuralTagsConfig
  4. tool_choice=auto + guided=false: no tags (unconstrained; parser still works).
  5. If validateStructuredOutputConfig throws, existing serving code unsets structured config — keep that hatch.

## Ground-truth Gemma4 wire format
Special tokens on this checkpoint:
  48 <|tool_call>     stc_token
  49 <tool_call|>     etc_token
  50 <|tool_response>
  52 <|"|>            string delimiter
  100 <|channel>
  101 <channel|>

Native call (unconstrained TRACE):
  <|tool_call>call:FUNC{key:<|"|>value<|"|>,num:42}<tool_call|>
Name regex (tokenizer_config.json):
  call\:(?P<name>\w+)(?P<arguments>\{.*\})
Optional thinking then tools:
  (<\|channel\>thought\n(?P<thinking>.*?)\<channel\|>)?(?P<tool_calls>\<\|tool_call\>.*\<tool_call\|>)?

## Prior art
1) xgrammar builtin Gemma4 structural tag — the mapping the DRAFT already uses.
   https://github.com/mlc-ai/xgrammar/pull/588
   python/xgrammar/builtin_structural_tag.py  get_gemma4_structural_tag
   TOOL_CALL_BEGIN_PREFIX = "<|tool_call>call:"
   TOOL_CALL_END = "<tool_call|>"
   TOOL_CALL_TRIGGER = "<|tool_call>"
   auto: TriggeredTagsFormat(triggers=[TRIGGER], tags=tags)
   required: same + at_least_one=True
   Intel OVMS main still has NO gemma4 factory branch as of 2026-09-05.

2) vLLM Gemma4 parser / recipes (format + streaming pitfalls, not the OVMS class):
   https://github.com/vllm-project/vllm/blob/main/vllm/parser/gemma4.py
   https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html
   --tool-call-parser gemma4 --reasoning-parser gemma4 --enable-auto-tool-choice
   Fallback if special tokens stripped: bare call:name{args}
   Known: streaming split of <|"|> (vLLM #38946); skip_special_tokens hiding channel markers. OVMS TRACE already has NeedsSpecialTokens: true.

3) Google:
   https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4

4) OVMS docs claim enable_tool_guided_generation works whenever tool_parser is set. True for hermes3/llama3/phi4/devstral. FALSE for gemma4 until factory + builder are wired.

## CRITICAL gate B — do not ship guided gen without this
xgrammar JSONSchema content after begin="<|tool_call>call:get_weather" produces:
  <|tool_call>call:get_weather{"city":"Berlin"}<tool_call|>
TRACE of the unconstrained model produces native:
  <|tool_call>call:get_weather{city:<|"|>Berlin<|"|>}<tool_call|>
Gemma4ToolParser::parseObjectParameter is written for the native <|"|> dialect.

You must:
A. Keep the draft TriggeredTags mapping (already xgrammar-compatible). Do not add '{' to begin.
B. Add parser/unit tests for BOTH native and guided-JSON argument forms. If JSON-after-name mangles arguments, FIX THE PARSER in the same change (detect a JSON object and pass through). Do not invent a custom <|"|> grammar unless GenAI actually exposes that grammar type.
C. Do not enable enable_tool_guided_generation in diagnostic vlm-stable until B is green.
D. tool_choice=required for NovaClaw is allowed once A+B are wired, even if the diagnostic graph keeps guided=false.

## Remaining work after the draft
1. Copy overlay files into an OVMS worktree; apply factory + BUILD snippets.
2. Add unit tests for parseConfigFromRequest (no tools / auto+guided=false / auto+guided=true / required).
3. Keep Gemma4OutputParserTest.* green; add JSON-after-name cases.
4. Rebuild full package (not ovms.exe alone). Verify:
   - unconstrained auto still matches TRACE native path
   - required forces token 48 / message.tool_calls on a "сейчас запущу" style prompt
   - factory no longer logs "will not be effective" for gemma4 when guided is on
5. Do not git reset --hard a correctly patched parser tree. Do not skip parser tests.

## Local evidence
TRACE log: C:\llm\ovms-trace-gemma4.log
NovaClaw: C:\Users\testc\AppData\Roaming\app.novaclaw.desktop\logs\20260905T002223\server.log
  session.tool.textual.recovered promised-tool; session.steer.stream.interrupted
Runtime: C:\llm\ovms-gemma4-patched  model gemma4-26-heretic  REST 8000
