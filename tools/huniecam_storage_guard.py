#!/usr/bin/env python3
"""Report large Madeira diagnostic artifacts that can silently consume iPad storage.

Read-only by design. Madeira issue #123 reported crash-created fex-jit-dump.bin
files hundreds of MiB in size. This tool identifies them and other title logs,
but never deletes anything automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_STORAGE_GUARD_V1"
DUMP_NAMES = {"fex-jit-dump.bin"}
LOG_NAMES = {"madeira-log.txt", "output_log.txt", "player.log", "player-prev.log"}


def fingerprint(path: pathlib.Path, max_hash_bytes: int = 4 * 1024 * 1024) -> str:
    """Hash only a bounded prefix; enough to distinguish artifacts without reading huge dumps."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        h.update(f.read(max_hash_bytes))
    return h.hexdigest()


def scan(root: pathlib.Path, dump_warn_mib: float = 64.0, log_warn_mib: float = 16.0) -> dict[str, Any]:
    root = root.expanduser().resolve()
    artifacts: list[dict[str, Any]] = []
    total = 0
    if root.is_dir():
        for p in root.rglob("*"):
            try:
                if not p.is_file():
                    continue
                name = p.name.casefold()
                if name not in DUMP_NAMES and name not in LOG_NAMES:
                    continue
                size = p.stat().st_size
                total += size
                rel = p.relative_to(root).as_posix()
                kind = "jit_dump" if name in DUMP_NAMES else "log"
                threshold = dump_warn_mib if kind == "jit_dump" else log_warn_mib
                artifacts.append({
                    "relative_path": rel,
                    "kind": kind,
                    "bytes": size,
                    "mib": round(size / (1024 * 1024), 2),
                    "large": size >= threshold * 1024 * 1024,
                    "prefix_sha256": fingerprint(p),
                })
            except OSError:
                continue
    artifacts.sort(key=lambda x: int(x["bytes"]), reverse=True)
    large_dumps = [a for a in artifacts if a["kind"] == "jit_dump" and a["large"]]
    large_logs = [a for a in artifacts if a["kind"] == "log" and a["large"]]
    actions = []
    if large_dumps:
        actions.append("Large fex-jit-dump.bin artifacts are present. Preserve the one needed for the active diagnosis, then remove stale copies manually only after confirming they are no longer evidence. This tool does not delete them.")
    if large_logs:
        actions.append("Large text logs are present. Keep the current failure log; archive or remove stale duplicates manually after evidence has been recorded.")
    if not artifacts:
        actions.append("No known HunieCam/Madeira diagnostic artifacts were found under the supplied folder.")
    return {
        "schema": SCHEMA,
        "root_label": root.name,
        "read_only": True,
        "artifact_count": len(artifacts),
        "total_bytes": total,
        "total_mib": round(total / (1024 * 1024), 2),
        "large_jit_dump_count": len(large_dumps),
        "large_log_count": len(large_logs),
        "artifacts": artifacts,
        "actions": actions,
        "rule": "Never delete the only copy of a crash artifact before the failure signature and relevant log evidence have been captured.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Read-only Madeira/HunieCam diagnostic storage audit")
    p.add_argument("root", type=pathlib.Path)
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    report = scan(args.root)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
