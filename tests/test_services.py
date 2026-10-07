import pytest

from ecole import backup, db
from ecole.services import ServiceError, Store


@pytest.fixture
def store():
    s = Store(db.connect(":memory:"))
    assert s.authenticate("admin", "admin") is not None
    return s


def make_group(store, teacher="أستاذ الرياضيات"):
    teacher_id = store.save_teacher({"full_name": teacher})
    return store.save_group({
        "name": "فوج 1",
        "teacher_id": teacher_id,
        "subject_id": store.list_subjects()[0]["id"],
        "level_id": store.list_levels()[0]["id"],
    }), teacher_id


def test_default_settings(store):
    assert store.payment_options() == {"session_price": 500, "pack_sessions": 4, "pack_price": 2000}
    assert store.split_income(500) == (167, 333)
    assert store.split_income(1500) == (500, 1000)


def test_pack_payment_and_receipt_numbers(store):
    sid = store.save_student({"full_name": "تلميذ"})
    p1 = store.create_payment(sid, "pack")
    p2 = store.create_payment(sid, "single")
    assert (p1["amount"], p1["sessions"]) == (2000, 4)
    assert (p2["amount"], p2["sessions"]) == (500, 1)
    assert p1["receipt_no"].endswith("-00001")
    assert p2["receipt_no"].endswith("-00002")
    assert store.student_balance(sid) == 5


def test_absent_not_deducted_and_debt_allowed(store):
    group_id, _ = make_group(store)
    a = store.save_student({"full_name": "أحمد"})
    b = store.save_student({"full_name": "بلال"})
    store.set_group_members(group_id, [a, b])
    store.create_payment(a, "single")
    lesson = store.get_or_create_lesson(group_id, "2026-10-05")
    store.save_attendance(lesson, {a: False, b: True})
    assert store.student_balance(a) == 1  # الغائب لا يُخصم
    assert store.student_balance(b) == -1  # الحضور برصيد صفر يصبح دَيناً
    assert [s["id"] for s in store.list_students(only_debtors=True)] == [b]


def test_pack_usable_across_groups(store):
    g1, _ = make_group(store, "أستاذ 1")
    g2, _ = make_group(store, "أستاذ 2")
    sid = store.save_student({"full_name": "تلميذ"})
    store.create_payment(sid, "pack")
    store.save_attendance(store.get_or_create_lesson(g1, "2026-10-05"), {sid: True})
    store.save_attendance(store.get_or_create_lesson(g2, "2026-10-06"), {sid: True})
    assert store.student_balance(sid) == 2


def test_cancelled_payment_removes_credit(store):
    sid = store.save_student({"full_name": "تلميذ"})
    p = store.create_payment(sid, "pack")
    with pytest.raises(ServiceError):
        store.cancel_payment(p["id"], "")
    store.cancel_payment(p["id"], "خطأ في الإدخال")
    assert store.student_balance(sid) == 0


def test_teacher_statement_split(store):
    group_id, teacher_id = make_group(store)
    students = [store.save_student({"full_name": f"تلميذ {i}"}) for i in range(4)]
    store.set_group_members(group_id, students)
    lesson = store.get_or_create_lesson(group_id, "2026-10-05")
    store.save_attendance(lesson, {students[0]: True, students[1]: True,
                                   students[2]: True, students[3]: False})
    [row] = store.teachers_statement("2026-10")
    assert row["attendances"] == 3
    assert row["total"] == 1500
    assert (row["academy"], row["net"]) == (500, 1000)
    store.record_teacher_payout(teacher_id, "2026-10", row["net"])
    assert store.teachers_statement("2026-10")[0]["paid"] == 1000
    with pytest.raises(ServiceError):
        store.record_teacher_payout(teacher_id, "2026-10", row["net"])
    assert store.teachers_statement("2026-09") == []


def test_price_kept_when_settings_change(store):
    group_id, _ = make_group(store)
    sid = store.save_student({"full_name": "تلميذ"})
    lesson = store.get_or_create_lesson(group_id, "2026-10-05")
    store.save_attendance(lesson, {sid: True})
    store.save_settings({"session_price": "600"})
    store.save_attendance(lesson, {sid: True})
    assert store.teachers_statement("2026-10")[0]["total"] == 500


def test_academy_summary(store):
    group_id, _ = make_group(store)
    a = store.save_student({"full_name": "أ"})
    b = store.save_student({"full_name": "ب"})
    store.create_payment(a, "pack")
    lesson = store.get_or_create_lesson(group_id, "2026-10-05")
    store.save_attendance(lesson, {a: True, b: True})
    s = store.academy_summary("2026-10-01", "2026-10-31")
    assert s["earned"] == 1000
    assert s["academy_share"] + s["teachers_share"] == 1000
    assert s["prepaid_sessions"] == 3
    assert s["debt_sessions"] == 1
    assert s["debtors"] == 1


def test_statement_running_balance(store):
    group_id, _ = make_group(store)
    sid = store.save_student({"full_name": "تلميذ"})
    store.create_payment(sid, "pack")
    lesson = store.get_or_create_lesson(group_id, "2099-01-01")
    store.save_attendance(lesson, {sid: True})
    events = store.student_statement(sid)
    assert [e["balance"] for e in events] == [4, 3]


def test_reception_cannot_cancel(store):
    store.save_user({"username": "recep", "role": "reception", "password": "1234"})
    sid = store.save_student({"full_name": "تلميذ"})
    p = store.create_payment(sid, "single")
    assert store.authenticate("recep", "1234") is not None
    with pytest.raises(ServiceError):
        store.cancel_payment(p["id"], "سبب")


def test_last_admin_protected(store):
    with pytest.raises(ServiceError):
        store.save_user({"id": store.user.id, "username": "admin", "role": "reception"})


def test_backup_roundtrip(tmp_path):
    db_path = tmp_path / "ecole.db"
    conn = db.connect(db_path)
    store = Store(conn)
    store.save_student({"full_name": "تلميذ"})
    path = backup.make_backup(conn, tmp_path / "bk", keep=2)
    for _ in range(3):
        backup.make_backup(conn, tmp_path / "bk", keep=2)
    assert len(list((tmp_path / "bk").glob("*.db"))) <= 2
    store.save_student({"full_name": "ثاني"})
    conn.close()
    latest = sorted((tmp_path / "bk").glob("*.db"))[-1]
    assert backup.is_valid_database(latest)
    backup.restore_backup(latest, db_path)
    assert len(Store(db.connect(db_path)).list_students()) == 1
    assert path.name.startswith(backup.PREFIX)
