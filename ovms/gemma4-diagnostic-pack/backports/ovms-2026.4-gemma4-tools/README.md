# OVMS 2026.4 RC1 Gemma4 tool-call parser backport

This backport targets the Windows OVMS **source checkout** at exact baseline:

`530dc63f816507d18bc14629e8cffeb55e3985e6`

It applies two fixes that Intel merged after that baseline:

1. `503ff866278e9236d08bc9b6ddd18ec879660f72` — tool parser finalization fixes, including Gemma4.
2. `95628b45a082bd3d9562a3ad2f3d0762d5883ca4` — `Gemma4 parsing fixes (#4508)`, including string values containing commas/braces/brackets and structural-tag cleanup.

The goal is narrow: when Gemma4 generates native markup such as
`<|tool_call>call:get_weather{...}<tool_call|>`, OVMS must expose an OpenAI-compatible `message.tool_calls` object instead of leaking that markup into `message.content`.

## Important path distinction

There are two completely separate locations:

- `-ModelServerPath` points to an OVMS **source checkout** used only to apply the C++ patch and build.
- `-DeployTo` points to the directory where you actually want to run the patched OVMS package.

A prebuilt `ovms.exe` cannot be source-patched in place. The parser is compiled C++ code. The source checkout is therefore required once for rebuilding, but it can live anywhere and does not become your runtime directory.

The apply step creates **no Git commit**, needs no Git user.name/user.email, and leaves the source changes as ordinary local modified files.

## Apply and build on Windows

If you already have `C:\git\model_server-gemma4` from an earlier attempt, reuse it after confirming it is clean and still on the pinned baseline:

```powershell
git -C C:\git\model_server-gemma4 status --short
git -C C:\git\model_server-gemma4 rev-parse HEAD
```

The second command must print:

```text
530dc63f816507d18bc14629e8cffeb55e3985e6
```

Otherwise create a fresh source checkout:

```powershell
git clone https://github.com/openvinotoolkit/model_server.git C:\git\model_server-gemma4
git -C C:\git\model_server-gemma4 checkout 530dc63f816507d18bc14629e8cffeb55e3985e6
```

Build a complete self-contained package without touching your existing OVMS runtime:

```powershell
C:\path\to\OpenVino-For-Gemma-4\ovms\gemma4-diagnostic-pack\backports\ovms-2026.4-gemma4-tools\build-windows.ps1 `
  -ModelServerPath C:\git\model_server-gemma4 `
  -DependenciesRoot opt `
  -InstallDependencies `
  -DeployTo C:\llm\ovms-gemma4-patched
```

If the normal OVMS Windows build dependencies already exist under `C:\opt`, omit `-InstallDependencies`.

The build uses `--with_python` because the diagnostic deployment uses `ChatTemplateMode JINJA`, and `--with_tests` so the upstream Gemma4 parser tests can run before packaging.

`windows_create_package.bat` then creates the matching self-contained runtime under:

```text
<ModelServerPath>\dist\windows\ovms
```

and `-DeployTo` copies that entire package, including the matching OpenVINO/GenAI/tokenizer DLLs and embedded Python, to the runtime location you chose.

Do not copy only `ovms.exe` over an unrelated unpacked runtime. That risks mixing the patched executable with incompatible DLLs.

## Replacing an existing unpacked OVMS directory

Stop OVMS first. Then pass the existing directory plus `-ForceDeploy`:

```powershell
.\build-windows.ps1 `
  -ModelServerPath C:\git\model_server-gemma4 `
  -DependenciesRoot opt `
  -DeployTo C:\llm\ovms `
  -ForceDeploy
```

The script does not delete the old runtime. It renames it to a timestamped backup such as:

```text
C:\llm\ovms.backup-20260904-205900
```

and then deploys the new self-contained package to `C:\llm\ovms`.

## Runtime acceptance

Start the model using the `ovms.exe` from `-DeployTo`, then run:

```powershell
python .\backports\ovms-2026.4-gemma4-tools\smoke_tool_call.py `
  --base-url http://127.0.0.1:8000 `
  --model gemma4-26-heretic
```

Acceptance requires all of the following:

- the HTTP request completes;
- `message.tool_calls` is present and non-empty;
- the first function is `get_weather`;
- arguments are valid JSON;
- `finish_reason` is `tool_calls`;
- raw `<|tool_call>` markup is absent from `message.content`.

## Deliberate limitation

`tool_choice=required` is not an acceptance criterion for this backport. In the 2026.4 source line Gemma4 has an output parser, but it still does not have a Gemma4-specific `GenerationConfigBuilder`; forcing/guided-generation behavior is therefore a separate upstream gap. This patch fixes the observed parser/serialization failure first and keeps guided generation out of the correctness baseline.

Do not enable `enable_tool_guided_generation` for this acceptance run.
