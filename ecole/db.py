"""قاعدة البيانات: الاتصال وإنشاء الجداول والإعدادات الافتراضية."""

import os
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'reception')),
    must_change   INTEGER NOT NULL DEFAULT 0,
    active        INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS levels (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subjects (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS teachers (
    id         INTEGER PRIMARY KEY,
    full_name  TEXT NOT NULL,
    phone      TEXT NOT NULL DEFAULT '',
    notes      TEXT NOT NULL DEFAULT '',
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS groups (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id),
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    level_id   INTEGER NOT NULL REFERENCES levels(id),
    room       TEXT NOT NULL DEFAULT '',
    schedule   TEXT NOT NULL DEFAULT '',
    capacity   INTEGER NOT NULL DEFAULT 0,
    active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS students (
    id           INTEGER PRIMARY KEY,
    full_name    TEXT NOT NULL,
    phone        TEXT NOT NULL DEFAULT '',
    parent_phone TEXT NOT NULL DEFAULT '',
    level_id     INTEGER REFERENCES levels(id),
    notes        TEXT NOT NULL DEFAULT '',
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS group_students (
    group_id   INTEGER NOT NULL REFERENCES groups(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    joined_at  TEXT NOT NULL DEFAULT (date('now', 'localtime')),
    PRIMARY KEY (group_id, student_id)
);

-- كل دفعة تضيف عدداً من الحصص إلى رصيد التلميذ (صالحة لأي فوج أو مادة).
-- لا تحذف الدفعات أبداً: الدفعة الخاطئة تُلغى مع ذكر السبب.
CREATE TABLE IF NOT EXISTS payments (
    id            INTEGER PRIMARY KEY,
    receipt_no    TEXT NOT NULL UNIQUE,
    student_id    INTEGER NOT NULL REFERENCES students(id),
    paid_at       TEXT NOT NULL,
    amount        INTEGER NOT NULL CHECK (amount >= 0),
    sessions      INTEGER NOT NULL CHECK (sessions > 0),
    user_id       INTEGER REFERENCES users(id),
    cancelled     INTEGER NOT NULL DEFAULT 0,
    cancel_reason TEXT NOT NULL DEFAULT '',
    cancelled_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_payments_student ON payments(student_id);
CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(paid_at);

-- الحصة المنجزة لفوج في تاريخ معين.
CREATE TABLE IF NOT EXISTS lessons (
    id          INTEGER PRIMARY KEY,
    group_id    INTEGER NOT NULL REFERENCES groups(id),
    lesson_date TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    user_id     INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_lessons_group_date ON lessons(group_id, lesson_date);

-- الحاضر فقط يُخصم من رصيده. السعر يُحفظ مع كل حضور
-- حتى لا تتغير الحسابات القديمة إذا تغيّر سعر الحصة.
CREATE TABLE IF NOT EXISTS attendance (
    lesson_id  INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES students(id),
    present    INTEGER NOT NULL DEFAULT 0,
    price      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (lesson_id, student_id)
);
CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id);

CREATE TABLE IF NOT EXISTS teacher_payouts (
    id         INTEGER PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id),
    period     TEXT NOT NULL,
    amount     INTEGER NOT NULL,
    paid_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    user_id    INTEGER REFERENCES users(id),
    notes      TEXT NOT NULL DEFAULT '',
    UNIQUE (teacher_id, period)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id      INTEGER PRIMARY KEY,
    at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    user_id INTEGER,
    action  TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT ''
);
"""

DEFAULT_SETTINGS = {
    "academy_name": "أكاديمية الدروس الخصوصية",
    "academy_address": "",
    "academy_phone": "",
    "receipt_footer": "شكراً لثقتكم",
    "session_price": "500",
    "pack_sessions": "4",
    "pack_price": "2000",
    # نسبة الأكاديمية على شكل كسر (الثلث = 1/3) لتفادي أخطاء التقريب.
    "academy_share_num": "1",
    "academy_share_den": "3",
    "backup_dir": "",
    "backup_keep": "30",
}

DEFAULT_LEVELS = [
    "1 ابتدائي", "2 ابتدائي", "3 ابتدائي", "4 ابتدائي", "5 ابتدائي",
    "1 متوسط", "2 متوسط", "3 متوسط", "4 متوسط",
    "1 ثانوي", "2 ثانوي", "3 ثانوي",
]

DEFAULT_SUBJECTS = [
    "رياضيات", "فيزياء", "علوم طبيعية", "لغة عربية", "لغة فرنسية",
    "لغة إنجليزية", "فلسفة", "تاريخ وجغرافيا", "محاسبة",
]


def default_data_dir() -> Path:
    override = os.environ.get("ECOLE_DATA_DIR")
    if override:
        return Path(override)
    return Path.home() / "Documents" / "EcoleData"


def connect(path) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    with conn:
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value)
            )
        if conn.execute("SELECT COUNT(*) FROM levels").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO levels(name, sort_order) VALUES (?, ?)",
                [(name, i) for i, name in enumerate(DEFAULT_LEVELS)],
            )
        if conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO subjects(name) VALUES (?)", [(n,) for n in DEFAULT_SUBJECTS]
            )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
