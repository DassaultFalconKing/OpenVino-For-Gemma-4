# Install patched OVMS 2026.4 for Gemma4 tool calling (Windows)

This is the install path that produces a **self-contained** runtime at `C:\llm\ovms-gemma4-patched` (or another `-DeployTo` directory). The Gemma4 C++ tool parser is compiled into `ovms.exe`. You cannot patch a prebuilt `ovms.exe` in place.

Two audiences:

- **Manual** — follow the commands in order.
- **Agent** — follow `AGENTS.md` at the repo root (and the Cursor skill `ovms-gemma4-patched-windows`). Do not skip the hard rules.

Pinned facts from a successful local build:

| Item | Value |
|---|---|
| Helper repo `main` (docs/wrapper baseline) | current `main` of this repository |
| OVMS source baseline | `530dc63f816507d18bc14629e8cffeb55e3985e6` (2026.4 RC1) |
| Upstream parser fixes | `#4493` `503ff866…`, `#4508` `95628b45…` |
| Deployed runtime | `C:\llm\ovms-gemma4-patched` |
| Acceptance | `message.tool_calls` for `get_weather`, not raw `<\|tool_call>` in `content` |

## Hard rules (both humans and agents)

1. **Do not** `git reset --hard` in the OVMS source checkout while Gemma4 parser files are correctly modified.
2. **Do not** apply the backport twice. If those parser files are already modified, pass `-SkipApply`.
3. **Do not** create Git commits or push from `C:\git\model_server-gemma4` unless you are explicitly opening an OVMS PR from a **separate** worktree.
4. **Do not** copy only `ovms.exe` over an old unpacked OVMS tree. Deploy the full package (EXE + OpenVINO/GenAI/tokenizer DLLs + bundled `python\`).
5. **Do not** disable `Gemma4OutputParserTest.*` to get a green build.
6. **Do not** enable `enable_tool_guided_generation`, speculative decoding, or JSON/grammar mode for this acceptance run.
7. `tool_choice=required` is **not** an acceptance criterion. Use `tool_choice=auto` and `temperature=0`.

## Prerequisites

- Windows 10/11 x64, ~50 GB free on `C:` (dependencies + Bazel + OpenCV).
- Git, curl.
- Visual Studio 2022 **Build Tools** with Desktop C++:
  - MSVC v143 x64 (`cl.exe` under `VC\Tools\MSVC\<ver>\bin\Hostx64\x64\cl.exe`)
  - Windows 11 SDK
  - CMake tools for Windows
  - MSVC v142 (`14.29.x`) if OpenCV configure uses `-T v142`
- Intel Arc GPU + current driver (for the 26B GPU serve path).
- Model directory, for example:
  `C:\llm\models\OpenVINO\Wondernutts\gemma-4-26B-A4B-it-qat-q4_0-unquantized-uncensored-heretic-int4-ov`

Standard VS locations the wrapper checks:

```text
C:\Program Files\Microsoft Visual Studio\2022\BuildTools
C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools
C:\BuildTools
```

If `cl.exe` is somewhere else, pass `-VisualStudioPath`. A directory named BuildTools without `cl.exe` is not sufficient.

---

# Manual install

## 1. Clone this repository

```powershell
git clone https://github.com/DassaultFalconKing/OpenVino-For-Gemma-4.git
cd OpenVino-For-Gemma-4
```

## 2. Checkout OVMS 2026.4 RC1 source (not a runtime zip)

```powershell
git clone https://github.com/openvinotoolkit/model_server.git C:\git\model_server-gemma4
git -C C:\git\model_server-gemma4 checkout 530dc63f816507d18bc14629e8cffeb55e3985e6
git -C C:\git\model_server-gemma4 rev-parse HEAD
```

HEAD must be `530dc63f816507d18bc14629e8cffeb55e3985e6`. If the tree already has local Gemma4 parser modifications from a previous attempt, keep them and use `-SkipApply` later. Do not reset.

## 3. Build and deploy

From `ovms\gemma4-diagnostic-pack\backports\ovms-2026.4-gemma4-tools`:

```powershell
.\build-windows.ps1 `
  -ModelServerPath C:\git\model_server-gemma4 `
  -DependenciesRoot opt `
  -InstallDependencies `
  -DeployTo C:\llm\ovms-gemma4-patched
```

If `C:\opt` is already fully populated from a previous successful dependency install, omit `-InstallDependencies`.

If parser files are already modified, add `-SkipApply`.

If VS is not under Program Files:

```powershell
.\build-windows.ps1 `
  -ModelServerPath C:\git\model_server-gemma4 `
  -DependenciesRoot opt `
  -SkipApply `
  -VisualStudioPath "C:\BuildTools" `
  -DeployTo C:\llm\ovms-gemma4-patched
```

The wrapper:

- locates `cl.exe` and sets `BAZEL_VC_FULL_VERSION` to the real toolset;
- temporarily rewrites Intel hardcoded VS paths in `windows_install_build_dependencies.bat` / `windows_build.bat` and restores them byte-for-byte afterwards;
- installs Python 3.12 into `C:\opt\Python312` and creates `python3.exe` there (Bazel's drogon fetch calls `python3` first; a Python 3.14 `python3.exe` plus `PYTHONHOME=C:\opt\Python312` causes `SRE module mismatch`);
- skips OpenCV's broken Python detection (`OPENCV_PYTHON_SKIP_DETECTION=ON`);
- treats `windows_build.bat` as failed if `win_build.log` contains `FAILED: Build did NOT complete successfully` (`| tee` otherwise hides Bazel's exit code);
- runs `Gemma4OutputParserTest.*`;
- packages EXE + matching DLLs + bundled Python, then copies to `-DeployTo`.

Expect hours for first dependency install + Bazel compile. Later runs skip existing `C:\opt` pieces.

## 4. Sanity-check the runtime

```powershell
C:\llm\ovms-gemma4-patched\ovms.exe --version
```

Confirm `ovms.exe`, `openvino*.dll`, `openvino_genai.dll`, `openvino_tokenizers.dll`, `python\`, and `setupvars.bat` all live in that directory.

## 5. Serve Gemma4 (JINJA, vlm-stable)

Point `PYTHONHOME` at the **bundled** runtime Python, not another OVMS/Python install:

```powershell
$runtime = "C:\llm\ovms-gemma4-patched"
$env:PYTHONHOME = Join-Path $runtime "python"
$env:PATH = "$runtime;$env:PYTHONHOME;$env:PYTHONHOME\Scripts;" + $env:PATH

cd <this-repo>\ovms\gemma4-diagnostic-pack
.\launch.ps1 `
  -OvmsExe "$runtime\ovms.exe" `
  -ModelPath "C:\llm\models\OpenVINO\Wondernutts\gemma-4-26B-A4B-it-qat-q4_0-unquantized-uncensored-heretic-int4-ov" `
  -ModelName gemma4-26-heretic `
  -Profile vlm-stable `
  -RestPort 8000 `
  -ChatTemplateMode JINJA
```

`launch.ps1` writes UTF-8 **without BOM**. A UTF-8 BOM makes OVMS reject `config.json` (`Configuration file is not a valid JSON file. Error: Invalid value.`).

Wait until logs show `ServableManagerModule started` and `Auto-detected tool_parser: gemma4`.

## 6. Tool-call acceptance

```powershell
python .\backports\ovms-2026.4-gemma4-tools\smoke_tool_call.py `
  --base-url http://127.0.0.1:8000 `
  --model gemma4-26-heretic
```

Required PASS line:

```text
PASS: Gemma4 tool call was exposed as OpenAI message.tool_calls
```

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| PowerShell aborts on curl `% Total` | `$ErrorActionPreference=Stop` treats native stderr as terminating | Current `build-windows.ps1` uses `Invoke-NativeProcess` |
| OpenCV CMake `find_package(... "OFF")` | OpenCV 4.14 BOOL `OPENCV_PYTHON3_VERSION` + stray `python3.exe` | Wrapper patches cmake to `OPENCV_PYTHON_SKIP_DETECTION=ON` |
| Bazel `SRE module mismatch` in `_drogon_cpp` | `which("python3")` finds Python 3.14 | Wrapper copies `C:\opt\Python312\python3.exe` |
| `windows_build.bat` exit 0 but no `ovms.exe` | `bazel … \| tee win_build.log` | Wrapper reads `FAILED:` from the log |
| OVMS `config.json` Invalid value | UTF-8 BOM from `Set-Content -Encoding UTF8` | Current `launch.ps1` writes UTF-8 no BOM |
| `VLM pipeline generation failed:` | server-side GenAI error | Read OVMS log; do not guess from REST `"Request processing failed"` |
| User-level `PYTHONHOME=C:\llm\ovms\python` | mixes another runtime's stdlib | Override `PYTHONHOME` to the patched `python\` before launch |

Logs: `C:\git\model_server-gemma4\win_build.log`, `win_environment.log`.

---

# Agent install

Paste this as the agent task (or rely on `AGENTS.md` + skill `ovms-gemma4-patched-windows`):

```text
Build Windows OVMS 2026.4 RC1 from source with the Gemma4 tool-parser backport
already in this repo, and deploy a self-contained runtime to
C:\llm\ovms-gemma4-patched.

Follow ovms/gemma4-diagnostic-pack/INSTALL.md and AGENTS.md exactly.
Use -SkipApply if the OVMS checkout already has the Gemma4 parser files modified.
Do not git reset --hard. Do not push from C:\git\model_server-gemma4.
Do not copy only ovms.exe. Run Gemma4OutputParserTest.*. Launch with
launch.ps1 Profile vlm-stable ChatTemplateMode JINJA. Then run
smoke_tool_call.py. Report PASS or BLOCKED with evidence.
```

The agent must execute commands on the machine, inspect exit codes, and fix root causes. Recommendations-only is a failed run.
