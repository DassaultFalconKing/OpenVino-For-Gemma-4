# Gemma-4 OVMS diagnostic deployment pack

This pack diagnoses corrupted or gibberish output from Gemma-4 OpenVINO models under OpenVINO Model Server (OVMS), especially on Intel Arc GPUs.

It deliberately separates two execution paths:

1. `vlm-stable` — **stateful `VLMPipeline`**, `DYNAMIC_QUANTIZATION_GROUP_SIZE=0`
2. `vlm-cb-experimental` — **Continuous Batching**, still `DQ=0`, with `max_num_seqs=1`

Use the stable profile first. Only test the CB profile after the stable profile produces coherent text.

The same pack can be used for both the Wondernuttz Gemma-4 26B model and an OpenVINO Gemma-4 31B model. The model path is injected at launch time.

## Why these profiles

Current OVMS distinguishes:

- `pipeline_type: VLM` -> stateful `VLMPipeline`
- `pipeline_type: VLM_CB` -> continuous-batching VLM pipeline

The pack answers one question cleanly:

> Does the model remain coherent when OVMS uses the stateful pipeline with runtime dynamic quantization disabled?

If `vlm-stable` is coherent but `vlm-cb-experimental` emits garbage, the evidence points at the CB/PagedAttention/scheduler execution path rather than the weights, tokenizer, or basic GPU execution.

## Files

```text
gemma4-ovms-diagnostic-pack/
├─ profiles/
│  ├─ vlm-stable/
│  │  └─ graph.pbtxt
│  └─ vlm-cb-experimental/
│     └─ graph.pbtxt
├─ config.template.json
├─ launch.ps1
├─ smoke_test.py
└─ tests/
```

`launch.ps1` generates a runtime-specific graph and `config.json` under `runtime/`, so the profile files remain portable.

## 26B: stateful correctness baseline

```powershell
cd C:\path\to\gemma4-ovms-diagnostic-pack

.\launch.ps1 `
  -OvmsExe C:\llm\ovms\ovms.exe `
  -ModelPath C:\llm\models\gemma4-26b-ov `
  -ModelName gemma4-26b `
  -Profile vlm-stable `
  -RestPort 8000 `
  -ChatTemplateMode JINJA
```

Then:

```powershell
python .\smoke_test.py `
  --base-url http://127.0.0.1:8000 `
  --model gemma4-26b
```

## 31B: same stateful correctness baseline

```powershell
.\launch.ps1 `
  -OvmsExe C:\llm\ovms\ovms.exe `
  -ModelPath C:\llm\models\gemma4-31b-ov `
  -ModelName gemma4-31b `
  -Profile vlm-stable `
  -RestPort 8000 `
  -ChatTemplateMode JINJA
```

Then:

```powershell
python .\smoke_test.py `
  --base-url http://127.0.0.1:8000 `
  --model gemma4-31b
```

## If JINJA is unavailable in your OVMS build

Re-run the same test with:

```powershell
-ChatTemplateMode MINJA
```

Do not change any other variable during that comparison.

## Continuous-batching diagnostic

After the exact same model is coherent with `vlm-stable`, stop OVMS and launch:

```powershell
.\launch.ps1 `
  -OvmsExe C:\llm\ovms\ovms.exe `
  -ModelPath C:\llm\models\gemma4-26b-ov `
  -ModelName gemma4-26b `
  -Profile vlm-cb-experimental `
  -RestPort 8000 `
  -ChatTemplateMode JINJA
```

Run the same smoke prompt. For 31B, only change `-ModelPath` and `-ModelName`.

## Interpretation

| Stateful `VLM` | `VLM_CB` | Interpretation |
|---|---|---|
| coherent | coherent | CB itself is not reproducing corruption with DQ0 |
| coherent | garbage | strong evidence against weights/tokenizer; investigate CB/PagedAttention/scheduler path |
| garbage | garbage | investigate model artifact, runtime/plugin mismatch, template/tokenizer path, or GPU execution |
| garbage in JINJA, coherent in MINJA | any | template-engine compatibility issue |
| coherent in JINJA, garbage in MINJA | any | MINJA compatibility with this model template is suspect |

## During diagnosis, do not enable

- dynamic quantization group sizes such as 32 or 128
- prefix caching
- speculative decoding
- JSON or grammar-guided output
- extra scheduler tuning
- multiple concurrent sequences
- client-side custom chat templates

Change one variable at a time. Humans invented multivariate debugging mostly to create meetings.

## Generate config without starting OVMS

```powershell
.\launch.ps1 `
  -ModelPath C:\llm\models\gemma4-26b-ov `
  -ModelName gemma4-26b `
  -Profile vlm-stable `
  -NoLaunch
```

Generated files appear under:

```text
runtime\<ModelName>\<Profile>\
```

## Recommended acceptance prompts

Run the same three prompts on both profiles:

```text
Answer in one short sentence: why is the sky blue?
What is 17 * 23? Return only the number.
Translate to German: The model server is working correctly.
```

The goal is binary coherence testing, not model-quality benchmarking.

## About the observed 31B corruption

Output dominated by repeated `1`, `C`, punctuation, occasional non-Latin characters, or fragments such as `lala` is much more consistent with a corrupted token-generation path than normal weak sampling.

If that corruption appears immediately on short prompts, test `vlm-stable + DQ0` before investigating long-context issues.

If short prompts are coherent and corruption begins only at long context, treat long-context/RoPE behavior as a separate investigation.
