---
name: gemma4-roundtrip-forensics
description: Use when Gemma4/OVMS completes an initial tool call but the next assistant turn after a tool result is empty, stops immediately, hangs, leaks special tokens, or differs between unary and streaming behavior.
---

# Gemma4 Roundtrip Forensics

## Overview

Localize failures at `assistant tool_call -> role: tool -> next assistant` without reopening the whole tool-calling stack. Preserve evidence before changing code. This package is self-contained: the probe is `scripts/roundtrip_probe.py`.

If a systematic-debugging skill is available, use it during the code-fix phase. Otherwise keep the same discipline: form one hypothesis, change one localized subsystem, rebuild, rerun the identical probe.

## Entry condition

The first tool call already works. Typical symptoms are `finish_reason=stop` with empty turn2, `completion_tokens=1`, no second `tool_calls`, immediate SSE termination, or `<eos>` leaking into assistant content.

## Procedure

1. Record artifact provenance: binary path/SHA256, source head, model, endpoint, profile, server log.
2. Run `python scripts/roundtrip_probe.py --help`, then run the probe against the live server. Keep the whole evidence directory.
3. Read the **exact-history** turn2 unary and streaming results before touching code.
4. Compare `exact` with `clean-null` and `clean-empty` history controls.
5. Localize with this table:

| Evidence | First subsystem to inspect |
|---|---|
| unary empty + stream empty + clean histories fail | session state, generation config, chat-template re-entry after `role: tool` |
| unary empty + stream has meaningful delta | output parser / OpenAI serializer |
| unary works + stream empty | streamer / streaming parser |
| exact fails + cleaned history recovers | special-token filtering / history serialization |
| `<eos>` leaks on turn1 but cleaned turn2 still fails | treat leakage and roundtrip as separate defects |

6. Fix one localized subsystem only. Preserve the failing evidence as the before-case.
7. Rerun the same probe against the new artifact lineage.
8. Green means exact-history unary **and** stream both produce a valid continuation, no blocking protocol defects remain, and the runtime stays healthy.
9. After one green run, require `--repeat 5`, then rerun the broader tool-calling acceptance matrix before promotion.

## RC2 reference signature

A known failure is: turn1 tool call succeeds; turn2 returns HTTP 200, `finish_reason=stop`, empty content, no tool call, `completion_tokens=1`; replacing prior assistant content with `null` or `""` does not recover it. That is evidence for generation/re-entry/template state, not GPU failure and not `<eos>` contamination alone.

## Evidence rule

Do not report a roundtrip fix from a single successful tool call or from a cleaned-history workaround. Keep `manifest.json`, raw unary/SSE responses, `sse-timeline.json`, timing/usage, request history, server-log scan, and `REPORT.md`.

`TTFT` is meaningful only for streaming in this probe. Unary records TTFB and total latency rather than inventing a pseudo-TTFT.

For flags, evidence layout, and interpretation details, read `references/ROUNDTRIP_FORENSICS.md`. For the validation pressure case, read `references/SCENARIOS.md`.
