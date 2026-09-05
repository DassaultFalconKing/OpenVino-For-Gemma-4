# Agent instructions: patched OVMS Gemma4 runtime

Use this file whenever the user asks to install, build, patch, or verify OpenVINO Model Server for Gemma4 tool calling on Windows.

Full procedure: [`ovms/gemma4-diagnostic-pack/INSTALL.md`](ovms/gemma4-diagnostic-pack/INSTALL.md).

## Goal

Produce a self-contained runtime at `C:\llm\ovms-gemma4-patched` with:

- Gemma4 native output parsing to OpenAI `message.tool_calls`;
- dual native / guided-JSON argument parsing;
- request-level hard `tool_choice=required`;
- enforced named function choice;
- unchanged healthy `auto` behavior unless graph-level guided generation is explicitly enabled.

## Execute, do not only recommend

Run commands, inspect stdout/stderr/exit codes, fix root causes, and retry only the failed stage.

## Pins

- OVMS source checkout: `C:\git\model_server-gemma4`
- Source baseline: `530dc63f816507d18bc14629e8cffeb55e3985e6`
- Accepted Gemma4 tool-calling RC1 candidate: `0a537f08987a3df4c0254c1614162c06ac20b968` ([`RC1-ACCEPTANCE.md`](ovms/gemma4-diagnostic-pack/backports/ovms-2026.4-gemma4-tools/RC1-ACCEPTANCE.md)). Later tool-stack changes go on top of this SHA and must prove no regression against that freeze.
- Helper scripts: `ovms/gemma4-diagnostic-pack/backports/ovms-2026.4-gemma4-tools/`
- Apply entry: `apply-backport.ps1`
- Local generation integration: `apply-gemma4-generation-config.ps1`
- Build entry: `build-windows.ps1`
- Launch: `ovms/gemma4-diagnostic-pack/launch.ps1`
- Smoke: `smoke_tool_call.py`

## Hard prohibitions

- No `git reset --hard` on a correctly patched OVMS checkout.
- No second apply of the backport. Use `-SkipApply` only for a **complete** parser + generation overlay; the build wrapper verifies this.
- No Git commits or pushes from `C:\git\model_server-gemma4` unless the user explicitly asked for an OVMS PR from a separate worktree.
- No replacing only `ovms.exe` inside an older unpacked OVMS directory.
- No skipping `Gemma4OutputParserTest.*` for acceptance.
- Do not globally enable `enable_tool_guided_generation` in diagnostic `vlm-stable`; ordinary `auto` is the control path.
- Do not treat a compile as proof of hard tool choice. `tool_choice=required`, named choice, and first-token TRACE are runtime acceptance gates.

## Procedure

1. Update this helper repo to the intended helper branch/HEAD.
2. Confirm OVMS HEAD is `530dc63f…` and `git status --short` is clean before first apply. If reusing a previously patched tree with `-SkipApply`, require the complete builder/factory/BUILD/parser integration.
3. Find the real `cl.exe` (`Program Files`, `Program Files (x86)`, or `C:\BuildTools`). Pass `-VisualStudioPath` if needed.
4. Run `build-windows.ps1` with `-ModelServerPath C:\git\model_server-gemma4 -DependenciesRoot opt -DeployTo C:\llm\ovms-gemma4-patched`. Add `-InstallDependencies` only if `C:\opt` is incomplete.
5. Require `Gemma4OutputParserTest.*` PASS, including the injected guided-JSON regression, and `ovms.exe --version` from the deployed directory.
6. Launch with `vlm-stable`, `JINJA`, REST 8000, `PYTHONHOME` set to the deployed `python\` directory.
7. Run `smoke_tool_call.py --base-url http://127.0.0.1:8000 --model gemma4-26-heretic --mode all`.
8. Run the full 17-case probe and NovaClaw later-turn scenario.
9. Capture TRACE/token output and require token `48` (`<|tool_call>`) as the first generated token for hard `required` / named choice.
10. Final report must be `PASS` or `BLOCKED` with exact command, log excerpt, and exit code/evidence.

## Runtime acceptance

Require all of the following:

- `auto` still returns structured tool calls in the cases that worked before;
- `tool_choice=none` remains tool-free;
- `tool_choice=required` emits a structured call without preceding prose;
- conflicting named `get_weather` is enforced instead of answering the arithmetic prompt;
- guided standard JSON and native `<|"|>` arguments both become valid OpenAI JSON;
- nested arrays/objects keep their types;
- streaming remains `delta.tool_calls` + `finish_reason=tool_calls` with no markup leak;
- TRACE proves hard choice begins with token 48.

## Known machine traps

- PowerShell `$ErrorActionPreference=Stop` + curl/wget stderr.
- OpenCV 4.14 cmake `find_package(Python3 "OFF")`.
- Bazel drogon fetch using PATH `python3` from Python 3.14 while `PYTHONHOME` is 3.12.
- `windows_build.bat` piping Bazel through `tee` and hiding Bazel failure.
- User `PYTHONHOME` pointing at another OVMS Python.
- UTF-8 BOM breaking OVMS JSON config.

Current wrappers mitigate these. Do not re-introduce BOM writes, bypass the integration assertion, or skip the `win_build.log` FAILED check.
