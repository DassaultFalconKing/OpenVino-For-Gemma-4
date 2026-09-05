# Gemma4 parser/generator integration decision

## Candidates compared

### Runtime-proven candidate

`DassaultFalconKing/model_server:fix/gemma4-parser-generation-candidate`

- parent: `721e13d12c0fd4820ccc4bd06a866963c6524da5`
- head: `fd0c86c77ce6812fd6c77d9c8ee16a7dd7cb973b`
- selected canonical branch: `integration/gemmamonster-gemma4-portable-tools`

### Heretic research hardening

`DassaultFalconKing/model_server:hardening/gemma4-heretic-parser-streaming`

- head: `3bbc47949eb35fe70cfd098d52dc62c306774396`

## Decision

Use `fd0c86c77ce6812fd6c77d9c8ee16a7dd7cb973b` as the production source candidate.

It is the only compared tree that combines the required parser hardening with the request-level `Gemma4GenerationConfigBuilder`, guided JSON support on both streaming and unary paths, and direct runtime evidence on the target Heretic model.

## Behavior-by-behavior selection

| Behavior | Selected source | Reason |
| --- | --- | --- |
| wait for complete `<tool_call|>` | `fd0c86c` lineage | present and runtime exercised |
| split structural-marker holdback | `fd0c86c` lineage | exhaustive byte-cut tests and runtime no-leak evidence |
| reasoning -> tool without `<channel|>` | `fd0c86c` | explicitly scoped through parser capabilities and locally accepted |
| recursive native objects | `fd0c86c` | preserves nested JSON structure |
| arrays / Windows path escaping | `fd0c86c` | fixed previous stringification witness |
| guided standard JSON, streaming | `fd0c86c` | parser and hard generator exercised together |
| guided standard JSON, unary | `fd0c86c` | closes the earlier streaming-only overlay gap |
| required/named hard generation | `fd0c86c` | TRACE proved first generated token 48 |
| synthetic closure of truncated arguments | **rejected** from `3bbc479` | invents structure not emitted by the model; requires real Heretic trace before production acceptance |
| `<turn|>` as alternate unary tool terminator | research watch-list from `3bbc479` | plausible tolerance improvement, but not required by current runtime evidence |
| complete call in one backend chunk / combined terminal chunk | research watch-list from `3bbc479` | valuable adversarial cases; must be tested against the selected candidate before adopting extra state-machine code |

## Integration rule

Do not merge the two branches wholesale. The Heretic research line contains useful tests and hypotheses but also a recovery policy that conflicts with the accepted deterministic parser contract.

The portable deployment stack therefore reconstructs:

1. pinned OVMS 2026.4 RC1 baseline;
2. pinned upstream parser fixes;
3. published parser streaming-hardening delta;
4. runtime-proven `fd0c86c` candidate delta.

The tester must explicitly probe the two unique safe research ideas, one-backend-chunk completion and alternate terminators. If the selected candidate fails a real runtime or focused C++ witness there, promote the narrow fix only, with a failing test first. Do not import synthetic truncated-call repair as collateral.
