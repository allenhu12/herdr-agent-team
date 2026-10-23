#!/usr/bin/env python3
"""Show the installed herdr-agent-team version and whether its source is newer.

Usage: skill-version.py [--changes]

Reads metadata.version from this copy's SKILL.md. When the copy was
installed by OpenSkills, .openskills.json names the source folder; the
script reads that SKILL.md too and compares. --changes also prints this
version's CHANGELOG.md section. Exit 0 when current, 3 when the source
has another version, 1 when this copy has no version.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def version_of(root):
    path = root / "SKILL.md"
    if not path.exists():
        return None
    front = yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])
    return str((front.get("metadata") or {}).get("version") or "") or None


def changelog_section(root, version):
    path = root / "CHANGELOG.md"
    if not path.exists():
        return None
    match = re.search(rf"^## \[?{re.escape(version)}\]?.*?(?=^## |\Z)",
                      path.read_text(encoding="utf-8"), re.M | re.S)
    return match.group(0).strip() if match else None


def source_commit(root):
    run = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%h %ad %s", "--date=short"],
                         capture_output=True, text=True)
    return run.stdout.strip() if run.returncode == 0 else None


def main(argv):
    if len(argv) > 2 or (len(argv) == 2 and argv[1] != "--changes"):
        print(__doc__.strip(), file=sys.stderr)
        return 1
    installed = version_of(ROOT)
    print(f"herdr-agent-team version: {installed or 'unknown'}")
    print(f"location: {ROOT}")
    if not installed:
        return 1

    status = 0
    meta_path = ROOT / ".openskills.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        print(f"installed at: {meta.get('installedAt', 'unknown')}")
        source = Path(meta.get("localPath") or "")
        if meta.get("sourceType") == "local" and source.is_dir() and source.resolve() != ROOT:
            latest = version_of(source)
            commit = source_commit(source)
            print(f"source: {source}")
            print(f"source version: {latest or 'unknown'}" + (f" (last commit {commit})" if commit else ""))
            if latest == installed:
                print("status: up to date")
            else:
                print("status: source has another version; reinstall to update")
                status = 3
        else:
            print("source: not a local folder; cannot compare")
    else:
        print("source: this is the source copy (no .openskills.json)")

    if len(argv) == 2:
        section = changelog_section(ROOT, installed)
        print()
        print(section or f"CHANGELOG.md has no section for {installed}")
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
