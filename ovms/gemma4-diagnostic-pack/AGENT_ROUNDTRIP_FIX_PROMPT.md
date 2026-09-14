# Agent Prompt: drive Gemma4 RC2 roundtrip to green

You are fixing a narrowly reproduced GEMMAMONSTER/OVMS Gemma4 protocol defect.
This is an implementation/debugging session, not a broad redesign.

## Authorities

Read first:

```text
ovms/gemma4-diagnostic-pack/RC2_ROUNDTRIP_TRIAGE.md
ovms/gemma4-diagnostic-pack/ROUNDTRIP_FORENSICS.md
skills/gemma4-roundtrip-forensics/SKILL.md
```

Use `roundtrip_probe.py` as the acceptance probe. Do not weaken, patch, or
reinterpret the probe to make the product pass.

## Known artifact and source provenance

```text
RC2_BINARY:
C:\git\artifacts\ovms-908d6695-rc2-repacked-20260914\ovms\ovms.exe

RC2_SHA256:
11d74fd958d1cd2570682fa13562c1bfcf0973dabbf79a0378a8d0cdc886a4fb

PRODUCT_REPO:
DassaultFalconKing/gemmamonster_model_server_OVMS

RC2_PRODUCT_COMMIT:
908d669563f57535ab4eb747989e9ab33dfd5267

HANDOFF_SOURCE_HEAD:
a2eaeb783dfd66f80c50070bf7050dd184b01364
```

Before modifying product code, resolve the refs yourself and record the actual
SHAs. Work on an isolated fix branch/worktree from the accepted RC2 product
lineage. Do not move main, release tags, or unrelated integration refs.

## First action: reproduce without edits

Run the forensic probe against the untouched RC2 binary and preserve the output
folder. The baseline is expected to show:

```text
turn1: real question tool call                    PASS
turn1: content contains <eos>                     DEFECT
turn2 unary: HTTP 200 / stop / empty / no tools  FAIL
turn2 completion_tokens                           1
turn2 stream                                      inspect explicitly
clean-null / clean-empty histories                expected to still FAIL
runtime health                                    PASS
```

Use the exact artifact path with `--artifact-path`, and include a server log if
available.

## Diagnostic decision rule

Do not guess from the unary API alone.

- exact unary empty + exact stream empty + clean histories fail:
  inspect session/prompt state, generation re-entry, and chat-template behavior
  after `role: tool`;
- unary empty + stream has meaningful output:
  inspect output parser/OpenAI serializer;
- unary works + stream empty:
  inspect streamer/streaming parser;
- exact fails + cleaned history recovers:
  inspect special-token/history serialization.

The known RC2 evidence already showed that manually removing `<eos>` from the
previous assistant content did not recover unary turn2. Therefore do not assume
that the `<eos>` leak is the roundtrip root cause.

## Investigation priority

Search the RC2 source and recent Gemma4 commits for code governing:

```text
Gemma4 generation config / tool_choice grammar
prompt/session state after a tool call
assistant continuation after role: tool
Gemma4 chat-template / Google Jinja overlay serialization
EOG/EOS stop-token handling on re-entry
Gemma4 output parser / streamer special-token filtering
```

Use the existing Gemma4 C++ contract tests as executable specifications when a
rebuild provides their binaries. Add a regression test before the production
fix whenever the affected seam is testable.

## Change discipline

Make the smallest evidence-driven product change. Do not:

- replace VLM with another pipeline merely to bypass the defect;
- disable tool grammar globally;
- relax required/named semantics;
- special-case the probe prompt text;
- strip arbitrary tokens from all assistant output;
- modify `roundtrip_probe.py` to accept empty turn2;
- declare success because only `clean-null` or `clean-empty` works.

If `<eos>` leakage and roundtrip need separate fixes, keep them as separate
logical changes so provenance remains readable.

## Acceptance loop

For each candidate build:

1. record source commit and exact binary SHA256;
2. start the same Gemma4/VLM profile;
3. run `roundtrip_probe.py` once;
4. inspect `REPORT.md`, exact unary, exact stream, and server-log scan;
5. if red, localize and make the next minimal change;
6. once exact-history is green, rerun with `--repeat 5`;
7. then rerun the existing `toolcall_matrix.py --mode all` to prove no regression
   in none/auto/required/named/question/parallel/stream;
8. run available focused Gemma4 native contract tests from the candidate build.

A candidate is not accepted until both unary and streaming exact-history turn2
produce a valid continuation, `<eos>` no longer leaks to user-visible content,
all five repeated forensic runs pass, the full tool-call matrix remains green,
and runtime health remains clean.

## Required final report

Return:

```text
BASE_PRODUCT_SHA:
FIX_BRANCH:
FIX_HEAD:
BINARY_PATH:
BINARY_SHA256:

BASELINE_FORENSICS:
CANDIDATE_FORENSICS:
REPEAT_5:
TOOLCALL_MATRIX:
FOCUSED_NATIVE_TESTS:
RUNTIME_HEALTH:

ROOT_CAUSE:
FILES_CHANGED:
WHY_THE_FIX_WORKS:
KNOWN_GAPS:

VERDICT:
```

Attach or preserve the before/after forensic evidence directories. If the run is
still red, report the narrowest demonstrated failing subsystem and stop claiming
acceptance. Evidence outranks optimism.
