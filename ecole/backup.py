"""النسخ الاحتياطي لقاعدة البيانات واسترجاعها."""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

PREFIX = "ecole-backup-"


def make_backup(conn: sqlite3.Connection, target_dir, keep: int = 30) -> Path:
    """ينسخ قاعدة البيانات بأمان (حتى أثناء استعمالها) ويحتفظ بآخر `keep` نسخة."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target = target_dir / f"{PREFIX}{stamp}.db"
    dest = sqlite3.connect(str(target))
    try:
        conn.backup(dest)
    finally:
        dest.close()
    _prune(target_dir, keep)
    return target


def _prune(target_dir: Path, keep: int) -> None:
    if keep <= 0:
        return
    backups = sorted(target_dir.glob(f"{PREFIX}*.db"))
    for old in backups[:-keep]:
        old.unlink(missing_ok=True)


def is_valid_database(path) -> bool:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
            return {"students", "payments", "attendance"} <= tables
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def restore_backup(backup_path, db_path) -> None:
    """يستبدل قاعدة البيانات الحالية بنسخة احتياطية (يجب إغلاق الاتصال قبل ذلك)."""
    db_path = Path(db_path)
    if not is_valid_database(backup_path):
        raise ValueError("الملف المختار ليس نسخة احتياطية صالحة.")
    for suffix in ("-wal", "-shm"):
        Path(str(db_path) + suffix).unlink(missing_ok=True)
    shutil.copy2(backup_path, db_path)
