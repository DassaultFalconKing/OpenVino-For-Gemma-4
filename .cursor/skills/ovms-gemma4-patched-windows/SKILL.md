---
name: ovms-gemma4-patched-windows
description: >-
  Builds and deploys a self-contained Windows OpenVINO Model Server 2026.4 RC1
  runtime with Gemma4 tool parsing plus hard required/named tool choice, then
  verifies OpenAI message.tool_calls. Use for OVMS Gemma4 build/patch/install,
  build-windows.ps1, Gemma4OutputParserTest, required/named tool_choice, or
  smoke_tool_call.py.
---

# Patched OVMS Gemma4 Windows runtime

Follow [`../../../ovms/gemma4-diagnostic-pack/INSTALL.md`](../../../ovms/gemma4-diagnostic-pack/INSTALL.md) and [`../../../AGENTS.md`](../../../AGENTS.md).

## Do this

1. Execute on the machine. Inspect stdout/stderr/exit codes and fix root causes.
2. Pin OVMS source to `530dc63f816507d18bc14629e8cffeb55e3985e6`.
3. Use `ovms/gemma4-diagnostic-pack/backports/ovms-2026.4-gemma4-tools/build-windows.ps1`.
4. Let `apply-backport.ps1` apply both upstream parser fixes and the local `Gemma4GenerationConfigBuilder` integration. Use `-SkipApply` only when the **complete** overlay is already present; the build wrapper validates it.
5. Deploy the **full** package to `C:\llm\ovms-gemma4-patched`, not `ovms.exe` alone.
6. Run `Gemma4OutputParserTest.*`, including the injected guided-JSON regression.
7. Launch `launch.ps1` with `-Profile vlm-stable -ChatTemplateMode JINJA`. Keep graph-level guided generation off for the baseline.
8. Set `PYTHONHOME` to the deployed `python\` directory before launch.
9. Run `smoke_tool_call.py --mode all`. Require auto, required, and conflicting named choice to pass.
10. Capture TRACE and require token `48` (`<|tool_call>`) as the first generated token for hard choice before declaring acceptance.

## Do not

- `git reset --hard` on a correctly patched OVMS checkout
- re-apply the backport on an already fully patched tree
- use `-SkipApply` on an old parser-only tree
- commit or push from `C:\git\model_server-gemma4` unless the user asked for an OVMS PR from a separate worktree
- enable graph-level tool-guided generation merely because the builder compiles
- skip `Gemma4OutputParserTest.*`
- treat a successful build as proof that `tool_choice=required` or named choice is enforced
- treat `$ErrorActionPreference=Stop` + native stderr as a compiler failure without checking the real process result

## Evidence required in the final report

Helper HEAD; OVMS HEAD + `git status --short`; builder/factory/BUILD/parser integration assertion; VS path + MSVC version; dependency result; `windows_build.bat` / `win_build.log`; Gemma4 gtest result; deployed path; `ovms.exe --version`; launch result; `smoke_tool_call.py --mode all`; full 17-case probe; hard-choice TRACE first token; then `PASS` or `BLOCKED`.
