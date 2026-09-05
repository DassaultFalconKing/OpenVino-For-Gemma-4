---
name: ovms-gemma4-patched-windows
description: >-
  Builds and deploys a self-contained Windows OpenVINO Model Server 2026.4 RC1
  runtime with the Gemma4 tool-call parser backport, then verifies OpenAI
  message.tool_calls. Use when the user asks to install, build, patch, compile,
  or verify OVMS for Gemma4 tool calling, ovms-gemma4-patched, build-windows.ps1,
  Gemma4OutputParserTest, or smoke_tool_call.py.
---

# Patched OVMS Gemma4 Windows runtime

Follow [`../../../ovms/gemma4-diagnostic-pack/INSTALL.md`](../../../ovms/gemma4-diagnostic-pack/INSTALL.md) and [`../../../AGENTS.md`](../../../AGENTS.md).

## Do this

1. Execute on the machine. Inspect stdout/stderr/exit codes. Fix root causes.
2. Pin OVMS source to `530dc63f816507d18bc14629e8cffeb55e3985e6`.
3. Use `ovms/gemma4-diagnostic-pack/backports/ovms-2026.4-gemma4-tools/build-windows.ps1`.
4. Pass `-SkipApply` if Gemma4 parser sources are already modified.
5. Deploy the **full** package to `C:\llm\ovms-gemma4-patched` (not `ovms.exe` alone).
6. Run `Gemma4OutputParserTest.*` — a compile without those tests is not success.
7. Launch `launch.ps1` with `-Profile vlm-stable -ChatTemplateMode JINJA`.
8. Set `PYTHONHOME` to the deployed `python\` directory before launch.
9. Run `smoke_tool_call.py`. Acceptance is `PASS: Gemma4 tool call was exposed as OpenAI message.tool_calls`.

## Do not

- `git reset --hard` on a correctly patched OVMS checkout
- Re-apply the backport on already-modified parser files
- Commit or push from `C:\git\model_server-gemma4` unless the user asked for an OVMS PR from a separate worktree
- Enable tool-guided generation, speculative decoding, or JSON grammar
- Treat `tool_choice=required` as acceptance
- Treat `$ErrorActionPreference=Stop` + native stderr as a real compiler failure without checking the command

## Evidence required in the final report

Helper HEAD, OVMS HEAD + `git status --short`, VS path + MSVC version, dependency result, `windows_build.bat` / `win_build.log` result, Gemma4 gtest result, deployed path, `ovms.exe --version`, model launch result, full smoke-test output, then `PASS` or `BLOCKED`.
