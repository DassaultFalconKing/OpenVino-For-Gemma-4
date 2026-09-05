#!/usr/bin/env python3
"""Apply the pinned Gemma4 OVMS stack without platform-specific build policy.

The applier only owns source provenance and source-tree mutation. Build toolchain
selection, dependency installation and packaging stay in platform adapters.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = SCRIPT_DIR / "manifest.json"
TEMP_REF_PREFIX = "refs/gemmamonster/apply"


def run_git(
    repo: Path,
    *args: str,
    input_bytes: bytes | None = None,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_bytes,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if check and result.returncode != 0:
        stdout = (result.stdout or b"").decode("utf-8", errors="replace")
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")
        raise RuntimeError(
            f"git {' '.join(args)} failed with exit {result.returncode}\n"
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
    return result


def git_text(repo: Path, *args: str) -> str:
    return run_git(repo, *args).stdout.decode("utf-8", errors="replace").strip()


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 3:
        raise ValueError("manifest schema_version must be 3")
    required = ("base_commit", "upstream_repository", "upstream_commits", "candidate_deltas")
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"manifest missing required keys: {', '.join(missing)}")

    deltas = data["candidate_deltas"]
    if not isinstance(deltas, list) or not deltas:
        raise ValueError("candidate_deltas must be a non-empty list")
    for index, delta in enumerate(deltas):
        for key in ("id", "repository", "base", "head"):
            if not delta.get(key):
                raise ValueError(f"candidate delta {index} missing {key}")
        if index and deltas[index - 1]["head"] != delta["base"]:
            raise ValueError(
                "candidate delta chain is not contiguous: "
                f"{deltas[index - 1]['head']} != {delta['base']}"
            )

    if deltas[0]["base"] != data["base_commit"]:
        raise ValueError(
            "candidate delta chain does not start at base_commit: "
            f"{deltas[0]['base']} != {data['base_commit']}"
        )
    return data


def verify_repo(repo: Path, expected_head: str) -> None:
    if not repo.exists():
        raise ValueError(f"model-server path does not exist: {repo}")
    inside = git_text(repo, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        raise ValueError(f"not a git work tree: {repo}")
    status = git_text(repo, "status", "--porcelain")
    if status:
        raise ValueError("OVMS checkout must be clean before applying the stack")
    actual_head = git_text(repo, "rev-parse", "HEAD")
    if actual_head != expected_head:
        raise ValueError(
            "OVMS checkout is on the wrong baseline: "
            f"expected {expected_head}, got {actual_head}"
        )


def fetch_exact(repo: Path, remote: str, sha: str, ref_name: str) -> str:
    ref = f"{TEMP_REF_PREFIX}/{ref_name}"
    run_git(repo, "fetch", "--no-tags", remote, f"{sha}:{ref}")
    resolved = git_text(repo, "rev-parse", ref)
    if resolved != sha:
        raise RuntimeError(f"fetched ref mismatch for {ref_name}: expected {sha}, got {resolved}")
    return ref


def delete_temp_ref(repo: Path, ref: str) -> None:
    run_git(repo, "update-ref", "-d", ref, check=False)


def apply_upstream_commit(repo: Path, remote: str, sha: str, ordinal: int) -> None:
    ref = fetch_exact(repo, remote, sha, f"upstream-{ordinal}")
    try:
        run_git(repo, "cherry-pick", "--no-commit", ref)
    finally:
        delete_temp_ref(repo, ref)


def apply_candidate_delta(repo: Path, delta: dict[str, str], ordinal: int) -> None:
    base_ref = fetch_exact(repo, delta["repository"], delta["base"], f"delta-{ordinal}-base")
    head_ref = fetch_exact(repo, delta["repository"], delta["head"], f"delta-{ordinal}-head")
    try:
        patch = run_git(repo, "diff", "--binary", base_ref, head_ref).stdout
        if not patch:
            raise RuntimeError(f"candidate delta {delta['id']} is empty")
        run_git(repo, "apply", "--3way", "--index", "-", input_bytes=patch)
    finally:
        delete_temp_ref(repo, base_ref)
        delete_temp_ref(repo, head_ref)


def rollback(repo: Path, original_head: str) -> None:
    run_git(repo, "cherry-pick", "--abort", check=False)
    run_git(repo, "reset", "--hard", original_head, check=False)
    # The initial cleanliness gate makes removal of newly created untracked files safe.
    run_git(repo, "clean", "-fd", check=False)


def apply_stack(repo: Path, manifest: dict[str, Any]) -> None:
    original_head = git_text(repo, "rev-parse", "HEAD")
    try:
        for ordinal, sha in enumerate(manifest["upstream_commits"], start=1):
            print(f"[upstream {ordinal}] {sha}")
            apply_upstream_commit(repo, manifest["upstream_repository"], sha, ordinal)

        for ordinal, delta in enumerate(manifest["candidate_deltas"], start=1):
            print(f"[delta {ordinal}] {delta['id']}: {delta['base']}..{delta['head']}")
            apply_candidate_delta(repo, delta, ordinal)

        # Source mutation is the product; repository history is not. Leave ordinary
        # unstaged changes so the caller can inspect, build, commit or discard them.
        run_git(repo, "reset", "--mixed", "HEAD")
    except Exception:
        rollback(repo, original_head)
        raise


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-server", required=True, type=Path, help="Clean OVMS source checkout")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    manifest = load_manifest(args.manifest.resolve())
    repo = args.model_server.resolve()
    verify_repo(repo, manifest["base_commit"])
    apply_stack(repo, manifest)

    print("Gemma4 portable source stack applied.")
    print(f"  baseline: {manifest['base_commit']}")
    print(f"  candidate: {manifest['candidate_deltas'][-1]['head']}")
    print("  source tree: modified, unstaged, ready for platform build adapter")
    stat = git_text(repo, "diff", "--stat")
    if stat:
        print(stat)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
