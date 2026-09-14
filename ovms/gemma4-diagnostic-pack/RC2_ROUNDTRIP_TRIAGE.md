# GEMMAMONSTER RC2 Roundtrip Triage

## Artifact under test

```text
RC2_BINARY:
C:\git\artifacts\ovms-908d6695-rc2-repacked-20260914\ovms\ovms.exe

RC2_SHA256:
11d74fd958d1cd2570682fa13562c1bfcf0973dabbf79a0378a8d0cdc886a4fb

SOURCE_REPO:
DassaultFalconKing/gemmamonster_model_server_OVMS

SOURCE_BRANCH:
docs/rc2-908d6695-handoff-20260914

SOURCE_HEAD:
a2eaeb783dfd66f80c50070bf7050dd184b01364

RC2_PRODUCT_COMMIT:
908d669563f57535ab4eb747989e9ab33dfd5267

OVMS_VERSION:
2026.4.0.908d66956
```

The acceptance run used the exact binary above. Its SHA256 matched the packaged
checksums and no alternate `ovms.exe` from `PATH` was used.

## What is already green

The existing live matrix passed every first-turn protocol case except roundtrip:

```text
none                  PASS
auto_optional         PASS
auto_expected         PASS
required              PASS
named                 PASS
question_auto         PASS
question_required     PASS
question_named        PASS
parallel_required     PASS
question_stream       PASS
question_roundtrip    FAIL
```

Additional evidence:

- repeated same-tool parallel calls passed 4/4;
- 20 sequential unary tool requests passed 20/20;
- 20 streaming tool requests passed 20/20;
- post-run plain chat remained healthy;
- server log contained no executor quarantine, GPU fatal, timeout, ERROR, or FATAL.

Therefore do **not** begin by re-debugging generic tool selection, parallel calls,
streaming startup, or GPU stability. Those are currently evidence-backed lower
priority paths.

## Defect A: roundtrip re-entry failure

Turn1 succeeds with a real `question` tool call. After returning the synthetic
tool result `{"answer":"A"}`, turn2 is:

```text
HTTP              200
finish_reason     stop
content           ""
tool_calls        []
completion_tokens 1
```

The same turn2 failure was reproduced after replacing the prior assistant
`content` with both `null` and `""`.

### Current localization

Highest-priority subsystem family:

1. session/prompt state after a completed tool call;
2. generation configuration re-entry after `role: tool`;
3. chat-template serialization/prefix for the assistant continuation following a
   tool result.

This signature is compatible with immediate EOS before useful second-turn
output. The new `roundtrip_probe.py` tests unary and streaming turn2 separately
to distinguish true generation/re-entry failure from downstream output parsing.

## Defect B: special-token leakage

Every successful tool-call response in the RC2 acceptance evidence carried:

```json
"content": "<eos>"
```

Streaming also emitted `<eos>` as a content delta before `finish_reason=tool_calls`.

Likely subsystem family:

- special-token filtering in the output parser;
- streamer/output serialization around terminal tokens.

### Important separation rule

Defect B is **not currently an explanation for Defect A**. Cleaning `<eos>` from
the history did not recover turn2. Fixing special-token leakage must therefore
not be accepted as a roundtrip fix unless the exact-history roundtrip probe also
goes green.

## Missing RC2 test evidence

The RC2 source contains Gemma4 C++ parser, generation, prompt-state, reasoning,
and chat-template contract test sources, but the packaged RC2 artifact contains
no corresponding test binaries. Rebuilding was explicitly forbidden during the
artifact acceptance run, so those contracts are `NOT_EXECUTED`, not PASS.

The focused live roundtrip probe is therefore important evidence for this RC2,
but it does not retroactively turn missing unit execution into green unit tests.

## Required next experiment

Run `roundtrip_probe.py` against the unchanged RC2 artifact first and preserve the
output directory as the baseline. The expected RC2 classification is roughly:

```text
TURN1_SPECIAL_TOKEN_LEAK
EMPTY_TURN2
IMMEDIATE_EOS
SSE_ZERO_DELTA              # if streaming turn2 also emits no meaningful delta
GENERATION_OR_REENTRY_FAILURE
CLEAN_HISTORY_STILL_FAILS
```

If streaming turn2 unexpectedly contains meaningful output while unary is empty,
reclassify toward output-parser/OpenAI-serializer loss instead of generation.

## Fix acceptance gate

A candidate patch is not accepted merely because the first tool call works or
because a cleaned-history variant works. Require all of the following on the
exact history path:

```text
turn1 valid tool call                 PASS
turn2 unary meaningful continuation  PASS
turn2 streaming meaningful continuation PASS
no <eos> content leak                 PASS
clean-history controls not required   PASS
server remains healthy                PASS
```

After the first green exact-history run, use `--repeat 5` before promoting the
candidate. Preserve before/after evidence directories with artifact provenance.
