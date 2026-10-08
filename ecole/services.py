"""منطق العمل: كل العمليات على البيانات تمر من هنا (مستقلة عن الواجهة).

القواعد المالية:
- التلميذ يملك رصيداً من الحصص صالحاً لأي فوج أو مادة.
- الدفع يضيف حصصاً (حصة واحدة أو باقة)، والحضور يخصم حصة واحدة.
- الغائب لا يُخصم منه شيء.
- يُسمح بالحضور برصيد صفر، فيصبح الرصيد سالباً (دَين).
- كل حضور يولّد دخلاً بسعر الحصة يُقسم بين الأكاديمية (نسبة ثابتة) والأستاذ.
"""

import hashlib
import hmac
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime


class ServiceError(Exception):
    """خطأ موجّه للمستخدم (رسالته بالعربية)."""


@dataclass
class User:
    id: int
    username: str
    full_name: str
    role: str
    must_change: bool

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return date.today().isoformat()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    expected = hash_password(password, bytes.fromhex(salt_hex)).split("$", 1)[1]
    return hmac.compare_digest(expected, digest_hex)


def _round_half_up_div(numerator: int, denominator: int) -> int:
    return (2 * numerator + denominator) // (2 * denominator)


class Store:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.user: User | None = None
        self.ensure_default_admin()

    # ------------------------------------------------------------------ عام
    def _log(self, action: str, details: str = "") -> None:
        self.conn.execute(
            "INSERT INTO audit_log(user_id, action, details) VALUES (?, ?, ?)",
            (self.user.id if self.user else None, action, details),
        )

    def _require_admin(self) -> None:
        if self.user is not None and not self.user.is_admin:
            raise ServiceError("هذه العملية مسموحة للمدير فقط.")

    # ------------------------------------------------------------ الإعدادات
    def settings(self) -> dict:
        return {r["key"]: r["value"] for r in self.conn.execute("SELECT key, value FROM settings")}

    def setting_int(self, key: str) -> int:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return int(row["value"]) if row else 0

    def save_settings(self, values: dict) -> None:
        self._require_admin()
        for key in ("session_price", "pack_sessions", "pack_price",
                    "academy_share_num", "academy_share_den"):
            if key in values:
                try:
                    if int(values[key]) < 0:
                        raise ValueError
                except ValueError:
                    raise ServiceError("القيم المالية يجب أن تكون أعداداً صحيحة موجبة.")
        if "academy_share_den" in values and int(values["academy_share_den"]) == 0:
            raise ServiceError("مقام نسبة الأكاديمية لا يمكن أن يكون صفراً.")
        with self.conn:
            for key, value in values.items():
                self.conn.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value)),
                )
            self._log("تعديل الإعدادات")

    def split_income(self, total: int) -> tuple[int, int]:
        """يقسم مبلغاً بين الأكاديمية والأستاذ: (حصة الأكاديمية، صافي الأستاذ)."""
        num = self.setting_int("academy_share_num")
        den = self.setting_int("academy_share_den") or 1
        academy = _round_half_up_div(total * num, den)
        return academy, total - academy

    # ------------------------------------------------------------ المستخدمون
    def ensure_default_admin(self) -> None:
        if self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO users(username, full_name, password_hash, role, must_change) "
                    "VALUES ('admin', 'المدير', ?, 'admin', 1)",
                    (hash_password("admin"),),
                )

    def authenticate(self, username: str, password: str) -> User | None:
        row = self.conn.execute(
            "SELECT * FROM users WHERE username = ? AND active = 1", (username.strip(),)
        ).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            return None
        self.user = User(row["id"], row["username"], row["full_name"], row["role"],
                         bool(row["must_change"]))
        with self.conn:
            self._log("تسجيل الدخول")
        return self.user

    def change_password(self, user_id: int, new_password: str) -> None:
        if len(new_password) < 4:
            raise ServiceError("كلمة السر يجب أن تحتوي على 4 أحرف على الأقل.")
        if self.user and self.user.id != user_id:
            self._require_admin()
        with self.conn:
            self.conn.execute(
                "UPDATE users SET password_hash = ?, must_change = 0 WHERE id = ?",
                (hash_password(new_password), user_id),
            )
            self._log("تغيير كلمة السر", str(user_id))
        if self.user and self.user.id == user_id:
            self.user.must_change = False

    def list_users(self):
        return self.conn.execute(
            "SELECT id, username, full_name, role, active FROM users ORDER BY id"
        ).fetchall()

    def save_user(self, data: dict) -> int:
        self._require_admin()
        username = data.get("username", "").strip()
        if not username:
            raise ServiceError("اسم المستخدم مطلوب.")
        if data.get("role") not in ("admin", "reception"):
            raise ServiceError("الصلاحية غير صحيحة.")
        try:
            with self.conn:
                if data.get("id"):
                    self.conn.execute(
                        "UPDATE users SET username=?, full_name=?, role=?, active=? WHERE id=?",
                        (username, data.get("full_name", ""), data["role"],
                         int(data.get("active", 1)), data["id"]),
                    )
                    user_id = data["id"]
                else:
                    password = data.get("password", "")
                    if len(password) < 4:
                        raise ServiceError("كلمة السر يجب أن تحتوي على 4 أحرف على الأقل.")
                    cur = self.conn.execute(
                        "INSERT INTO users(username, full_name, password_hash, role, must_change) "
                        "VALUES (?, ?, ?, ?, 1)",
                        (username, data.get("full_name", ""), hash_password(password),
                         data["role"]),
                    )
                    user_id = cur.lastrowid
                admins = self.conn.execute(
                    "SELECT COUNT(*) FROM users WHERE role='admin' AND active=1"
                ).fetchone()[0]
                if admins == 0:
                    raise ServiceError("يجب أن يبقى مدير واحد نشط على الأقل.")
                self._log("حفظ مستخدم", username)
        except sqlite3.IntegrityError:
            raise ServiceError("اسم المستخدم موجود مسبقاً.")
        return user_id

    # ------------------------------------------------- المستويات والمواد
    def list_levels(self):
        return self.conn.execute("SELECT * FROM levels ORDER BY sort_order, id").fetchall()

    def list_subjects(self):
        return self.conn.execute("SELECT * FROM subjects ORDER BY name").fetchall()

    def _save_named(self, table: str, item_id, name: str) -> int:
        name = name.strip()
        if not name:
            raise ServiceError("الاسم مطلوب.")
        try:
            with self.conn:
                if item_id:
                    self.conn.execute(f"UPDATE {table} SET name = ? WHERE id = ?", (name, item_id))
                    return item_id
                if table == "levels":
                    order = self.conn.execute(
                        "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM levels").fetchone()[0]
                    cur = self.conn.execute(
                        "INSERT INTO levels(name, sort_order) VALUES (?, ?)", (name, order))
                else:
                    cur = self.conn.execute(f"INSERT INTO {table}(name) VALUES (?)", (name,))
                return cur.lastrowid
        except sqlite3.IntegrityError:
            raise ServiceError("هذا الاسم موجود مسبقاً.")

    def save_level(self, level_id, name: str) -> int:
        return self._save_named("levels", level_id, name)

    def save_subject(self, subject_id, name: str) -> int:
        return self._save_named("subjects", subject_id, name)

    def delete_level(self, level_id: int) -> None:
        used = self.conn.execute(
            "SELECT (SELECT COUNT(*) FROM groups WHERE level_id = ?) + "
            "(SELECT COUNT(*) FROM students WHERE level_id = ?)", (level_id, level_id)
        ).fetchone()[0]
        if used:
            raise ServiceError("لا يمكن حذف مستوى مستعمل في أفواج أو تلاميذ.")
        with self.conn:
            self.conn.execute("DELETE FROM levels WHERE id = ?", (level_id,))

    def delete_subject(self, subject_id: int) -> None:
        used = self.conn.execute(
            "SELECT COUNT(*) FROM groups WHERE subject_id = ?", (subject_id,)).fetchone()[0]
        if used:
            raise ServiceError("لا يمكن حذف مادة مستعملة في أفواج.")
        with self.conn:
            self.conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))

    # ------------------------------------------------------------ الأساتذة
    def list_teachers(self, active_only: bool = False, search: str = ""):
        sql = """
            SELECT t.*,
                   (SELECT COUNT(*) FROM groups g WHERE g.teacher_id = t.id AND g.active = 1)
                       AS groups_count,
                   (SELECT GROUP_CONCAT(DISTINCT sub.name) FROM groups g
                      JOIN subjects sub ON sub.id = g.subject_id
                     WHERE g.teacher_id = t.id AND g.active = 1) AS subjects
              FROM teachers t WHERE 1 = 1"""
        params: list = []
        if active_only:
            sql += " AND t.active = 1"
        if search:
            sql += " AND (t.full_name LIKE ? OR t.phone LIKE ?)"
            params += [f"%{search}%", f"%{search}%"]
        return self.conn.execute(sql + " ORDER BY t.active DESC, t.full_name", params).fetchall()

    def get_teacher(self, teacher_id: int):
        return self.conn.execute("SELECT * FROM teachers WHERE id = ?", (teacher_id,)).fetchone()

    def save_teacher(self, data: dict) -> int:
        name = data.get("full_name", "").strip()
        if not name:
            raise ServiceError("اسم الأستاذ مطلوب.")
        values = (name, data.get("phone", "").strip(), data.get("notes", ""),
                  int(data.get("active", 1)))
        with self.conn:
            if data.get("id"):
                self.conn.execute(
                    "UPDATE teachers SET full_name=?, phone=?, notes=?, active=? WHERE id=?",
                    values + (data["id"],))
                teacher_id = data["id"]
            else:
                teacher_id = self.conn.execute(
                    "INSERT INTO teachers(full_name, phone, notes, active) VALUES (?,?,?,?)",
                    values).lastrowid
            self._log("حفظ أستاذ", name)
        return teacher_id

    # ------------------------------------------------------------ الأفواج
    _GROUP_SELECT = """
        SELECT g.*, t.full_name AS teacher_name, sub.name AS subject_name,
               l.name AS level_name,
               (SELECT COUNT(*) FROM group_students gs WHERE gs.group_id = g.id) AS members
          FROM groups g
          JOIN teachers t ON t.id = g.teacher_id
          JOIN subjects sub ON sub.id = g.subject_id
          JOIN levels l ON l.id = g.level_id
    """

    def list_groups(self, active_only: bool = False, teacher_id: int | None = None,
                    search: str = ""):
        sql = self._GROUP_SELECT + " WHERE 1 = 1"
        params: list = []
        if active_only:
            sql += " AND g.active = 1"
        if teacher_id:
            sql += " AND g.teacher_id = ?"
            params.append(teacher_id)
        if search:
            sql += " AND (g.name LIKE ? OR t.full_name LIKE ? OR sub.name LIKE ? OR l.name LIKE ?)"
            params += [f"%{search}%"] * 4
        sql += " ORDER BY g.active DESC, l.sort_order, sub.name, g.name"
        return self.conn.execute(sql, params).fetchall()

    def get_group(self, group_id: int):
        return self.conn.execute(self._GROUP_SELECT + " WHERE g.id = ?", (group_id,)).fetchone()

    def save_group(self, data: dict) -> int:
        name = data.get("name", "").strip()
        if not name:
            raise ServiceError("اسم الفوج مطلوب.")
        for key, label in (("teacher_id", "الأستاذ"), ("subject_id", "المادة"),
                           ("level_id", "المستوى")):
            if not data.get(key):
                raise ServiceError(f"يجب اختيار {label}.")
        values = (name, data["teacher_id"], data["subject_id"], data["level_id"],
                  data.get("room", "").strip(), data.get("schedule", "").strip(),
                  int(data.get("capacity") or 0), int(data.get("active", 1)))
        with self.conn:
            if data.get("id"):
                self.conn.execute(
                    "UPDATE groups SET name=?, teacher_id=?, subject_id=?, level_id=?, room=?, "
                    "schedule=?, capacity=?, active=? WHERE id=?", values + (data["id"],))
                group_id = data["id"]
            else:
                group_id = self.conn.execute(
                    "INSERT INTO groups(name, teacher_id, subject_id, level_id, room, schedule, "
                    "capacity, active) VALUES (?,?,?,?,?,?,?,?)", values).lastrowid
            self._log("حفظ فوج", name)
        return group_id

    def group_member_ids(self, group_id: int) -> set[int]:
        rows = self.conn.execute(
            "SELECT student_id FROM group_students WHERE group_id = ?", (group_id,))
        return {r[0] for r in rows}

    def set_group_members(self, group_id: int, student_ids) -> None:
        new = set(student_ids)
        old = self.group_member_ids(group_id)
        with self.conn:
            for sid in old - new:
                self.conn.execute(
                    "DELETE FROM group_students WHERE group_id = ? AND student_id = ?",
                    (group_id, sid))
            for sid in new - old:
                self.conn.execute(
                    "INSERT INTO group_students(group_id, student_id) VALUES (?, ?)",
                    (group_id, sid))
            self._log("تعديل تلاميذ الفوج", f"فوج {group_id}: +{len(new - old)} -{len(old - new)}")

    def add_group_member(self, group_id: int, student_id: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO group_students(group_id, student_id) VALUES (?, ?)",
                (group_id, student_id))

    # ------------------------------------------------------------ التلاميذ
    _BALANCE_SQL = """
        COALESCE((SELECT SUM(p.sessions) FROM payments p
                   WHERE p.student_id = s.id AND p.cancelled = 0), 0)
      + COALESCE((SELECT SUM(b.sessions) FROM balance_adjustments b
                   WHERE b.student_id = s.id), 0)
      - COALESCE((SELECT COUNT(*) FROM attendance a
                   WHERE a.student_id = s.id AND a.present = 1), 0)
    """

    def list_students(self, search: str = "", active_only: bool = False,
                      level_id: int | None = None, only_debtors: bool = False):
        sql = f"""
            SELECT s.*, l.name AS level_name, ({self._BALANCE_SQL}) AS balance,
                   (SELECT GROUP_CONCAT(sub.name, '، ') FROM group_students gs
                      JOIN groups g ON g.id = gs.group_id
                      JOIN subjects sub ON sub.id = g.subject_id
                     WHERE gs.student_id = s.id AND g.active = 1) AS subjects
              FROM students s LEFT JOIN levels l ON l.id = s.level_id
             WHERE 1 = 1"""
        params: list = []
        if search:
            sql += " AND (s.full_name LIKE ? OR s.phone LIKE ? OR s.parent_phone LIKE ? OR s.id = ?)"
            params += [f"%{search}%"] * 3 + [search if search.isdigit() else -1]
        if active_only:
            sql += " AND s.active = 1"
        if level_id:
            sql += " AND s.level_id = ?"
            params.append(level_id)
        if only_debtors:
            sql += f" AND ({self._BALANCE_SQL}) < 0"
        sql += " ORDER BY s.active DESC, s.full_name"
        return self.conn.execute(sql, params).fetchall()

    def get_student(self, student_id: int):
        return self.conn.execute(
            f"SELECT s.*, l.name AS level_name, ({self._BALANCE_SQL}) AS balance "
            "FROM students s LEFT JOIN levels l ON l.id = s.level_id WHERE s.id = ?",
            (student_id,)).fetchone()

    def student_balance(self, student_id: int) -> int:
        row = self.conn.execute(
            f"SELECT ({self._BALANCE_SQL}) FROM students s WHERE s.id = ?", (student_id,)
        ).fetchone()
        return row[0] if row else 0

    def save_student(self, data: dict) -> int:
        name = data.get("full_name", "").strip()
        if not name:
            raise ServiceError("اسم التلميذ مطلوب.")
        values = (name, data.get("phone", "").strip(), data.get("parent_phone", "").strip(),
                  data.get("level_id") or None, data.get("notes", ""),
                  int(data.get("active", 1)))
        with self.conn:
            if data.get("id"):
                self.conn.execute(
                    "UPDATE students SET full_name=?, phone=?, parent_phone=?, level_id=?, "
                    "notes=?, active=? WHERE id=?", values + (data["id"],))
                student_id = data["id"]
            else:
                student_id = self.conn.execute(
                    "INSERT INTO students(full_name, phone, parent_phone, level_id, notes, active) "
                    "VALUES (?,?,?,?,?,?)", values).lastrowid
            self._log("حفظ تلميذ", name)
        return student_id

    def add_balance_adjustment(self, student_id: int, sessions: int, reason: str) -> None:
        """يضيف (أو يُنقص إن كان سالباً) حصصاً لرصيد التلميذ دون تسجيل مبلغ مقبوض."""
        if sessions == 0:
            return
        with self.conn:
            self.conn.execute(
                "INSERT INTO balance_adjustments(student_id, sessions, reason, user_id) "
                "VALUES (?, ?, ?, ?)",
                (student_id, sessions, reason, self.user.id if self.user else None))
            self._log("تعديل الرصيد", f"تلميذ {student_id}: {sessions:+d} ({reason})")

    def student_groups(self, student_id: int):
        return self.conn.execute(
            self._GROUP_SELECT +
            " JOIN group_students gs ON gs.group_id = g.id WHERE gs.student_id = ? "
            "ORDER BY sub.name", (student_id,)).fetchall()

    def set_student_groups(self, student_id: int, group_ids) -> None:
        new = set(group_ids)
        old = {g["id"] for g in self.student_groups(student_id)}
        with self.conn:
            for gid in old - new:
                self.conn.execute(
                    "DELETE FROM group_students WHERE group_id = ? AND student_id = ?",
                    (gid, student_id))
            for gid in new - old:
                self.conn.execute(
                    "INSERT INTO group_students(group_id, student_id) VALUES (?, ?)",
                    (gid, student_id))

    def student_statement(self, student_id: int) -> list[dict]:
        """كشف حساب التلميذ: الدفعات والحضور مرتبة زمنياً مع الرصيد التراكمي."""
        events: list[dict] = []
        for p in self.conn.execute(
                "SELECT * FROM payments WHERE student_id = ? ORDER BY paid_at", (student_id,)):
            label = f"دفع - وصل رقم {p['receipt_no']}"
            if p["cancelled"]:
                label += f" (ملغى: {p['cancel_reason']})"
            events.append({
                "date": p["paid_at"], "label": label, "amount": p["amount"],
                "change": 0 if p["cancelled"] else p["sessions"], "cancelled": bool(p["cancelled"]),
                "receipt_no": p["receipt_no"],
            })
        for a in self.conn.execute("""
                SELECT a.present, l.lesson_date, l.created_at, g.name AS group_name,
                       sub.name AS subject_name, t.full_name AS teacher_name
                  FROM attendance a
                  JOIN lessons l ON l.id = a.lesson_id
                  JOIN groups g ON g.id = l.group_id
                  JOIN subjects sub ON sub.id = g.subject_id
                  JOIN teachers t ON t.id = g.teacher_id
                 WHERE a.student_id = ?""", (student_id,)):
            state = "حضور" if a["present"] else "غياب"
            events.append({
                "date": a["lesson_date"] + " " + a["created_at"][11:],
                "label": f"{state} - {a['subject_name']} ({a['group_name']}) - {a['teacher_name']}",
                "amount": 0, "change": -1 if a["present"] else 0, "cancelled": False,
                "receipt_no": None,
            })
        for b in self.conn.execute(
                "SELECT * FROM balance_adjustments WHERE student_id = ?", (student_id,)):
            events.append({
                "date": b["created_at"], "label": f"تعديل الرصيد - {b['reason']}",
                "amount": 0, "change": b["sessions"], "cancelled": False, "receipt_no": None,
            })
        # عند تساوي الوقت: تعديل الرصيد ثم الدفع ثم الحضور.
        order = {"تعديل": 0, "دفع": 1}
        events.sort(key=lambda e: (e["date"], order.get(e["label"].split(" ", 1)[0], 2)))
        running = 0
        for e in events:
            running += e["change"]
            e["balance"] = running
        return events

    # ------------------------------------------------------------ المدفوعات
    def _next_receipt_no(self, year: int) -> str:
        row = self.conn.execute(
            "SELECT MAX(CAST(SUBSTR(receipt_no, 6) AS INTEGER)) FROM payments "
            "WHERE receipt_no LIKE ?", (f"{year}-%",)).fetchone()
        return f"{year}-{(row[0] or 0) + 1:05d}"

    def payment_options(self) -> dict:
        price = self.setting_int("session_price")
        return {
            "session_price": price,
            "pack_sessions": self.setting_int("pack_sessions"),
            "pack_price": self.setting_int("pack_price"),
        }

    def create_payment(self, student_id: int, kind: str, count: int = 1):
        """kind: 'single' (حصة واحدة) أو 'pack' (باقة) أو 'custom' (عدد حصص × السعر).

        count: عدد الحصص الفردية أو عدد الباقات حسب النوع.
        """
        if count < 1:
            raise ServiceError("العدد يجب أن يكون 1 على الأقل.")
        opts = self.payment_options()
        if kind == "pack":
            sessions, amount = opts["pack_sessions"] * count, opts["pack_price"] * count
        elif kind in ("single", "custom"):
            sessions, amount = count, opts["session_price"] * count
        else:
            raise ServiceError("نوع الدفع غير معروف.")
        if self.get_student(student_id) is None:
            raise ServiceError("التلميذ غير موجود.")
        paid_at = now_str()
        with self.conn:
            receipt_no = self._next_receipt_no(int(paid_at[:4]))
            pid = self.conn.execute(
                "INSERT INTO payments(receipt_no, student_id, paid_at, amount, sessions, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (receipt_no, student_id, paid_at, amount, sessions,
                 self.user.id if self.user else None)).lastrowid
            self._log("دفع", f"وصل {receipt_no}: {amount} دج / {sessions} حصص")
        return self.get_payment(pid)

    def get_payment(self, payment_id: int):
        return self.conn.execute("""
            SELECT p.*, s.full_name AS student_name, l.name AS level_name,
                   u.full_name AS user_name
              FROM payments p
              JOIN students s ON s.id = p.student_id
              LEFT JOIN levels l ON l.id = s.level_id
              LEFT JOIN users u ON u.id = p.user_id
             WHERE p.id = ?""", (payment_id,)).fetchone()

    def cancel_payment(self, payment_id: int, reason: str) -> None:
        self._require_admin()
        reason = reason.strip()
        if not reason:
            raise ServiceError("يجب ذكر سبب الإلغاء.")
        p = self.get_payment(payment_id)
        if p is None:
            raise ServiceError("الدفعة غير موجودة.")
        if p["cancelled"]:
            raise ServiceError("هذه الدفعة ملغاة مسبقاً.")
        with self.conn:
            self.conn.execute(
                "UPDATE payments SET cancelled = 1, cancel_reason = ?, cancelled_at = ? "
                "WHERE id = ?", (reason, now_str(), payment_id))
            self._log("إلغاء دفعة", f"وصل {p['receipt_no']}: {reason}")

    def list_payments(self, date_from: str, date_to: str, search: str = ""):
        sql = """
            SELECT p.*, s.full_name AS student_name, u.full_name AS user_name
              FROM payments p
              JOIN students s ON s.id = p.student_id
              LEFT JOIN users u ON u.id = p.user_id
             WHERE date(p.paid_at) BETWEEN ? AND ?"""
        params: list = [date_from, date_to]
        if search:
            sql += " AND (s.full_name LIKE ? OR p.receipt_no LIKE ?)"
            params += [f"%{search}%"] * 2
        return self.conn.execute(sql + " ORDER BY p.paid_at DESC", params).fetchall()

    # ------------------------------------------------------- الحصص والحضور
    def lessons_for(self, group_id: int, lesson_date: str):
        return self.conn.execute(
            "SELECT * FROM lessons WHERE group_id = ? AND lesson_date = ? ORDER BY id",
            (group_id, lesson_date)).fetchall()

    def get_or_create_lesson(self, group_id: int, lesson_date: str) -> int:
        existing = self.lessons_for(group_id, lesson_date)
        if existing:
            return existing[0]["id"]
        return self.create_lesson(group_id, lesson_date)

    def create_lesson(self, group_id: int, lesson_date: str) -> int:
        with self.conn:
            return self.conn.execute(
                "INSERT INTO lessons(group_id, lesson_date, user_id) VALUES (?, ?, ?)",
                (group_id, lesson_date, self.user.id if self.user else None)).lastrowid

    def get_lesson(self, lesson_id: int):
        return self.conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()

    def delete_lesson(self, lesson_id: int) -> None:
        self._require_admin()
        with self.conn:
            self.conn.execute("DELETE FROM attendance WHERE lesson_id = ?", (lesson_id,))
            self.conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
            self._log("حذف حصة", str(lesson_id))

    def attendance_sheet(self, lesson_id: int) -> list[dict]:
        """تلاميذ الفوج + من سُجّل حضوره من خارج الفوج، مع حالة الحضور والرصيد."""
        lesson = self.get_lesson(lesson_id)
        rows = self.conn.execute(f"""
            SELECT s.id, s.full_name, s.parent_phone, l.name AS level_name,
                   a.present, ({self._BALANCE_SQL}) AS balance,
                   EXISTS(SELECT 1 FROM group_students gs
                           WHERE gs.group_id = ? AND gs.student_id = s.id) AS is_member
              FROM students s
              LEFT JOIN levels l ON l.id = s.level_id
              LEFT JOIN attendance a ON a.student_id = s.id AND a.lesson_id = ?
             WHERE s.id IN (SELECT student_id FROM group_students WHERE group_id = ?)
                OR s.id IN (SELECT student_id FROM attendance WHERE lesson_id = ?)
             ORDER BY s.full_name""",
            (lesson["group_id"], lesson_id, lesson["group_id"], lesson_id)).fetchall()
        return [dict(r) | {"present": bool(r["present"]), "recorded": r["present"] is not None}
                for r in rows]

    def attendance_for(self, group_id: int, lesson_date: str) -> tuple[int | None, list[dict]]:
        """ورقة الحضور لفوج في تاريخ. لا تُنشأ الحصة إلا عند الحفظ."""
        lessons = self.lessons_for(group_id, lesson_date)
        if lessons:
            return lessons[0]["id"], self.attendance_sheet(lessons[0]["id"])
        rows = self.conn.execute(f"""
            SELECT s.id, s.full_name, s.parent_phone, l.name AS level_name,
                   ({self._BALANCE_SQL}) AS balance
              FROM students s
              JOIN group_students gs ON gs.student_id = s.id AND gs.group_id = ?
              LEFT JOIN levels l ON l.id = s.level_id
             WHERE s.active = 1
             ORDER BY s.full_name""", (group_id,)).fetchall()
        return None, [dict(r) | {"present": False, "recorded": False, "is_member": True}
                      for r in rows]

    def save_attendance(self, lesson_id: int, presence: dict[int, bool]) -> None:
        """presence: {رقم التلميذ: حاضر؟}. الحاضر يُخصم من رصيده بسعر الحصة الحالي."""
        price = self.setting_int("session_price")
        with self.conn:
            for student_id, present in presence.items():
                old = self.conn.execute(
                    "SELECT present, price FROM attendance WHERE lesson_id = ? AND student_id = ?",
                    (lesson_id, student_id)).fetchone()
                if present:
                    # إن كان حاضراً من قبل نحتفظ بسعره الأصلي.
                    keep = old["price"] if old is not None and old["present"] else price
                    new_price = keep
                else:
                    new_price = 0
                self.conn.execute(
                    "INSERT INTO attendance(lesson_id, student_id, present, price) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT(lesson_id, student_id) DO UPDATE SET "
                    "present = excluded.present, price = excluded.price",
                    (lesson_id, student_id, int(present), new_price))
            present_count = sum(1 for v in presence.values() if v)
            self._log("تسجيل الحضور", f"حصة {lesson_id}: {present_count} حاضر")

    def lessons_between(self, date_from: str, date_to: str, group_id: int | None = None):
        sql = """
            SELECT le.*, g.name AS group_name, sub.name AS subject_name,
                   t.full_name AS teacher_name, lv.name AS level_name,
                   (SELECT COUNT(*) FROM attendance a WHERE a.lesson_id = le.id AND a.present = 1)
                       AS present_count,
                   (SELECT COUNT(*) FROM attendance a WHERE a.lesson_id = le.id AND a.present = 0)
                       AS absent_count
              FROM lessons le
              JOIN groups g ON g.id = le.group_id
              JOIN subjects sub ON sub.id = g.subject_id
              JOIN teachers t ON t.id = g.teacher_id
              JOIN levels lv ON lv.id = g.level_id
             WHERE le.lesson_date BETWEEN ? AND ?"""
        params: list = [date_from, date_to]
        if group_id:
            sql += " AND le.group_id = ?"
            params.append(group_id)
        return self.conn.execute(sql + " ORDER BY le.lesson_date DESC, le.id DESC",
                                 params).fetchall()

    # ------------------------------------------------------------ التقارير
    @staticmethod
    def month_range(period: str) -> tuple[str, str]:
        year, month = (int(x) for x in period.split("-"))
        start = date(year, month, 1)
        end = date(year + (month == 12), month % 12 + 1, 1)
        return start.isoformat(), date.fromordinal(end.toordinal() - 1).isoformat()

    def teachers_summary(self, date_from: str, date_to: str) -> list[dict]:
        """حصيلة كل أستاذ بين تاريخين: الحصص، الحضور، المجموع، نصيب الأكاديمية، صافي الأستاذ."""
        rows = self.conn.execute("""
            SELECT t.id, t.full_name,
                   COUNT(DISTINCT le.id) AS lessons,
                   COALESCE(SUM(a.present), 0) AS attendances,
                   COALESCE(SUM(CASE WHEN a.present = 1 THEN a.price END), 0) AS total
              FROM teachers t
              JOIN groups g ON g.teacher_id = t.id
              JOIN lessons le ON le.group_id = g.id AND le.lesson_date BETWEEN ? AND ?
              LEFT JOIN attendance a ON a.lesson_id = le.id
             GROUP BY t.id ORDER BY t.full_name""", (date_from, date_to)).fetchall()
        result = []
        for r in rows:
            academy, net = self.split_income(r["total"])
            result.append({
                "teacher_id": r["id"], "teacher_name": r["full_name"], "lessons": r["lessons"],
                "attendances": r["attendances"], "total": r["total"], "academy": academy,
                "net": net,
            })
        return result

    def teachers_statement(self, period: str) -> list[dict]:
        """كشف شهري (شهر ميلادي) لكل الأساتذة. period بصيغة YYYY-MM."""
        start, end = self.month_range(period)
        payouts = {r["teacher_id"]: r for r in self.conn.execute(
            "SELECT * FROM teacher_payouts WHERE period = ?", (period,))}
        result = self.teachers_summary(start, end)
        for r in result:
            payout = payouts.get(r["teacher_id"])
            r["paid"] = payout["amount"] if payout else None
            r["paid_at"] = payout["paid_at"] if payout else None
        return result

    # ------------------------------------------------- فترات الحساب (الرواتب)
    PERIOD_WEEKS = 4

    @staticmethod
    def _add_days(day: str, n: int) -> str:
        return date.fromordinal(date.fromisoformat(day).toordinal() + n).isoformat()

    def _period_dict(self, row) -> dict:
        p = dict(row)
        last = p["end_date"] or max(today_str(), p["start_date"])
        p["days"] = (date.fromisoformat(last) - date.fromisoformat(p["start_date"])).days + 1
        p["is_open"] = p["end_date"] is None
        p["due"] = p["is_open"] and p["days"] > self.PERIOD_WEEKS * 7
        return p

    def current_period(self) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM pay_periods WHERE end_date IS NULL ORDER BY id DESC LIMIT 1").fetchone()
        return self._period_dict(row) if row else None

    def list_periods(self) -> list[dict]:
        return [self._period_dict(r) for r in self.conn.execute(
            "SELECT * FROM pay_periods ORDER BY start_date DESC, id DESC")]

    def get_period(self, period_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM pay_periods WHERE id = ?", (period_id,)).fetchone()
        return self._period_dict(row) if row else None

    def start_first_period(self, start_date: str) -> int:
        """أول «بداية حساب»: تُستعمل مرة واحدة عندما لا توجد أي فترة."""
        self._require_admin()
        if self.conn.execute("SELECT COUNT(*) FROM pay_periods").fetchone()[0]:
            raise ServiceError("الحساب بدأ مسبقاً. استعمل «بداية الحساب» لإغلاق الفترة الحالية.")
        with self.conn:
            pid = self.conn.execute(
                "INSERT INTO pay_periods(start_date, user_id) VALUES (?, ?)",
                (start_date, self.user.id if self.user else None)).lastrowid
            self._log("بداية الحساب", f"من {start_date}")
        return pid

    def close_period(self, end_date: str) -> int:
        """يغلق الفترة الحالية في end_date (يدخل فيها)، يسجّل رواتب الأساتذة، ويفتح فترة جديدة."""
        self._require_admin()
        period = self.current_period()
        if period is None:
            raise ServiceError("لا توجد فترة مفتوحة.")
        if end_date < period["start_date"]:
            raise ServiceError("تاريخ نهاية الفترة قبل تاريخ بدايتها.")
        summary = self.teachers_summary(period["start_date"], end_date)
        with self.conn:
            for r in summary:
                self.conn.execute(
                    "INSERT INTO period_payouts(period_id, teacher_id, lessons, attendances, "
                    "total, academy, amount) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (period["id"], r["teacher_id"], r["lessons"], r["attendances"], r["total"],
                     r["academy"], r["net"]))
            self.conn.execute(
                "UPDATE pay_periods SET end_date = ?, closed_at = ? WHERE id = ?",
                (end_date, now_str(), period["id"]))
            self.conn.execute(
                "INSERT INTO pay_periods(start_date, user_id) VALUES (?, ?)",
                (self._add_days(end_date, 1), self.user.id if self.user else None))
            total = sum(r["net"] for r in summary)
            self._log("دفع رواتب الأساتذة وبداية حساب جديد",
                      f"الفترة {period['start_date']} إلى {end_date}: {total} دج")
        return period["id"]

    def reopen_last_period(self) -> None:
        """تراجع عن آخر «بداية حساب»: تُدمج الفترة الحالية مع السابقة وتُلغى رواتبها المسجلة."""
        self._require_admin()
        current = self.current_period()
        last = self.conn.execute(
            "SELECT * FROM pay_periods WHERE end_date IS NOT NULL ORDER BY end_date DESC LIMIT 1"
        ).fetchone()
        if current is None or last is None:
            raise ServiceError("لا توجد فترة مغلقة للتراجع عنها.")
        with self.conn:
            self.conn.execute("DELETE FROM period_payouts WHERE period_id = ?", (last["id"],))
            self.conn.execute("DELETE FROM pay_periods WHERE id = ?", (current["id"],))
            self.conn.execute(
                "UPDATE pay_periods SET end_date = NULL, closed_at = NULL WHERE id = ?",
                (last["id"],))
            self._log("تراجع عن دفع الرواتب", f"الفترة من {last['start_date']}")

    def period_for_date(self, day: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM pay_periods WHERE start_date <= ? AND (end_date IS NULL OR end_date >= ?) "
            "ORDER BY id DESC LIMIT 1", (day, day)).fetchone()
        return self._period_dict(row) if row else None

    def period_weeks(self, period: dict) -> list[dict]:
        """أسابيع الفترة: الأسبوع 1 = الأيام 1–7 من بداية الفترة، وهكذا."""
        weeks = max(self.PERIOD_WEEKS, -(-period["days"] // 7))
        out = []
        for i in range(weeks):
            start = self._add_days(period["start_date"], 7 * i)
            end = self._add_days(start, 6)
            if period["end_date"] and start > period["end_date"]:
                break
            if period["end_date"] and end > period["end_date"]:
                end = period["end_date"]
            out.append({"number": i + 1, "start": start, "end": end})
        return out

    def period_payouts(self, period_id: int) -> dict[int, dict]:
        return {r["teacher_id"]: dict(r) for r in self.conn.execute(
            "SELECT * FROM period_payouts WHERE period_id = ?", (period_id,))}

    def teacher_detail(self, teacher_id: int, period: str):
        """تفاصيل حصص أستاذ خلال شهر."""
        start, end = self.month_range(period)
        rows = self.conn.execute("""
            SELECT le.id, le.lesson_date, g.name AS group_name, sub.name AS subject_name,
                   lv.name AS level_name,
                   COALESCE(SUM(a.present), 0) AS attendances,
                   COUNT(a.student_id) - COALESCE(SUM(a.present), 0) AS absents,
                   COALESCE(SUM(CASE WHEN a.present = 1 THEN a.price END), 0) AS total
              FROM lessons le
              JOIN groups g ON g.id = le.group_id
              JOIN subjects sub ON sub.id = g.subject_id
              JOIN levels lv ON lv.id = g.level_id
              LEFT JOIN attendance a ON a.lesson_id = le.id
             WHERE g.teacher_id = ? AND le.lesson_date BETWEEN ? AND ?
             GROUP BY le.id ORDER BY le.lesson_date, g.name""",
            (teacher_id, start, end)).fetchall()
        return [dict(r) for r in rows]

    def record_teacher_payout(self, teacher_id: int, period: str, amount: int,
                              notes: str = "") -> None:
        self._require_admin()
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO teacher_payouts(teacher_id, period, amount, user_id, notes) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (teacher_id, period, amount, self.user.id if self.user else None, notes))
                self._log("دفع مستحقات أستاذ", f"أستاذ {teacher_id} شهر {period}: {amount} دج")
        except sqlite3.IntegrityError:
            raise ServiceError("مستحقات هذا الشهر مسجلة كمدفوعة مسبقاً.")

    def cancel_teacher_payout(self, teacher_id: int, period: str) -> None:
        self._require_admin()
        with self.conn:
            self.conn.execute("DELETE FROM teacher_payouts WHERE teacher_id = ? AND period = ?",
                              (teacher_id, period))
            self._log("إلغاء دفع مستحقات أستاذ", f"أستاذ {teacher_id} شهر {period}")

    def academy_summary(self, date_from: str, date_to: str) -> dict:
        cash = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM payments "
            "WHERE cancelled = 0 AND date(paid_at) BETWEEN ? AND ?",
            (date_from, date_to)).fetchone()
        per_teacher = self.conn.execute("""
            SELECT g.teacher_id, COALESCE(SUM(a.price), 0) AS total, COUNT(*) AS n
              FROM attendance a
              JOIN lessons le ON le.id = a.lesson_id
              JOIN groups g ON g.id = le.group_id
             WHERE a.present = 1 AND le.lesson_date BETWEEN ? AND ?
             GROUP BY g.teacher_id""", (date_from, date_to)).fetchall()
        earned = sum(r["total"] for r in per_teacher)
        attendances = sum(r["n"] for r in per_teacher)
        academy_share = sum(self.split_income(r["total"])[0] for r in per_teacher)
        lessons = self.conn.execute(
            "SELECT COUNT(*) FROM lessons WHERE lesson_date BETWEEN ? AND ?",
            (date_from, date_to)).fetchone()[0]
        balances = self.conn.execute(f"""
            SELECT COALESCE(SUM(CASE WHEN b > 0 THEN b END), 0) AS prepaid,
                   COALESCE(SUM(CASE WHEN b < 0 THEN -b END), 0) AS debt,
                   COALESCE(SUM(CASE WHEN b < 0 THEN 1 END), 0) AS debtors
              FROM (SELECT ({self._BALANCE_SQL}) AS b FROM students s)""").fetchone()
        price = self.setting_int("session_price")
        return {
            "cash": cash[0], "payments_count": cash[1],
            "lessons": lessons, "attendances": attendances, "earned": earned,
            "academy_share": academy_share, "teachers_share": earned - academy_share,
            "prepaid_sessions": balances["prepaid"], "prepaid_amount": balances["prepaid"] * price,
            "debt_sessions": balances["debt"], "debt_amount": balances["debt"] * price,
            "debtors": balances["debtors"],
        }

    def dashboard(self) -> dict:
        today = today_str()
        summary = self.academy_summary(today, today)
        counts = self.conn.execute("""
            SELECT (SELECT COUNT(*) FROM students WHERE active = 1),
                   (SELECT COUNT(*) FROM teachers WHERE active = 1),
                   (SELECT COUNT(*) FROM groups WHERE active = 1)""").fetchone()
        return summary | {
            "students": counts[0], "teachers": counts[1], "groups": counts[2],
            "today_lessons": self.lessons_between(today, today),
        }

    def audit_log(self, limit: int = 300):
        return self.conn.execute("""
            SELECT a.*, u.full_name AS user_name FROM audit_log a
              LEFT JOIN users u ON u.id = a.user_id
             ORDER BY a.id DESC LIMIT ?""", (limit,)).fetchall()
