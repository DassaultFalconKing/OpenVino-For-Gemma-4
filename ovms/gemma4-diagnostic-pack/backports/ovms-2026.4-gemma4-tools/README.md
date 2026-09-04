# OVMS 2026.4 RC1 Gemma4 tool-call parser backport

This backport is for the Windows OVMS source baseline:

`530dc63f816507d18bc14629e8cffeb55e3985e6`

It applies two fixes that Intel merged after that baseline:

1. `503ff866278e9236d08bc9b6ddd18ec879660f72` — tool parser finalization fixes, including Gemma4.
2. `95628b45a082bd3d9562a3ad2f3d0762d5883ca4` — `Gemma4 parsing fixes (#4508)`, including string values containing commas/braces/brackets and structural-tag cleanup.

The goal is narrow: when Gemma4 generates native markup such as
`<|tool_call>call:get_weather{...}<tool_call|>`, OVMS must expose an OpenAI-compatible `message.tool_calls` object instead of leaking that markup into `message.content`.

## Apply and build on Windows

Use a fresh checkout. The apply script deliberately refuses a dirty worktree or any source HEAD other than the pinned RC1 base.

```powershell
git clone https://github.com/openvinotoolkit/model_server.git C:\git\model_server-gemma4
cd C:\git\model_server-gemma4
git checkout 530dc63f816507d18bc14629e8cffeb55e3985e6

C:\path\to\OpenVino-For-Gemma-4\ovms\gemma4-diagnostic-pack\backports\ovms-2026.4-gemma4-tools\build-windows.ps1 `
  -ModelServerPath C:\git\model_server-gemma4 `
  -DependenciesRoot opt
```

If the normal OVMS Windows build dependencies are not installed under `C:\opt`, add `-InstallDependencies`. The build uses `--with_python` because the diagnostic deployment uses `ChatTemplateMode JINJA`, and `--with_tests` so the upstream Gemma4 parser tests can run before the binary is accepted.

The expected binary is:

```text
C:\git\model_server-gemma4\bazel-bin\src\ovms.exe
```

Point `launch.ps1 -OvmsExe` at that binary.

## Runtime acceptance

Start the model with the normal `vlm-stable` diagnostic profile, then run:

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
