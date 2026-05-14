"""
Backup/restore InsightPM's SQLite database.

The DB lives at ~/.insightpm/insightpm.db. It contains:
- All your saved BigQuery connection profiles (including service account JSON)
- All your saved funnels

If you lose this file, you lose all that work. This script copies it out to
a safe location with a timestamp suffix.

Usage:
    python -m app.backup backup [target_dir]
    python -m app.backup restore <backup_file>
    python -m app.backup list

Examples:
    python -m app.backup backup
        -> ~/.insightpm/backups/insightpm-20260425-143012.db

    python -m app.backup backup C:\\my-backups
        -> C:\\my-backups\\insightpm-20260425-143012.db

    python -m app.backup list
        Shows all backups currently in ~/.insightpm/backups/

    python -m app.backup restore ~/.insightpm/backups/insightpm-20260425-143012.db
        Restores from that backup. Current DB is moved to .pre-restore.db before
        overwriting, so it's recoverable if you change your mind.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def _db_path() -> Path:
    return Path.home() / ".insightpm" / "insightpm.db"


def _default_backup_dir() -> Path:
    p = Path.home() / ".insightpm" / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def cmd_backup(target_dir: Path | None = None) -> int:
    src = _db_path()
    if not src.exists():
        print(f"ERROR: No database found at {src}.")
        print("Either you haven't connected yet, or this is a fresh install.")
        return 1

    target = target_dir or _default_backup_dir()
    target.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_file = target / f"insightpm-{timestamp}.db"

    # Use sqlite3's backup API instead of file copy. Handles WAL/journal
    # cleanly even if the app is running.
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(out_file))
    try:
        src_conn.backup(dst_conn)
    finally:
        src_conn.close()
        dst_conn.close()

    size_kb = out_file.stat().st_size / 1024
    print(f"OK: Backed up to {out_file} ({size_kb:.1f} KB)")

    # Show summary of what's in the backup
    counts = _summarize(out_file)
    if counts:
        print(f"  - {counts['profiles']} connection profile(s)")
        print(f"  - {counts['funnels']} saved funnel(s)")
    return 0


def cmd_restore(backup_file: Path) -> int:
    if not backup_file.exists():
        print(f"ERROR: Backup file not found: {backup_file}")
        return 1

    # Sanity check: file is a valid SQLite DB
    try:
        conn = sqlite3.connect(str(backup_file))
        conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn.close()
    except sqlite3.DatabaseError as e:
        print(f"ERROR: {backup_file} doesn't look like a valid SQLite DB: {e}")
        return 1

    target = _db_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    # Save current DB as .pre-restore.db so this is reversible.
    if target.exists():
        safety = target.with_suffix(".pre-restore.db")
        shutil.copy2(target, safety)
        print(f"Existing DB moved to {safety} (you can manually restore it if needed)")

    shutil.copy2(backup_file, target)
    counts = _summarize(target)
    print(f"OK: Restored from {backup_file}")
    if counts:
        print(f"  - {counts['profiles']} connection profile(s)")
        print(f"  - {counts['funnels']} saved funnel(s)")
    print("Restart the InsightPM backend (uvicorn) for changes to take effect.")
    return 0


def cmd_list() -> int:
    backup_dir = _default_backup_dir()
    backups = sorted(backup_dir.glob("insightpm-*.db"), reverse=True)
    if not backups:
        print(f"No backups found in {backup_dir}")
        print("Run `python -m app.backup backup` to create one.")
        return 0
    print(f"Backups in {backup_dir}:")
    for b in backups:
        size_kb = b.stat().st_size / 1024
        ts = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  {b.name}  ({size_kb:.1f} KB, {ts})")
    return 0


def _summarize(db_file: Path) -> dict | None:
    try:
        conn = sqlite3.connect(str(db_file))
        prof = conn.execute("SELECT COUNT(*) FROM connection_profiles").fetchone()[0]
        funnels = conn.execute("SELECT COUNT(*) FROM saved_funnels").fetchone()[0]
        conn.close()
        return {"profiles": prof, "funnels": funnels}
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.backup")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_backup = sub.add_parser("backup", help="Save a copy of the DB")
    p_backup.add_argument("target_dir", nargs="?", type=Path,
                          help="Optional dir for the backup file (default: ~/.insightpm/backups/)")

    p_restore = sub.add_parser("restore", help="Restore from a backup file")
    p_restore.add_argument("backup_file", type=Path)

    sub.add_parser("list", help="Show available backups")

    args = parser.parse_args(argv)

    if args.cmd == "backup":
        return cmd_backup(args.target_dir)
    if args.cmd == "restore":
        return cmd_restore(args.backup_file)
    if args.cmd == "list":
        return cmd_list()
    return 1


if __name__ == "__main__":
    sys.exit(main())
