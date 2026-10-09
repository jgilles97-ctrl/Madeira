#!/usr/bin/env python3
"""Read-only fingerprint/compare helper for HunieCam Studio save data.

It never parses or uploads save contents. A snapshot records relative names,
sizes and SHA-256 hashes. A verification combines BEFORE, AFTER visible
progress, and AFTER FULL RELAUNCH so acceptance can prove both that the game
wrote progress and that the written tree survived the restart.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

SNAPSHOT_SCHEMA = "MADEIRA_HUNIECAM_SAVE_SNAPSHOT_V1"
COMPARE_SCHEMA = "MADEIRA_HUNIECAM_SAVE_COMPARE_V1"
VERIFY_SCHEMA = "MADEIRA_HUNIECAM_SAVE_VERIFY_V1"


def hash_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(root: pathlib.Path) -> dict[str, object]:
    root = root.expanduser().resolve()
    entries = []
    total = 0
    if root.is_dir():
        for p in sorted(root.rglob("*"), key=lambda x: x.as_posix().casefold()):
            if p.is_symlink() or not p.is_file():
                continue
            try:
                st = p.stat()
                rel = p.relative_to(root).as_posix()
                digest = hash_file(p)
            except OSError:
                continue
            total += st.st_size
            entries.append({"path": rel, "bytes": st.st_size, "sha256": digest})
    aggregate = hashlib.sha256()
    for item in entries:
        aggregate.update(str(item["path"]).encode("utf-8", errors="replace"))
        aggregate.update(b"\0")
        aggregate.update(str(item["bytes"]).encode("ascii"))
        aggregate.update(b"\0")
        aggregate.update(str(item["sha256"]).encode("ascii"))
        aggregate.update(b"\n")
    return {
        "schema": SNAPSHOT_SCHEMA,
        "source_label": root.name,
        "exists": root.is_dir(),
        "file_count": len(entries),
        "total_bytes": total,
        "tree_sha256": aggregate.hexdigest(),
        "files": entries,
    }


def compare(old: dict[str, object], new: dict[str, object]) -> dict[str, object]:
    old_files = {str(x["path"]): x for x in old.get("files", []) if isinstance(x, dict) and "path" in x}
    new_files = {str(x["path"]): x for x in new.get("files", []) if isinstance(x, dict) and "path" in x}
    added = sorted(set(new_files) - set(old_files))
    removed = sorted(set(old_files) - set(new_files))
    changed = sorted(
        p for p in set(old_files) & set(new_files)
        if old_files[p].get("sha256") != new_files[p].get("sha256") or old_files[p].get("bytes") != new_files[p].get("bytes")
    )
    unchanged = sorted(set(old_files) & set(new_files) - set(changed))
    return {
        "schema": COMPARE_SCHEMA,
        "changed": changed,
        "added": added,
        "removed": removed,
        "unchanged_count": len(unchanged),
        "progress_write_detected": bool(changed or added or removed),
        "same_tree": old.get("tree_sha256") == new.get("tree_sha256"),
        "old_tree_sha256": old.get("tree_sha256"),
        "new_tree_sha256": new.get("tree_sha256"),
    }


def verify(before: dict[str, object], after: dict[str, object], relaunch: dict[str, object]) -> dict[str, object]:
    write = compare(before, after)
    after_hash = after.get("tree_sha256")
    relaunch_hash = relaunch.get("tree_sha256")
    after_exists = bool(after.get("exists"))
    relaunch_exists = bool(relaunch.get("exists"))
    persisted = bool(after_exists and relaunch_exists and after_hash is not None and after_hash == relaunch_hash)
    return {
        "schema": VERIFY_SCHEMA,
        "progress_write_detected": bool(write["progress_write_detected"]),
        "write_compare": write,
        "after_tree_sha256": after_hash,
        "relaunch_tree_sha256": relaunch_hash,
        "after_file_count": after.get("file_count"),
        "relaunch_file_count": relaunch.get("file_count"),
        "save_tree_survived_relaunch": persisted,
        "machine_gate_pass": bool(write["progress_write_detected"] and persisted),
        "manual_gate_still_required": "Confirm inside the relaunched game that the same visible progress actually returned; matching files alone do not prove the game interpreted them correctly.",
    }


def load(path: pathlib.Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="HunieCam save fingerprint/persistence checker")
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("save_dir", type=pathlib.Path)
    snap.add_argument("--json", dest="json_path", type=pathlib.Path)
    comp = sub.add_parser("compare")
    comp.add_argument("before", type=pathlib.Path)
    comp.add_argument("after", type=pathlib.Path)
    comp.add_argument("--json", dest="json_path", type=pathlib.Path)
    ver = sub.add_parser("verify")
    ver.add_argument("before", type=pathlib.Path)
    ver.add_argument("after", type=pathlib.Path)
    ver.add_argument("relaunch", type=pathlib.Path)
    ver.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = parser.parse_args()

    if args.command == "snapshot":
        report = snapshot(args.save_dir)
    elif args.command == "compare":
        report = compare(load(args.before), load(args.after))
    else:
        report = verify(load(args.before), load(args.after), load(args.relaunch))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
