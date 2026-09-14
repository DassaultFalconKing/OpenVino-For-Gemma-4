# gemma4-roundtrip-forensics validation scenarios

## RC2 reference pressure case

Input evidence:

- first-turn `none/auto/required/named/question/parallel/stream` cases pass;
- every successful tool response leaks `<eos>` in assistant content;
- roundtrip turn2 returns HTTP 200, `finish_reason=stop`, empty content, no tool calls, `completion_tokens=1`;
- replacing turn1 assistant content with `null` or `""` does not recover turn2;
- 20 unary + 20 streaming requests and post-run plain chat remain healthy;
- no executor quarantine, GPU fatal, timeout, or server error is present.

A correct application of the skill must:

1. classify roundtrip as generation/re-entry/template-state territory before blaming runtime;
2. keep `<eos>` leakage as a separate protocol defect unless evidence joins the causes;
3. request/execute turn2 in both unary and stream form;
4. preserve exact-history plus clean-history controls;
5. refuse to call the system fixed until the exact-history path is green.

Incorrect responses include:

- "fix `<eos>` first; that is probably the roundtrip cause" without further evidence;
- "parser is broken" based only on empty unary output;
- "runtime/GPU instability" despite healthy repetition and logs;
- accepting `clean-null`/`clean-empty` as production success.
