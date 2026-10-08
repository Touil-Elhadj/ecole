import pytest

from ecole import db
from ecole.services import ServiceError, Store


@pytest.fixture
def store():
    s = Store(db.connect(":memory:"))
    s.authenticate("admin", "admin")
    return s


def setup_group(store, teacher="أستاذ"):
    tid = store.save_teacher({"full_name": teacher})
    gid = store.save_group({"name": "فوج 1", "teacher_id": tid,
                            "subject_id": store.list_subjects()[0]["id"],
                            "level_id": store.list_levels()[0]["id"]})
    students = [store.save_student({"full_name": f"{teacher} تلميذ {i}"}) for i in range(3)]
    store.set_group_members(gid, students)
    return tid, gid, students


def attend(store, gid, day, students):
    store.save_attendance(store.get_or_create_lesson(gid, day), {s: True for s in students})


def test_first_period_and_weeks(store):
    assert store.current_period() is None
    store.start_first_period("2026-10-01")
    p = store.current_period()
    weeks = store.period_weeks(p)
    assert [(w["start"], w["end"]) for w in weeks[:2]] == [
        ("2026-10-01", "2026-10-07"), ("2026-10-08", "2026-10-14")]
    assert len(weeks) >= 4
    with pytest.raises(ServiceError):
        store.start_first_period("2026-10-05")


def test_weekly_summary_per_teacher(store):
    store.start_first_period("2026-10-01")
    _, g1, s1 = setup_group(store, "أستاذ أ")
    _, g2, s2 = setup_group(store, "أستاذ ب")
    attend(store, g1, "2026-10-02", s1)       # الأسبوع 1: 3 حضور
    attend(store, g1, "2026-10-09", s1[:2])   # الأسبوع 2: 2 حضور
    attend(store, g2, "2026-10-03", s2[:1])   # الأسبوع 1: 1 حضور
    week1 = {r["teacher_name"]: r for r in store.teachers_summary("2026-10-01", "2026-10-07")}
    assert week1["أستاذ أ"]["total"] == 1500
    assert (week1["أستاذ أ"]["academy"], week1["أستاذ أ"]["net"]) == (500, 1000)
    assert week1["أستاذ ب"]["total"] == 500
    period = {r["teacher_name"]: r for r in store.teachers_summary("2026-10-01", "2026-10-28")}
    assert period["أستاذ أ"]["attendances"] == 5


def test_close_period_records_pay_and_starts_new(store):
    store.start_first_period("2026-10-01")
    tid, gid, students = setup_group(store)
    attend(store, gid, "2026-10-02", students)
    attend(store, gid, "2026-10-30", students)  # بعد يوم الدفع: للفترة الجديدة
    closed = store.close_period("2026-10-28")
    payouts = store.period_payouts(closed)
    assert payouts[tid]["total"] == 1500
    assert payouts[tid]["amount"] == 1000
    new = store.current_period()
    assert new["start_date"] == "2026-10-29"
    assert store.get_period(closed)["end_date"] == "2026-10-28"
    assert store.period_for_date("2026-10-30")["id"] == new["id"]


def test_reopen_last_period(store):
    store.start_first_period("2026-10-01")
    tid, gid, students = setup_group(store)
    attend(store, gid, "2026-10-02", students)
    closed = store.close_period("2026-10-28")
    store.reopen_last_period()
    p = store.current_period()
    assert p["id"] == closed and p["end_date"] is None
    assert store.period_payouts(closed) == {}
    with pytest.raises(ServiceError):
        store.reopen_last_period()


def test_close_period_validates_dates(store):
    with pytest.raises(ServiceError):
        store.close_period("2026-10-28")
    store.start_first_period("2026-10-10")
    with pytest.raises(ServiceError):
        store.close_period("2026-10-05")


def test_reception_cannot_close(store):
    store.start_first_period("2026-10-01")
    store.save_user({"username": "r", "role": "reception", "password": "1234"})
    store.authenticate("r", "1234")
    with pytest.raises(ServiceError):
        store.close_period("2026-10-28")
