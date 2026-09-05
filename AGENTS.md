# Agent instructions: patched OVMS Gemma4 runtime

Use this file whenever the user asks to install, build, patch, or verify OpenVINO Model Server for Gemma4 tool calling on Windows.

Full human + agent procedure: [`ovms/gemma4-diagnostic-pack/INSTALL.md`](ovms/gemma4-diagnostic-pack/INSTALL.md).

## Goal

Self-contained runtime at `C:\llm\ovms-gemma4-patched` that exposes Gemma4 native tool markup as OpenAI `message.tool_calls`.

## Execute, do not only recommend

Run commands, read exit codes and logs, fix root causes, retry only the failed stage.

## Pins

- OVMS source checkout: `C:\git\model_server-gemma4`
- Baseline: `530dc63f816507d18bc14629e8cffeb55e3985e6`
- Helper scripts: `ovms/gemma4-diagnostic-pack/backports/ovms-2026.4-gemma4-tools/`
- Build entry: `build-windows.ps1`
- Launch: `ovms/gemma4-diagnostic-pack/launch.ps1`
- Smoke: `smoke_tool_call.py`

## Hard prohibitions

- No `git reset --hard` in the OVMS checkout while parser patches are present and correct.
- No second apply of the backport (`-SkipApply` if Gemma4 parser files are already modified).
- No Git commits or pushes from `C:\git\model_server-gemma4` unless the user explicitly asked for an OVMS PR from a **separate worktree**.
- No replacing only `ovms.exe` inside an older unpacked OVMS directory.
- No skipping `Gemma4OutputParserTest.*`.
- No `enable_tool_guided_generation`, speculative decoding, or JSON grammar for acceptance.
- `tool_choice=required` is not acceptance.

## Procedure

1. `git pull --ff-only` this helper repo `main`.
2. Confirm OVMS HEAD is `530dc63f…` and inspect `git status --short`. If parser files are already modified, continue with `-SkipApply`.
3. Find real `cl.exe` (`Program Files`, `Program Files (x86)`, or `C:\BuildTools`). Pass `-VisualStudioPath` if needed.
4. Run `build-windows.ps1` with `-ModelServerPath C:\git\model_server-gemma4 -DependenciesRoot opt -DeployTo C:\llm\ovms-gemma4-patched`. Add `-InstallDependencies` only if `C:\opt` is incomplete.
5. Require `Gemma4OutputParserTest.*` PASS and `ovms.exe --version` from the **deployed** directory.
6. Launch with `vlm-stable`, `JINJA`, REST 8000, `PYTHONHOME` set to the patched `python\` directory.
7. Run `smoke_tool_call.py --base-url http://127.0.0.1:8000 --model gemma4-26-heretic`.
8. Final report must be `PASS` or `BLOCKED` with command, log excerpt, and exit code.

## Known machine traps

- PowerShell `$ErrorActionPreference=Stop` + curl/wget stderr.
- OpenCV 4.14 cmake `find_package(Python3 "OFF")`.
- Bazel drogon fetch using PATH `python3` from Python 3.14 while `PYTHONHOME` is 3.12.
- `windows_build.bat` piping Bazel through `tee` (exit code always 0).
- User `PYTHONHOME` pointing at another OVMS Python.
- `Set-Content -Encoding UTF8` BOM breaking OVMS JSON config.

Current wrapper and `launch.ps1` already mitigate these. Do not re-introduce BOM writes or skip the `win_build.log` FAILED check.
