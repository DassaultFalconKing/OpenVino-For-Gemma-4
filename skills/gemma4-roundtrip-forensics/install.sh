#!/usr/bin/env sh
set -eu
TARGET="${1:-agents}"
SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "$TARGET" in
  agents) DEST="${HOME}/.agents/skills/gemma4-roundtrip-forensics" ;;
  claude) DEST="${HOME}/.claude/skills/gemma4-roundtrip-forensics" ;;
  *) DEST="$TARGET" ;;
esac
mkdir -p "$DEST"
cp -R "$SRC"/. "$DEST"/
printf 'Installed gemma4-roundtrip-forensics to %s\n' "$DEST"
printf "Verify: python -m unittest discover '%s/tests' -p 'test_roundtrip_probe*.py' -v\n" "$DEST"
