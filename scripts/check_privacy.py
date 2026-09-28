"""Check tracked and staged paths for likely private data without reading files."""

from __future__ import annotations

import subprocess
import sys
import re
from pathlib import PurePosixPath
from typing import Iterable


def normalize_path(path: str) -> str:
    """Return a repository-relative path with POSIX separators."""
    normalized = path.replace("\\", "/").lower()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def privacy_reason(path: str) -> str | None:
    """Return a reason when a path names a private artifact, otherwise None."""
    normalized = normalize_path(path)
    name = PurePosixPath(normalized).name
    parts = PurePosixPath(normalized).parts

    if "local" in parts:
        return "private local/ runtime data"
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return "environment file"
    if name in {"data_latest.json", "runner_profile.local.json", "workout-registry.jsonl"}:
        return "legacy private runtime data"
    if "memory" in parts:
        return "agent memory"
    if any(part in {"healthdata", "garminDb".lower(), ".garmindb"} for part in parts):
        return "Garmin private data"
    if name.startswith("_garmin_workouts") and name.endswith(".jsonl"):
        return "Garmin workout registry"
    if name.endswith((".db", ".db-journal", ".sqlite", ".sqlite3", ".fit", ".tcx", ".gpx")):
        return "database or activity export"
    if name.endswith((".key", ".pem", ".p12", ".pfx", ".crt", ".cer")):
        return "private key or certificate"
    secret_artifact = re.compile(r"(?:^|[_.-])(?:token|cookie|key|cert)(?:$|[_.-])")
    safe_artifact_extensions = (".json", ".txt", ".yaml", ".yml", ".ini", ".conf", ".env")
    if name.endswith(safe_artifact_extensions) and secret_artifact.search(name):
        return "token or cookie artifact"
    if name in {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}:
        return "private key artifact"
    return None


def find_private_paths(paths: Iterable[str]) -> list[tuple[str, str]]:
    """Return sorted (path, reason) pairs for paths that must not be committed."""
    findings = [(path, reason) for path in paths if (reason := privacy_reason(path))]
    return sorted(findings, key=lambda item: normalize_path(item[0]))


def git_paths(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if result.returncode:
        message = result.stderr.strip() or "git command failed"
        raise RuntimeError(message)
    return [line for line in result.stdout.splitlines() if line]


def main() -> int:
    try:
        paths = set(git_paths("ls-files"))
        paths.update(git_paths("diff", "--cached", "--name-only", "--diff-filter=ACMR"))
    except RuntimeError as error:
        print(f"ERROR: cannot inspect Git paths: {error}", file=sys.stderr)
        return 2

    findings = find_private_paths(paths)
    if not findings:
        print("OK: no tracked or staged private paths found.")
        return 0

    print("ERROR: private paths must not be committed:")
    for path, reason in findings:
        print(f"- {path} ({reason})")
    print("No file contents were inspected.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
