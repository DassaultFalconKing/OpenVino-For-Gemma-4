# Gemma4 clean-port investigation — minimal reviewable fork-main candidate on fresh upstream OVMS 2026.4

- Date (UTC): 2026-09-07
- Investigation repo: `DassaultFalconKing/model_server`, local `C:\git\model_server-gemma4-fast`
- Report repo (this file): `DassaultFalconKing/OpenVino-For-Gemma-4`, `docs/gemmamonster-leading-docs/2026-09-07-gemma4-clean-port-investigation.md`
- Session type: INVESTIGATION / INTEGRATION DESIGN — no merges to remote `main`, no force-push, no rewrite of existing feature branches, no new PR. Local throwaway branches/worktrees only.
- All refs re-resolved via `git fetch origin --prune && git fetch upstream --prune` + `git rev-parse` on 2026-09-07. SHAs below are resolved, not trusted blindly.

## Resolved refs

| Ref | Expected | Resolved | Match |
|---|---|---|---|
| UPSTREAM_MAIN `openvinotoolkit/model_server main` | `5fe145e54064d7a048fd7cdc9603f4bde6f0f175` | `5fe145e54064d7a048fd7cdc9603f4bde6f0f175` | YES — `git log -1` = "Fix qwen3coder tool parser keeping quotes (#4502)"; no drift beyond expected SHA after fetch |
| FORK_MAIN_START `origin/main` | `be410567f2b3f8146eda87087beb59b67199c893` | `be410567f2b3f8146eda87087beb59b67199c893` | YES |
| PARSER_HARDENING `fix/gemma4-parser-hardening-post-f36d2d75` | `d1c21ac1a54d499e644e7619155944a3875fd071` | `d1c21ac1a54d499e644e7619155944a3875fd071` | YES — 36 commits in `be410567..d1c21ac1` |
| GENERATOR_FEATURE `feature/gemma4-llamacpp-auto-generator-port` | `6db0c8fb797a15f5acfd0c4d23b4ef1a75eae196` | `6db0c8fb797a15f5acfd0c4d23b4ef1a75eae196` | YES — 48 commits in `be410567..6db0c8fb` |
| GENERATOR_HANDOFF_COMMIT | `35c5262d9b270005da18a505c06bf3a412394f3b` | `35c5262d9b270005da18a505c06bf3a412394f3b` | YES — docs-only, "record auto generator port handoff" |
| RESPONSES_POLICY_FIX `fix/gemma4-responses-parallel-tool-policy` | `34c2f23d58e96a2c2ef1b3e2f940909c3131ace5` | `34c2f23d58e96a2c2ef1b3e2f940909c3131ace5` | YES — 1 file, 1 line |
| CURRENT LOCAL MERGE-TEST `integration/gemma4-hardening-on-ovms-2026.4` | `c1604e2246bf56908837d6f2c4220cc44e1a2021` | `c1604e2246bf56908837d6f2c4220cc44e1a2021` | YES, with caveat: LOCAL-ONLY branch, no `origin/` ref (`git branch -a` shows only local). Parents: `c1604e22 -> d886ca34 -> 0f1be4c76744364fa2301e993de3095ab249020c`; `0f1be4c7` = `be410567` + `5fe145e5` sync. Evidence of mechanical upstream+parser compatibility only, NOT a future main candidate. |

Upstream `main` has NOT moved beyond `5fe145e5` at fetch time. Analysis below holds relative to actual upstream HEAD (= `5fe145e5`).

Previous merge-test result confirmed: `upstream/main -> PASS`, parser hardening `-> CONFLICT_RESOLVED` (8-file textual overlap set), `35c5262d -> BLOCKED` (not a standalone patch; sits atop ~34-commit generator/tool-policy history; direct merge/cherry-pick drags unwanted lineage).

---

```text
INVESTIGATION_REPORT

UPSTREAM_MAIN:
5fe145e54064d7a048fd7cdc9603f4bde6f0f175 (re-fetched 2026-09-07; `git log -1 upstream/main` = "Fix qwen3coder tool parser keeping quotes (#4502)"; no drift beyond expected SHA; no newer upstream HEAD observed)

FORK_MAIN:
be410567f2b3f8146eda87087beb59b67199c893 (origin/main, verified)

PARSER_BRANCH:
origin/fix/gemma4-parser-hardening-post-f36d2d75@d1c21ac1a54d499e644e7619155944a3875fd071 (verified; 36 commits in be410567..d1c21ac1)

GENERATOR_BRANCH:
origin/feature/gemma4-llamacpp-auto-generator-port@6db0c8fb797a15f5acfd0c4d23b4ef1a75eae196 (verified; 48 commits in be410567..6db0c8fb)

RESPONSES_FIX:
origin/fix/gemma4-responses-parallel-tool-policy@34c2f23d58e96a2c2ef1b3e2f940909c3131ace5 (verified; 1-file, 1-line)

CURRENT_INTEGRATION_BRANCH:
integration/gemma4-hardening-on-ovms-2026.4@c1604e2246bf56908837d6f2c4220cc44e1a2021 (LOCAL-ONLY: no origin/ ref; parents c1604e22 -> d886ca34 -> 0f1be4c76744364fa2301e993de3095ab249020c; 0f1be4c7 = be410567 + 5fe145e5 sync)

RECOMMENDED_BASE:
5fe145e54064d7a048fd7cdc9603f4bde6f0f175 (upstream/main tip; local sync equivalent 0f1be4c76744364fa2301e993de3095ab249020c). DO NOT use be410567 as base: `upstream..be410567` = 142 files, 2276+/5525- (fast-build deletions: servable_management/*, llmnode/idle/schema tests, gemma4_tool_parser 826-line delta, windows_build_fast.ps1). Clean PR must branch from upstream tip and preserve 5fe145e5.

PARSER_MINIMAL_PORT:
- 798e99e04d53fba2d / src/llm/io_processing/gemma4/gemma4_tool_parser.cpp+|.hpp / findMatchingContainerEnd(...,malformedEndTag) quoted-endTag awareness, ownsToolCallBoundaries=true, deferred ++toolCallIndex, parseTools() empty-tools guard (also output_parser.cpp bypass + output_parsing_config.hpp flag + openai_api_handler.cpp guard in same commit)
- 6f6272e11ff10453 / gemma4_tool_parser.cpp / findRecoverableBareCall() (line-boundary `call:` + allowedToolNames/enforceToolRegistry/saneToolName) hooked in parseInContentState/parseInToolCallEndedState/parseChunk
- 30d2b5866a290faa / gemma4_tool_parser.cpp+|.hpp / NumberPreservingWriter::RawNumber, normalizeJsonLosslessly(kParseNumbersAsStringsFlag), NativeValueParser::writeJsonToken lossless path, DOM round-trip removal in normalizeSingleNativeValue/parseNativeArgumentsBody, parseChunk 4096-byte truncate, friend Gemma4ToolParserTestAccess
- 149c8e1b7d5c36dd / gemma4_tool_parser.cpp / isJsonNumberLexeme() strict [-]int[.frac][(e/E)(+/-)exp] gate before RawValue(kNumberType); without it 30d2b586 emits `-`/`01`/`1.` as numbers; parser-only (NOT in generator lineage)
- 1598c3d68c652c35 / gemma4_tool_parser.cpp / bareCallLineBoundary(), couldStillBecomeAllowedTool(), findPendingRecoverableBareCallPrefix(), argsPos==npos return nullopt (was `return candidate` hold); fixes prose-eating + streaming stall; parser-only (NOT in generator lineage)
- aa110ba01a78ed95 / gemma4_tool_parser.cpp+|.hpp / currentCallStart member + resetState() + fail-closed flush `if (State::ToolCallStarted && currentCallStart<size) return wrapDeltaContent(substr(currentCallStart))`; parser-only despite `test()` prefix; KEEP
- Per-file verdicts: gemma4_tool_parser.cpp NEEDS MANUAL PORT (port 149c8e1b+1598c3d6+aa110ba0 onto generator 80b88528 base; wholesale overwrite drops generator AUTO work; splitting 30d2b586 without 149c8e1b or 6f6272e1 without 1598c3d6 reintroduces bugs); gemma4_tool_parser.hpp NEEDS MANUAL PORT (currentCallStart+reset+friend; shared sig/flag); output_parser.cpp KEEP (ownsToolCallBoundaries bypass, identical both branches); output_parsing_config.hpp KEEP (single flag); openai_api_handler.cpp KEEP (empty-tools InvalidArgumentError; 81ff2f2c/6be4dfcc are NO-OP here, DROP from 5-file scope)

GENERATOR_MINIMAL_PORT:
- 80b885281443d7b0 / src/llm/io_processing/generation_config_builder.hpp / ToolConstraintMode{Disabled,Auto,Hard}, getToolConstraintMode(), buildAutoToolGrammar() TriggeredTags{triggers={<|tool_call>},at_least_one=false}, buildMandatoryToolGrammar() TagsWithSeparator+thought Union, switch() dispatch replacing `if(!hard)reset()` unguided-auto path; MANUAL PORT as unit (core Gemma builder)
- 158c6c8aa2447c79f / src/llm/io_processing/base_generation_config_builder.hpp / virtual shouldPreserveStructuredOutputOnValidationFailure(){return false;} (7-line additive); CHERRY-PICK CLEAN
- ac5a8deead2e77f64 / src/llm/io_processing/generation_config_builder.hpp / buildAuto/MandatoryToolGrammar(...,bool parallelToolCalls) stop_after_first=!parallel, hardToolChoice member, Gemma override {return hardToolChoice;}, GenerationConfigBuilder::unset/hasHardToolChoice delegate to impl; MANUAL PORT stacked with 80b88528
- 2badb13ec7c954f9f / src/llm/apis/openai_request.hpp / bool parallelToolCalls{true}; CHERRY-PICK CLEAN
- 1244577fb30474a9c / src/llm/apis/openai_api_handler.hpp / parseParallelToolCallsPolicy() (absent/Null->Ok, !IsBool->InvalidArgument, else assign) + parseTools() virtual; CHERRY-PICK CLEAN (deps: 2badb13e)
- b705fc19dff874da3 / src/llm/apis/openai_completions.hpp / parseTools() override -> policy then base; CHERRY-PICK CLEAN (deps: 1244577f)
- 0cd155a88afbd11fe / src/llm/apis/openai_responses.hpp / identical Responses override; CHERRY-PICK CLEAN (deps: 1244577f)
- Tests to carry with prod: bc4cd8c08749d86165 (auto TriggeredTags contract, gemma4_generation_contract_test.cpp 127 lines), 5da129da6f8048af + 5bec28149a4db7386 (openai_parallel_tool_calls_contract_test.cpp 85 lines + BUILD), 94b74498d01ea23d14eed059e8840b2618dac41f (note prompt typo missing `0`; ValidationFallbackPolicyIsGemmaSpecific + ParallelToolCallsControlsGrammarRepeatability), 5a602b1e03baffce31 + 91d02cf827a4e1e10 (Responses policy test + BUILD dep)
- DROP docs-only 35c5262d9b270005 + e51cbe8461d240031 (handoff/plan reference only)
- DROP c1698126b489acee (wholesale openai_responses.cpp 115+/1242-, blob 3e7ef45d->465c9844, 69180->55312 bytes, strips comments/collapses ResponsesInputBuilder)
- DROP 6db0c8fb797a15f5a as port unit (net-zero restore 1242+/115-, blob 465c9844->3e7ef45d = be410567 blob; `be410567..6db0c8fb -- openai_responses.cpp` empty); real follow-up is 34c2f23d
- Path correction: correct files are src/llm/io_processing/generation_config_builder.hpp + base_generation_config_builder.hpp; src/llm/text_utils/* does not exist (empty `git diff --name-only`)

PARALLEL_TOOL_CALLS_PORT:
- 2badb13e openai_request.hpp:86 parallelToolCalls{true} default
- 1244577f openai_api_handler.hpp:136-142 policy: absent->true, true->true, false->false, wrong type->InvalidArgument("parallel_tool_calls is not a bool")
- b705fc19 openai_completions.hpp:40 + 0cd155a8 openai_responses.hpp:105 overrides (both call policy then base parseTools)
- ac5a8dee generation_config_builder.hpp:109,119,125,132,187,190 grammar mapping parallel=true=>stop_after_first=false / parallel=false=>stop_after_first=true for AUTO (TriggeredTags) and REQUIRED/NAMED (TagsWithSeparator Hard path; named = Hard subset via buildToolTags filter)
- 34c2f23d openai_responses.cpp:789 writer.Bool(true)->writer.Bool(request.parallelToolCalls); `git show --stat` = 1 file 1+/1-; `6db0c8fb..34c2f23d` identical; without it plumbing is INCOMPLETE on 6db0c8fb (request+grammar complete, serialize hardcoded true), COMPLETE on 34c2f23d; mandatory candidate

SESSION_STORE_FINDING:
REWRITE (not KEEP, not plain REMOVE)
Evidence: c1604e22 already rewrote kfs_rest_test.cpp V3ChatCompletionsPropagatesSessionHeaders->SessionIdAndGenericHeaders (X-OVMS-Session-Store/C:\tmp\gemma4-session-store -> X-OVMS-Test-Passthrough/diagnostic-value) and removed payload.headers.emplace("x-ovms-session-store") from max_model_length_test.cpp (now env OVMS_SESSION_STORE_DIR + x-ovms-session-id only, correct). Remainder at HEAD multi_part_parser_drogon_test.cpp:30 `req->addHeader("X-OVMS-Session-Store","C:\\tmp\\gemma4-session-store")` + :50 ASSERT_EQ(lowered["x-ovms-session-store"],...) is same false per-request store-path contract: no reader of X-OVMS-Session-Store in src/ (`git grep` only servable.cpp:375,557,584 getenv OVMS_SESSION_STORE_DIR + X-OVMS-Session-ID warning); 00b678aa message itself says root cause was missing env dir, not dropped header; test body only does newHttpRequest/addHeader/headers-copy/asciiLower lookup, never parseRequestComponents/V3 dispatcher/loadRequest, so mechanically generic header pass-through fixture misnamed as session test. Fix same pattern as c1604e22: X-OVMS-Test-Passthrough/diagnostic-value + keep session-id + content-type lines; optionally rename TEST to GenericHeadersSurviveReqHeadersCopy. Do not modify until clean PR (needs proof, now provided).

AUTO_SEMANTICS:
UNCHANGED (parser merge safe; generator intentionally changes)
Evidence: be410567 vs d1c21ac1 generation_config_builder.hpp AUTO path byte-identical `if(!hardToolChoice){reset();return;}` — no TriggeredTags/at_least_one=false/stop_after_first change; `git diff be410567..d1c21ac1 -- src/llm/apis` hits only openai_api_handler.cpp:250-253 empty-tools guard. Intended generator 6db0c8fb:41-70,107-132,172-192 = Disabled(no tools/none->no grammar) / Auto(""/auto+tools->TriggeredTags lazy free-text-until-<|tool_call>) / Hard(required/named->TagsWithSeparator eager + optional thought Union); at_least_one=false prevents auto->required promotion. Parser merge does not regress AUTO; wholesale generator merge is what introduces lazy AUTO (desired, but must be ported deliberately, not accidentally reverted to old `auto->global hard grammar`).

GENERIC_BUILDER_FALLBACK:
SAFE
Evidence: base_generation_config_builder.hpp:104 default `return false` (historic unguided fallback preserved); base .cpp:141 validate + :147-148 unconditional reset; generation_config_builder.hpp:47 hardToolChoice, :59-60 isHardToolChoiceImpl=required||named, :157-158 Gemma override {return hardToolChoice;}, :163 set in parseConfigFromRequest (auto->false, required/named->true), :228-234 unset guards with "Refusing to clear... fail-closed", :241 hasHardToolChoice delegates; openai_api_handler.cpp:342-345 try validate/catch unset (generic clears, Gemma hard refuses); `git grep shouldPreserve 6db0c8fb -- src/llm` = base + gemma only; hermes3/llama3/phi4/devstral no override (only enableToolGuidedGeneration||required gates, e.g. hermes3:36,38,50); Hermes unchanged. Contracts: bc4cd8c0 + 94b74498 prove gemma-vs-hermes split.

UPSTREAM_OVERLAP:
- 5fe145e5 (#4502, 5 files +364: qwen3coder_tool_parser.cpp 4+, utils.cpp 15+, utils.hpp 6+, io_processing_utils_test 83+, qwen3coder_output_parser_test 256+, trimSurroundingQuotes x2 call sites) vs our gemma4 stack: ZERO file overlap (different parsers/bugs: <|"|>/JSON vs <parameter="x">); be410567..d1c21ac1 -- qwen3coder/utils empty; merge d886ca34 correctly preserves upstream fix at HEAD (utils.cpp + qwen3coder parser contain trimSurroundingQuotes; be410567 lacks it, 0f1be4c7 has it). MUST KEEP upstream files in clean port.
- True textual overlap (both sides edited since e894bac, 8 files): src/BUILD, chat_template/analyzer.cpp, caps.hpp, input_processors/chat_template_adapter.cpp/.hpp, kfs_rest_test.cpp, chat_template_adapter_test.cpp, chat_template_analyzer_test.cpp. d886ca34 already resolved (our analyzer/caps/adapter deltas small: 8,7,26,4 lines second-parent stat); replay must keep upstream hunks + re-apply gemma4 deltas, not overwrite.
- Semantic-only (keep both, no textual conflict): qwen3coder/utils+tests (upstream-only, keep), probe.cpp/hpp +31/+2 (upstream-only; fork deletes relative to upstream — do NOT port deletion blindly, keep upstream probe unless fast-build explicitly drops it with justification), gemma4_tool_parser/servable/output_parser/generation_config/py_jinja/openai_api_handler.cpp (fork-only since e894bac..5fe145e5 -- gemma4/servable/output_parser empty; safe to port).
- fork main divergence warning: upstream..be410567 142 files (fast-build deletions) — clean PR must not carry these.

DROP_FROM_CLEAN_PORT:
- commits: all evidence/harness/docs/session lineage (071c505b,3c14f476,73009951,ba5e0fba,2d6aafcd,f5d62015,49ec1033,2c22b024,3e996806,e72b80ab,b4d3c1c4,8f84ec0a,00b678aa,cd5b2f6c,f3283dd0,2cb5a9a0,f36d2d75,d1c21ac1,35c5262d,e51cbe84) + session/template prod (03d12b1a servable 460+,79cf23aa servable.hpp 49+,7d00c5fe log demote,c09d73aa,6be4dfcc unless session PR,81ff2f2c unless session PR,5519de03,908bc8b7 unless template PR) + c1698126 (wholesale) + 6db0c8fb (net-zero; keep 34c2f23d instead); never `git merge fix/... / feature/... / 35c5262d` wholesale (would drag ~34-commit generator lineage + 402 evidence files)
- directories: ab-evidence/* (402 files: reliability-campaign 181, runs/2cb5a9a0 88, newest-runtime 47, named-fix 19, live-81ff2f2c 12, live-reallyfinal 12, live-chain-auto/named/required 8+8+8, stage-A/B, *.raw x22, *.pyd, *-sha256, version/pid/build-output, pyovms.pyd 180KB), docs/gemma4/* + docs/superpowers/plans|specs/*session-state* + docs/*auto-generator* (reference only)
- files: HANDOFF.md, windows_build_fast.ps1 + scripts/gemma4/*.ps1 (harness, not prod PR), all ab-evidence/*.py as blobs (port file-by-file only if harness PR), src/llm/servable.cpp/.hpp + analyzer/caps/adapter + py_jinja + reasoning_parser session/template hunks (defer to separate session/template PR; see CLEAN_PORT_FILESET note), gemma4_parser_hardening_test.cpp deletion in generator branch must NOT be carried (keep file)

CLEAN_PORT_FILESET:
production (minimal tool-calling, 12 files):
- src/llm/io_processing/gemma4/gemma4_tool_parser.cpp (MANUAL: 798e99e0+6f6272e1+30d2b586+149c8e1b+1598c3d6+aa110ba0)
- src/llm/io_processing/gemma4/gemma4_tool_parser.hpp (MANUAL: currentCallStart+reset+friend; shared sig/flag)
- src/llm/io_processing/output_parser.cpp (KEEP bypass)
- src/llm/io_processing/output_parsing_config.hpp (KEEP flag)
- src/llm/apis/openai_api_handler.cpp (KEEP empty-tools guard only)
- src/llm/apis/openai_api_handler.hpp (1244577f policy+virtual)
- src/llm/apis/openai_request.hpp (2badb13e field)
- src/llm/apis/openai_completions.hpp (b705fc19 override)
- src/llm/apis/openai_responses.hpp (0cd155a8 override)
- src/llm/io_processing/base_generation_config_builder.hpp (158c6c8a hook)
- src/llm/io_processing/generation_config_builder.hpp (MANUAL: 80b88528+ac5a8dee)
- src/llm/apis/openai_responses.cpp (34c2f23d 1-line serialize fix only; explicitly exclude c1698126/6db0c8fb blobs)
- DEFERRED to separate session/template PR (not in clean tool-calling PR): analyzer.cpp, caps.hpp, gemma4_reasoning_parser.cpp, chat_template_adapter.cpp/.hpp, py_jinja_template_processor.cpp, servable.cpp/.hpp, src/BUILD + windows_build_fast.ps1 deltas unless test BUILD needs them
tests (required, with edits):
- src/test/llm/gemma4_fast/BUILD + gemma4_parser_contract_test.cpp (KEEP) + gemma4_parser_hardening_test.cpp (KEEP from 18ad1514+aa110ba0; do NOT accept generator-branch deletion)
- src/test/llm/generation_config/BUILD + gemma4_generation_contract_test.cpp (bc4cd8c0+94b74498+81ff2f2c hunks as applicable) + openai_parallel_tool_calls_contract_test.cpp (5da129da+5a602b1e; add 91d02cf8 responses dep)
- src/test/llm/output_parsers/gemma4_v2_contract_test.cpp (KEEP)
- src/test/kfs_rest_test.cpp (KEEP only c1604e22 generic-header hunk)
- src/test/llm/max_model_length_test.cpp (KEEP only SessionStateStoreTest + c1604e22 fix; drop x-ovms-session-store)
- src/test/multi_part_parser_drogon_test.cpp (REWRITE :30/:50 to X-OVMS-Test-Passthrough per SESSION_STORE_FINDING)
- src/test/llm/chat_template_adapter_test.cpp + chat_template_analyzer_test.cpp (KEEP only gemma4 hunks; resolve 8-file upstream overlap)
optional docs/harness (reference only, NOT in code PR):
- docs/gemma4-auto-generator-port-handoff.md (35c5262d) + 2026-09-07-gemma4-generator-hardening.md (e51cbe84) as review refs; scripts/gemma4/collect-runtime-provenance.ps1 + prepare-google-template-overlay.ps1 + top-level ab-evidence/*.py only if separate harness PR opened file-by-file

PROTOTYPE_BRANCH:
NOT_CREATED

PROTOTYPE_HEAD:
N/A

PROTOTYPE_DIFF_STAT:
N/A (not executed; mechanical prototype deliberately skipped — parser 149c8e1b/1598c3d6/aa110ba0 onto generator 80b88528 base + 8-file upstream analyzer/caps/adapter/BUILD overlap both require MANUAL semantic merge; speculative auto-cherry-pick would violate "no speculative fixes". Expected clean-PR stat from range analysis for reference only: ~12 production files (5 parser + 6 generator/plumbing + 1 responses 1-liner) + ~8 test files/BUILDs; parser-5 diff be410567..d1c21ac1 = 5 files 256+/43- (cpp 279 lines); generator-6 + responses-1 = additive small hunks (request 3+, handler 15+-, 2x7+ overrides, base 7+, gemma builder ~105+-, responses 1-line); total excludes 402 ab-evidence + ~11 docs + session/template hunks (servable 460+/495+, adapter/analyzer/py_jinja) and excludes 142-file fast-build divergence. `git merge-tree 0f1be4c7 d1c21ac1 5fe145e5` smoke shows only expected overlap set, no hidden conflicts beyond listed 8 files.)

CONFLICTS:
- Textual (must hand-resolve, keep upstream then re-apply ours): src/BUILD, analyzer.cpp, caps.hpp, chat_template_adapter.cpp/.hpp + their tests (upstream e894bac..5fe145e5 vs our be410567..d1c21ac1 both touched; our deltas 8/7/26/4 lines)
- Semantic (keep both): upstream qwen3coder/utils+tests (must not be deleted by our diff; d1c21ac1 direct diff vs upstream shows false deletion artifact — use 0f1be4c7-based replay); upstream probe.cpp/hpp (fork deletes — keep upstream unless fast-build justification recorded); fork session/template hunks (defer, do not silently include)
- Lineage (must manual-port, not cherry-pick wholesale): gemma4_tool_parser.cpp 143-line d1c21ac1..6db0c8fb delta (generator has stale 6f6272e1-era `return candidate // hold prefix` bug + lacks isJsonNumberLexeme/bareCallLineBoundary/couldStillBecomeAllowedTool/findPending/currentCallStart); generation_config_builder.hpp 80b88528+ac5a8dee stacked in same file; openai_responses.cpp c1698126 vs 6db0c8fb inverse pair (use only 34c2f23d)
- Test (must not regress): generator branch deletes gemma4_parser_hardening_test.cpp (d1c21ac1..6db0c8fb D) — clean PR must KEEP it; multi_part_parser :30/:50 must be REWRITTEN, not kept

TESTABILITY:
- tests runnable now: git diff --check; python harness syntax (python3 available); git-level contract verification above (grep/log/diff/blob SHAs); manual file:line review
- tests blocked by environment: ALL C++ Bazel builds/tests BLOCKED here (`Get-Command bazel` not found; no cl.exe check performed in this session; windows_build_fast.ps1 not executed) — must NOT claim PASS; implementation session must run Gemma4OutputParserTest.*, gemma4_generation_contract, openai_parallel_tool_calls_contract + ovms.exe --version + smoke_tool_call.py --mode all + 17-case probe + TRACE token-48 first-token gate on Windows OVMS host
- tests requiring Gemma tokenizer: bc4cd8c0 auto-grammar validation, 94b74498 ParallelToolCallsControlsGrammarRepeatability, parser numeric/bare-call corpus (18ad1514 Windows-path, aa110ba0 fail-closed)
- tests requiring live Arc/OVMS: chained-tool acceptance (30052a01/908bc8b7/524443cb harnesses — harness only, do not port as prod), reallyfinal/live session evidence (f3283dd0/e72b80ab), 17-case probe + NovaClaw later-turn + streaming delta.tool_calls/finish_reason=tool_calls no-markup-leak + required/named first-token TRACE

RECOMMENDED_COMMIT_STRUCTURE:
1. chore(base): branch from 5fe145e5 (record `git rev-parse upstream/main` + `git log -1`; do NOT branch from be410567)
2. fix(parser): manual port gemma4_tool_parser.cpp/.hpp core (798e99e0 boundaries + 6f6272e1 bare-call + 30d2b586 lossless numbers/truncate + 149c8e1b lexeme gate + 1598c3d6 prefix-hold fix + aa110ba0 currentCallStart fail-closed) + output_parser.cpp + output_parsing_config.hpp + openai_api_handler.cpp guard
3. feat(generator): manual port ToolConstraintMode + TriggeredTags AUTO + TagsWithSeparator Hard (80b88528) in generation_config_builder.hpp
4. fix(generator): base hook shouldPreserve... (158c6c8a) + Hard wiring + parallel->stop_after_first (ac5a8dee)
5. feat(openai): parallel_tool_calls field + policy + overrides (2badb13e + 1244577f + b705fc19 + 0cd155a8)
6. fix(openai): Responses serialize request.parallelToolCalls (34c2f23d 1-line; explicitly no c1698126/6db0c8fb)
7. test: parser contracts (gemma4_parser_contract + hardening_test KEEP + v2_contract) + generator/parallel contracts (bc4cd8c0 + 5da129da/5bec2814 + 94b74498 + 5a602b1e/91d02cf8) + BUILD deps
8. test: session-store cleanup (c1604e22 hunks KEEP + multi_part_parser :30/:50 REWRITE to X-OVMS-Test-Passthrough)
9. chore: resolve 8-file upstream overlap (BUILD/analyzer/caps/adapter+tests) keeping 5fe145e5 hunks (qwen3coder/utils/tests, probe) + verify `git diff --check`
10. verify: Windows Bazel build + Gemma4OutputParserTest.* + ovms.exe --version + vlm-stable JINJA REST 8000 smoke + 17-case + TRACE token 48 (separate verification session; BLOCKED here)

RECOMMENDED_FINAL_PR:
base: upstream-synced fork tip at 5fe145e54064d7a048fd7cdc9603f4bde6f0f175 (NOT be410567)
head concept: single clean integration branch with ~10 commits above (parser core -> generator AUTO -> fail-closed -> parallel plumbing -> responses 1-liner -> tests -> session-store rewrite -> overlap resolution); NO wholesale `git merge fix/... / feature/... / 35c5262d`; NO second apply; NO history rewrite of existing branches
expected production files: gemma4_tool_parser.cpp/.hpp, output_parser.cpp, output_parsing_config.hpp, openai_api_handler.cpp/.hpp, openai_request.hpp, openai_completions.hpp, openai_responses.hpp/.cpp (1 line), base_generation_config_builder.hpp, generation_config_builder.hpp (+ minimal BUILD test-target edits only)
expected test files: gemma4_fast/BUILD, gemma4_parser_contract_test.cpp, gemma4_parser_hardening_test.cpp, gemma4_generation_contract_test.cpp, openai_parallel_tool_calls_contract_test.cpp, gemma4_v2_contract_test.cpp, kfs_rest_test.cpp (partial), max_model_length_test.cpp (partial), multi_part_parser_drogon_test.cpp (REWRITTEN :30/:50), chat_template_adapter/analyzer_test.cpp (partial gemma4 hunks only)
files/dirs explicitly excluded: ab-evidence/** (402), docs/** + HANDOFF.md + *handoff*.md (~11-13), scripts/gemma4/* + windows_build_fast.ps1 (unless BUILD-only hunk proven), src/llm/servable.cpp/.hpp + analyzer/caps/adapter/py_jinja/reasoning_parser session/template hunks (separate PR), *.raw/*.pyd/*sha256*/*version.txt/*pid.txt/build-output*/launch-env, c1698126 blob + 6db0c8fb restore, all pre-f36d2d75 reliability/session evidence commits

BLOCKERS_BEFORE_PR:
- Design decision: confirm session/template files (servable 460+/495+, analyzer/caps/adapter/py_jinja/reasoning_parser) are OUT of tool-calling PR (separate session PR) — currently the only scope ambiguity
- Design decision: confirm probe.cpp/hpp kept from upstream (do not port fork deletion) + fast-build deletions (142-file be410567 delta) stay out of clean PR
- Manual-port authorship: parser 149c8e1b/1598c3d6/aa110ba0 onto generator 80b88528 base + generator 80b88528/ac5a8dee stacking must be hand-merged (no `git cherry-pick -n` wholesale; STOP if semantics change needed beyond listed symbols)
- multi_part_parser :30/:50 REWRITE must land in same PR (otherwise false X-OVMS-Session-Store contract ships)
- `git diff --check` + `git status --short` clean (except ignored bazel-* dir) + `git show-ref` re-resolved before branch-off (do not trust SHAs blindly if upstream moved)

BLOCKERS_BEFORE_MAIN_MERGE:
- Windows Bazel build PASS + Gemma4OutputParserTest.* PASS (incl. guided-JSON regression) + ovms.exe --version from deployed dir (compile alone is NOT proof of hard choice)
- Runtime gates: auto structured-calls preserved; none tool-free; required structured call without prose; conflicting named get_weather enforced over arithmetic prompt; guided standard JSON + native <|"|> both valid OpenAI JSON; nested arrays/objects typed; streaming delta.tool_calls + finish_reason=tool_calls no markup leak; TRACE proves hard choice begins with token 48 (<|tool_call|>)
- Live Arc 140V acceptance: smoke_tool_call.py --mode all + full 17-case probe + NovaClaw later-turn on vlm-stable JINJA REST 8000 with PYTHONHOME=deployed python\
- No `git reset --hard` on patched tree, no second backport apply (use -SkipApply only for complete parser+generation overlay verified by wrapper), no replace-only-ovms.exe, no global enable_tool_guided_generation in vlm-stable (auto is control), no commits/pushes from C:\git\model_server-gemma4 unless explicit OVMS PR worktree, no BOM writes, no bypass of integration assertion, no skipping win_build.log FAILED check

OVERALL:
NEEDS_DESIGN_DECISION
```

---

## Clean integration implementation plan (next session — no wholesale merges)

> Each step names source commit + touched files. Stop and document conflict if a step requires semantics change beyond listed symbols.

1. `branch from 5fe145e54064d7a048fd7cdc9603f4bde6f0f175` — `git fetch upstream --prune && git rev-parse upstream/main && git checkout -b clean/gemma4-tools-minimal 5fe145e5`; record HEAD. Do NOT branch from `be410567f2b3f8146eda87087beb59b67199c893`.
2. `port parser boundary ownership from 798e99e0` — files `gemma4_tool_parser.cpp/.hpp, output_parser.cpp, output_parsing_config.hpp, openai_api_handler.cpp`: `findMatchingContainerEnd(...,malformedEndTag)`, `ownsToolCallBoundaries=true` + router bypass, deferred `++toolCallIndex`, `parseTools()` empty-tools guard. Keep upstream `qwen3coder/utils/probe` untouched.
3. `port numeric/bare-call recovery from 6f6272e1 + 30d2b586 + 149c8e1b + 1598c3d6 + aa110ba0` — file `gemma4_tool_parser.cpp/.hpp` only, MANUAL (generator base diverged): `findRecoverableBareCall` + `bareCallLineBoundary/couldStillBecomeAllowedTool/findPending...` + `nullopt` fix + `NumberPreservingWriter/isJsonNumberLexeme/writeJsonToken` + 4096 truncate + `currentCallStart` fail-closed flush. Do NOT split `30d2b586` without `149c8e1b`, nor `6f6272e1` without `1598c3d6`.
4. `port Gemma-specific validation fallback hook from 158c6c8a + ac5a8dee (part 1)` — files `base_generation_config_builder.hpp` (`shouldPreserve...(){return false;}`) + `generation_config_builder.hpp` (`hardToolChoice` member, override `{return hardToolChoice;}`, `unset/hasHardToolChoice` delegate). Verify generic/Hermes/Llama/Phi/Devstral stay fail-open.
5. `port parallel_tool_calls request field + API parsing from 2badb13e + 1244577f + b705fc19 + 0cd155a8` — files `openai_request.hpp` (`bool parallelToolCalls{true}`), `openai_api_handler.hpp` (`parseParallelToolCallsPolicy` + `virtual parseTools`), `openai_completions.hpp` + `openai_responses.hpp` (overrides). Policy: absent→true, true→true, false→false, non-bool→InvalidArgument.
6. `port TriggeredTags / TagsWithSeparator stop_after_first from 80b88528 + ac5a8dee (part 2)` — file `generation_config_builder.hpp`: `ToolConstraintMode`, `buildAutoToolGrammar(...,parallel)` (`stop_after_first=!parallel`), `buildMandatoryToolGrammar(...,parallel)`, `Disabled/Auto/Hard` dispatch. Verify `auto`=lazy, `required/named`=eager, `none`=no grammar.
7. `port Responses serialization fix 34c2f23d` — file `openai_responses.cpp:789` `writer.Bool(true)`→`writer.Bool(request.parallelToolCalls)` ONLY. Explicitly exclude `c1698126` wholesale + `6db0c8fb` restore (verify blobs: base `3e7ef45d`, never `465c9844`).
8. `add exact focused tests` — `gemma4_parser_contract_test.cpp` + `gemma4_parser_hardening_test.cpp` (KEEP, do not accept generator deletion) + `gemma4_v2_contract_test.cpp` + `gemma4_generation_contract_test.cpp` (`bc4cd8c0` auto grammar + `94b74498` fallback/parallel) + `openai_parallel_tool_calls_contract_test.cpp` (`5da129da`+`5a602b1e`) + `generation_config/BUILD` + `gemma4_fast/BUILD` deps (`5bec2814`+`91d02cf8`); partial `kfs_rest`/`max_model_length` (`c1604e22` hunks) + `multi_part_parser_drogon_test.cpp:30,50` REWRITE to `X-OVMS-Test-Passthrough`; partial `chat_template_*_test` gemma4 hunks only.
9. `run exact static commands` — `git diff --check`, `git status --short`, `git diff --stat` (expect ~12 prod + ~8 test files, zero `ab-evidence/`/`docs/`/`*.raw`/`*.pyd`), `git log -S shouldPreserve/TriggeredTags/parallelToolCalls` sanity, `git show --stat HEAD` per-commit review.
10. `build Windows OVMS` — per `AGENTS.md`/INSTALL.md pins: `build-windows.ps1 -ModelServerPath <clean-tree> -DependenciesRoot opt -DeployTo C:\llm\ovms-gemma4-patched`, require `Gemma4OutputParserTest.*` PASS + `ovms.exe --version` from deployed dir; on failure fix root cause, retry only failed stage; never `git reset --hard` / second apply / replace-only-exe.
11. `live Arc 140V acceptance` — `launch.ps1` (vlm-stable, JINJA, REST 8000, `PYTHONHOME`=deployed `python\`), `smoke_tool_call.py --base-url http://127.0.0.1:8000 --model gemma4-26-heretic --mode all` + 17-case probe + NovaClaw later-turn; capture TRACE proving token 48 first for `required`/named; final report PASS/BLOCKED with command + log excerpt + exit code.

## Evidence appendix (commands run in `C:\git\model_server-gemma4-fast`)

- `git fetch origin --prune` → 0; `git fetch upstream --prune` → 0
- `git rev-parse upstream/main` → `5fe145e5...`; `origin/main` → `be41056...`; parser → `d1c21ac1...`; generator → `6db0c8fb...`; responses-fix → `34c2f23d...`; HEAD → `c1604e22...`; handoff `35c5262d` verified
- `git rev-list --count`: parser 36, generator 48 from `be410567`
- `git merge-base`: parser/generator vs `origin/main` → `be410567`; vs `upstream/main` → `e894bac71dc02616a68b669af7445a0f8fdb3361`
- `git show --stat 34c2f23d` → 1 file 1+/1-; `git show 34c2f23d` → `writer.Bool(true)` → `writer.Bool(request.parallelToolCalls)`
- `git show --stat c1698126` → `115+/1242-`; blob `be410567:openai_responses.cpp=3e7ef45d`, `c1698126=465c9844`, `6db0c8fb=3e7ef45d` (restore proven)
- `git log -S shouldPreserveStructuredOutputOnValidationFailure --all --oneline` → `ac5a8dee, 158c6c8a, e51cbe84`
- `git log -S TriggeredTags --all --oneline` → `80b88528` (+ docs/harness)
- `git show be410567:.../generation_config_builder.hpp` vs `d1c21ac1:...` → AUTO `if(!hardToolChoice){reset();return;}` identical; vs `6db0c8fb:...` → `ToolConstraintMode/TriggeredTags/stop_after_first/parallelToolCalls/shouldPreserve` present
- `git grep parallelToolCalls 6db0c8fb -- src/llm` → request:86, handler:142, builder:109,119,125,132,187,190
- `git show HEAD:src/test/multi_part_parser_drogon_test.cpp` → `:30` + `:50` still `X-OVMS-Session-Store`; `kfs_rest_test.cpp` at HEAD already generic-header (c1604e22 verified)
- `git diff --stat`: `upstream..be410567` 142 files; `be410567..d1c21ac1` 442 files (+143462/-67); `be410567..6db0c8fb` 449 files; parser-5 files `256+/43-`
- `Get-Command bazel` → not found → C++ build/tests BLOCKED in this env (reported as such, not PASS)
- No branches created, no merges, no pushes, no production edits in investigation session (`git status --short` in model_server clone: only `?? bazel-model_server-gemma4-fast/`; branch left on `integration/gemma4-hardening-on-ovms-2026.4@c1604e22`).

## prohibitions observed

- No `git merge fix/... / feature/... / 35c5262d` as solution; no `git reset --hard`; no second backport apply; no commits/pushes from `C:\git\model_server-gemma4-fast`; no `ovms.exe`-only replacement; no `Gemma4OutputParserTest` skip; no global `enable_tool_guided_generation`; no compile-as-proof-of-hard-choice; no `c1698126` in clean lineage; no `ab-evidence`/dumps in clean PR; no `multi_part_parser :30/:50` edit without proof (proof now recorded above for the implementation session).
