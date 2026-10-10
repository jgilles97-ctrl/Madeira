#!/usr/bin/env python3
"""Read-only fingerprint/compare helper for HunieCam Studio save data.

Cycle 6 binds all three persistence snapshots to one exact directory without
revealing its absolute path: the resolved path is SHA-256 hashed. This prevents
snapshots from different folders with similar contents from accidentally passing.
File contents are never parsed or embedded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

SNAPSHOT_SCHEMA = "MADEIRA_HUNIECAM_SAVE_SNAPSHOT_V2"
COMPARE_SCHEMA = "MADEIRA_HUNIECAM_SAVE_COMPARE_V2"
VERIFY_SCHEMA = "MADEIRA_HUNIECAM_SAVE_VERIFY_V2"
EXPECTED_SOURCE_LABEL = "HunieCam Studio"


def hash_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _path_hash(root: pathlib.Path) -> str:
    return hashlib.sha256(str(root).encode("utf-8", errors="replace")).hexdigest()


def snapshot(root: pathlib.Path) -> dict[str, object]:
    root = root.expanduser().resolve()
    entries: list[dict[str, Any]] = []
    total = 0
    if root.is_dir():
        for p in sorted(root.rglob("*"), key=lambda x: x.as_posix().casefold()):
            if p.is_symlink() or not p.is_file():
                continue
            try:
                st = p.stat(); rel = p.relative_to(root).as_posix(); digest = hash_file(p)
            except OSError:
                continue
            total += st.st_size
            entries.append({"path": rel, "bytes": st.st_size, "sha256": digest})
    aggregate = hashlib.sha256()
    for item in entries:
        aggregate.update(str(item["path"]).encode("utf-8", errors="replace")); aggregate.update(b"\0")
        aggregate.update(str(item["bytes"]).encode("ascii")); aggregate.update(b"\0")
        aggregate.update(str(item["sha256"]).encode("ascii")); aggregate.update(b"\n")
    return {
        "schema": SNAPSHOT_SCHEMA,
        "source_label": root.name,
        "source_path_sha256": _path_hash(root),
        "expected_title_folder": root.name == EXPECTED_SOURCE_LABEL,
        "exists": root.is_dir(),
        "file_count": len(entries),
        "total_bytes": total,
        "tree_sha256": aggregate.hexdigest(),
        "files": entries,
        "privacy": {"absolute_path_embedded": False, "file_contents_embedded": False},
    }


def _snapshot_errors(data: dict[str, object], name: str) -> list[str]:
    errors = []
    if data.get("schema") not in {"MADEIRA_HUNIECAM_SAVE_SNAPSHOT_V1", SNAPSHOT_SCHEMA}:
        errors.append(f"{name} has unsupported snapshot schema {data.get('schema')!r}.")
    if not data.get("source_label"):
        errors.append(f"{name} has no source label.")
    return errors


def compare(old: dict[str, object], new: dict[str, object]) -> dict[str, object]:
    errors = _snapshot_errors(old, "old") + _snapshot_errors(new, "new")
    old_path_hash = old.get("source_path_sha256")
    new_path_hash = new.get("source_path_sha256")
    if old_path_hash and new_path_hash and old_path_hash != new_path_hash:
        errors.append("Snapshots came from different resolved save directories.")
    if old.get("source_label") != new.get("source_label"):
        errors.append("Snapshot source labels differ.")
    old_files = {str(x["path"]): x for x in old.get("files", []) if isinstance(x, dict) and "path" in x}
    new_files = {str(x["path"]): x for x in new.get("files", []) if isinstance(x, dict) and "path" in x}
    added = sorted(set(new_files) - set(old_files)); removed = sorted(set(old_files) - set(new_files))
    changed = sorted(p for p in set(old_files) & set(new_files) if old_files[p].get("sha256") != new_files[p].get("sha256") or old_files[p].get("bytes") != new_files[p].get("bytes"))
    unchanged = sorted(set(old_files) & set(new_files) - set(changed))
    return {
        "schema": COMPARE_SCHEMA,
        "valid_comparison": not errors,
        "errors": errors,
        "changed": changed, "added": added, "removed": removed, "unchanged_count": len(unchanged),
        "progress_write_detected": bool(changed or added or removed) if not errors else False,
        "same_tree": old.get("tree_sha256") == new.get("tree_sha256"),
        "old_tree_sha256": old.get("tree_sha256"), "new_tree_sha256": new.get("tree_sha256"),
        "same_source_directory_proven": bool(old_path_hash and new_path_hash and old_path_hash == new_path_hash),
    }


def verify(before: dict[str, object], after: dict[str, object], relaunch: dict[str, object]) -> dict[str, object]:
    write = compare(before, after); persistence_compare = compare(after, relaunch)
    errors = list(dict.fromkeys([*write.get("errors", []), *persistence_compare.get("errors", [])]))
    path_hashes = {x.get("source_path_sha256") for x in (before, after, relaunch) if x.get("source_path_sha256")}
    labels = {x.get("source_label") for x in (before, after, relaunch)}
    if len(path_hashes) > 1: errors.append("BEFORE/AFTER/RELAUNCH snapshots do not come from one exact save directory.")
    if len(labels) > 1: errors.append("BEFORE/AFTER/RELAUNCH snapshot labels differ.")
    expected_folder = all(x.get("source_label") == EXPECTED_SOURCE_LABEL for x in (before, after, relaunch))
    if not expected_folder: errors.append(f"Save snapshots are not all from the expected '{EXPECTED_SOURCE_LABEL}' folder.")
    after_hash = after.get("tree_sha256"); relaunch_hash = relaunch.get("tree_sha256")
    persisted = bool(after.get("exists") and relaunch.get("exists") and after_hash is not None and after_hash == relaunch_hash and persistence_compare.get("valid_comparison"))
    write_detected = bool(write.get("progress_write_detected") and write.get("valid_comparison"))
    gate = bool(write_detected and persisted and not errors and len(path_hashes) == 1 and expected_folder)
    return {
        "schema": VERIFY_SCHEMA,
        "progress_write_detected": write_detected,
        "write_compare": write,
        "persistence_compare": persistence_compare,
        "after_tree_sha256": after_hash,
        "relaunch_tree_sha256": relaunch_hash,
        "after_file_count": after.get("file_count"),
        "relaunch_file_count": relaunch.get("file_count"),
        "same_source_directory_proven": len(path_hashes) == 1 and bool(path_hashes),
        "expected_save_folder_proven": expected_folder,
        "save_tree_survived_relaunch": persisted,
        "machine_gate_pass": gate,
        "errors": errors,
        "manual_gate_still_required": "Confirm inside the relaunched game that the same visible progress actually returned; matching files alone do not prove the game interpreted them correctly.",
    }


def load(path: pathlib.Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="HunieCam save fingerprint/persistence checker")
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot"); snap.add_argument("save_dir", type=pathlib.Path); snap.add_argument("--json", dest="json_path", type=pathlib.Path)
    comp = sub.add_parser("compare"); comp.add_argument("before", type=pathlib.Path); comp.add_argument("after", type=pathlib.Path); comp.add_argument("--json", dest="json_path", type=pathlib.Path)
    ver = sub.add_parser("verify"); ver.add_argument("before", type=pathlib.Path); ver.add_argument("after", type=pathlib.Path); ver.add_argument("relaunch", type=pathlib.Path); ver.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = parser.parse_args()
    report = snapshot(args.save_dir) if args.command == "snapshot" else compare(load(args.before), load(args.after)) if args.command == "compare" else verify(load(args.before), load(args.after), load(args.relaunch))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path: args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if not report.get("errors") else 2


if __name__ == "__main__": raise SystemExit(main())
