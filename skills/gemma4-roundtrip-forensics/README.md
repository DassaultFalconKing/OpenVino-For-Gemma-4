# gemma4-roundtrip-forensics portable skill

Self-contained agent skill for diagnosing Gemma4/OVMS failures after a successful first tool call when the next assistant turn after `role: tool` is empty, stops immediately, or diverges between unary and streaming behavior.

## Contents

- `SKILL.md` — agent instructions and triage decision table.
- `scripts/roundtrip_probe.py` — stdlib-only forensic probe.
- `references/ROUNDTRIP_FORENSICS.md` — detailed evidence contract and usage.
- `references/SCENARIOS.md` — RC2-derived pressure scenario.
- `tests/` — unit and fake-server integration tests.
- `install.ps1` / `install.sh` — optional installers.

## Install

Cross-runtime location used by Codex, Gemini CLI, and other agents that understand Agent Skills:

```text
~/.agents/skills/gemma4-roundtrip-forensics/
```

Claude Code location:

```text
~/.claude/skills/gemma4-roundtrip-forensics/
```

You can also keep the directory repo-local and point an agent at `SKILL.md` explicitly.

### Windows

```powershell
./install.ps1 -Target agents
# or
./install.ps1 -Target claude
```

### Linux/macOS

```bash
./install.sh agents
# or
./install.sh claude
```

## Self-test

From the bundle root:

```bash
python -m py_compile scripts/roundtrip_probe.py
python -m unittest discover tests -p 'test_roundtrip_probe*.py' -v
```

Expected: 9 tests, including one fake server that reproduces the RC2 empty-turn2 signature and one healthy server.

## Typical run

```powershell
python scripts/roundtrip_probe.py `
  --base-url http://127.0.0.1:18091/v3 `
  --model gemma4 `
  --run-label RC2 `
  --artifact-path C:\path\to\ovms.exe `
  --source-head <commit> `
  --server-log C:\path\to\server.stdout.log `
  --output-dir C:\temp\roundtrip-forensics `
  --timeout 240 `
  --max-tokens 256
```

The probe exits 0 only when the exact-history unary and streaming roundtrip are valid and blocking protocol defects are absent.

## Provenance

Portable packaging derived from `DassaultFalconKing/OpenVino-For-Gemma-4`, branch `diagnostics/gemma4-roundtrip-forensics`.
