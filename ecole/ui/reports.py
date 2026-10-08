"""التقارير: كشف الأساتذة الشهري، ملخص الأكاديمية، المدينون."""

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from .. import printing
from .common import (
    RED, cell, date_edit, error, fill_table, iso, make_table,
    money, money_cell, selected_id, title_label,
)


def month_edit() -> QDateEdit:
    edit = QDateEdit(QDate.currentDate())
    edit.setDisplayFormat("yyyy-MM")
    edit.setCalendarPopup(True)
    edit.setLayoutDirection(Qt.LeftToRight)
    return edit


def period_of(edit: QDateEdit) -> str:
    return edit.date().toString("yyyy-MM")


class TeacherDetailDialog(QDialog):
    def __init__(self, store, teacher_id: int, period: str, parent=None):
        super().__init__(parent)
        self.store = store
        self.teacher = store.get_teacher(teacher_id)
        self.period = period
        self.setWindowTitle(f"تفاصيل حصص {self.teacher['full_name']} - {period}")
        self.resize(820, 560)
        self.lessons = store.teacher_detail(teacher_id, period)
        total = sum(le["total"] for le in self.lessons)
        self.academy, self.net = store.split_income(total)

        table = make_table(["التاريخ", "المادة", "المستوى", "الفوج", "الحاضرون", "الغائبون",
                            "المبلغ"])
        fill_table(table, [[le["lesson_date"], le["subject_name"], le["level_name"],
                            le["group_name"], cell(le["attendances"], align_center=True),
                            cell(le["absents"], align_center=True), money_cell(le["total"])]
                           for le in self.lessons])
        summary = QLabel(f"عدد الحصص: {len(self.lessons)}   |   المجموع: {money(total)}   |   "
                         f"نصيب الأكاديمية: {money(self.academy)}   |   "
                         f"صافي الأستاذ: {money(self.net)}")
        summary.setStyleSheet("font-weight: bold; font-size: 12pt")
        summary.setWordWrap(True)
        print_btn = QPushButton("🖨 طباعة")
        print_btn.clicked.connect(self._print)
        close = QPushButton("إغلاق")
        close.clicked.connect(self.accept)
        bar = QHBoxLayout()
        bar.addWidget(print_btn)
        bar.addStretch()
        bar.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(table)
        layout.addWidget(summary)
        layout.addLayout(bar)
        self.total = total

    def _print(self):
        rows = [[le["lesson_date"], le["subject_name"], le["level_name"], le["group_name"],
                 le["attendances"], le["absents"], money(le["total"])] for le in self.lessons]
        totals = ["المجموع", "", "", "", sum(le["attendances"] for le in self.lessons),
                  "", money(self.total)]
        html = printing.table_html(
            f"كشف الأستاذ: {self.teacher['full_name']}",
            f"شهر {self.period} — نصيب الأكاديمية: {money(self.academy)} — "
            f"صافي الأستاذ: {money(self.net)}",
            ["التاريخ", "المادة", "المستوى", "الفوج", "الحاضرون", "الغائبون", "المبلغ"],
            rows, self.store.settings(), totals)
        printing.print_html(self, html)


class TeachersTab(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.month = month_edit()
        self.month.dateChanged.connect(self.refresh)
        self.table = make_table(["الأستاذ", "الحصص", "الحضور", "المجموع", "نصيب الأكاديمية",
                                 "صافي الأستاذ"])
        self.table.doubleClicked.connect(self._detail)
        self.summary = QLabel()
        self.summary.setStyleSheet("font-weight: bold; font-size: 12pt")

        detail = QPushButton("التفاصيل")
        detail.clicked.connect(self._detail)
        print_btn = QPushButton("🖨 طباعة الكشف")
        print_btn.clicked.connect(self._print)

        top = QHBoxLayout()
        top.addWidget(QLabel("الشهر:"))
        top.addWidget(self.month)
        top.addStretch()
        # دفع الرواتب صار في «الحصيلة والرواتب» (كل 4 أسابيع)، هذا الكشف للاطلاع فقط.
        for b in (detail, print_btn):
            top.addWidget(b)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addWidget(self.summary)

    def refresh(self):
        self.rows = self.store.teachers_statement(period_of(self.month))
        fill_table(self.table, [[
            cell(r["teacher_name"], data=r["teacher_id"], bold=True),
            cell(r["lessons"], align_center=True),
            cell(r["attendances"], align_center=True),
            money_cell(r["total"]),
            money_cell(r["academy"]),
            money_cell(r["net"], bold=True),
        ] for r in self.rows])
        total = sum(r["total"] for r in self.rows)
        academy = sum(r["academy"] for r in self.rows)
        self.summary.setText(f"المجموع: {money(total)}   |   نصيب الأكاديمية: {money(academy)}"
                             f"   |   مستحقات الأساتذة: {money(total - academy)}")

    def _row(self):
        tid = selected_id(self.table)
        if tid is None:
            error(self, "اختر أستاذاً من القائمة أولاً.")
            return None
        return next(r for r in self.rows if r["teacher_id"] == tid)

    def _detail(self):
        r = self._row()
        if r:
            TeacherDetailDialog(self.store, r["teacher_id"], period_of(self.month), self).exec()

    def _print(self):
        rows = [[r["teacher_name"], r["lessons"], r["attendances"], money(r["total"]),
                 money(r["academy"]), money(r["net"])] for r in self.rows]
        total = sum(r["total"] for r in self.rows)
        academy = sum(r["academy"] for r in self.rows)
        html = printing.table_html(
            "كشف مستحقات الأساتذة", f"شهر {period_of(self.month)}",
            ["الأستاذ", "الحصص", "الحضور", "المجموع", "نصيب الأكاديمية", "صافي الأستاذ"],
            rows, self.store.settings(),
            ["المجموع", "", "", money(total), money(academy), money(total - academy)])
        printing.print_html(self, html)


class SummaryTab(QWidget):
    FIELDS = [
        ("cash", "المقبوض نقداً (الدفعات)", True),
        ("payments_count", "عدد الوصولات", False),
        ("lessons", "عدد الحصص المنجزة", False),
        ("attendances", "عدد الحضور", False),
        ("earned", "دخل الحصص المنجزة", True),
        ("academy_share", "نصيب الأكاديمية", True),
        ("teachers_share", "مستحقات الأساتذة", True),
    ]
    NOW_FIELDS = [
        ("prepaid_sessions", "حصص مدفوعة مسبقاً لم تُستهلك", False),
        ("prepaid_amount", "قيمتها (أمانة لدى الأكاديمية)", True),
        ("debtors", "عدد التلاميذ المدينين", False),
        ("debt_sessions", "حصص غير مدفوعة (دَين)", False),
        ("debt_amount", "قيمة الديون", True),
    ]

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        today = QDate.currentDate()
        self.date_from = date_edit(today.addDays(1 - today.day()))
        self.date_to = date_edit()
        for w in (self.date_from, self.date_to):
            w.dateChanged.connect(self.refresh)
        top = QHBoxLayout()
        top.addWidget(QLabel("من:"))
        top.addWidget(self.date_from)
        top.addWidget(QLabel("إلى:"))
        top.addWidget(self.date_to)
        top.addStretch()
        print_btn = QPushButton("🖨 طباعة")
        print_btn.clicked.connect(self._print)
        top.addWidget(print_btn)

        self.labels: dict[str, QLabel] = {}
        period_box = QGroupBox("خلال الفترة")
        period_form = QFormLayout(period_box)
        now_box = QGroupBox("الوضع الحالي")
        now_form = QFormLayout(now_box)
        for fields, form in ((self.FIELDS, period_form), (self.NOW_FIELDS, now_form)):
            for key, label, _ in fields:
                value = QLabel()
                value.setStyleSheet("font-size: 13pt; font-weight: bold")
                self.labels[key] = value
                form.addRow(label + ":", value)
        note = QLabel("ملاحظة: الدخل يُحسب عند حضور التلميذ، لا عند الدفع. المال المدفوع مسبقاً "
                      "ولم يُستهلك بعد هو أمانة وليس ربحاً.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #5b6b80")
        boxes = QHBoxLayout()
        boxes.addWidget(period_box)
        boxes.addWidget(now_box)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(boxes)
        layout.addWidget(note)
        layout.addStretch()

    def refresh(self):
        self.data = self.store.academy_summary(iso(self.date_from), iso(self.date_to))
        for key, _, is_money in self.FIELDS + self.NOW_FIELDS:
            v = self.data[key]
            self.labels[key].setText(money(v) if is_money else str(v))

    def _print(self):
        rows = [[label, money(self.data[k]) if m else self.data[k]]
                for k, label, m in self.FIELDS + self.NOW_FIELDS]
        html = printing.table_html(
            "ملخص الأكاديمية", f"من {iso(self.date_from)} إلى {iso(self.date_to)}",
            ["البيان", "القيمة"], rows, self.store.settings())
        printing.print_html(self, html)


class DebtorsTab(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.table = make_table(["الاسم واللقب", "المستوى", "هاتف الولي", "حصص غير مدفوعة",
                                 "المبلغ المستحق"])
        self.total = QLabel()
        self.total.setStyleSheet("font-weight: bold; font-size: 12pt")
        print_btn = QPushButton("🖨 طباعة القائمة")
        print_btn.clicked.connect(self._print)
        bar = QHBoxLayout()
        bar.addWidget(self.total)
        bar.addStretch()
        bar.addWidget(print_btn)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(bar)

    def refresh(self):
        price = self.store.setting_int("session_price")
        self.rows = self.store.list_students(only_debtors=True)
        fill_table(self.table, [[
            cell(s["full_name"], data=s["id"], bold=True), s["level_name"] or "",
            s["parent_phone"] or s["phone"],
            cell(-s["balance"], align_center=True, color=RED),
            money_cell(-s["balance"] * price, color=RED),
        ] for s in self.rows])
        total = sum(-s["balance"] for s in self.rows) * price
        self.total.setText(f"عدد المدينين: {len(self.rows)}   |   مجموع الديون: {money(total)}")

    def _print(self):
        price = self.store.setting_int("session_price")
        rows = [[s["full_name"], s["level_name"] or "", s["parent_phone"] or s["phone"],
                 -s["balance"], money(-s["balance"] * price)] for s in self.rows]
        html = printing.table_html(
            "قائمة التلاميذ المدينين", f"بتاريخ {QDate.currentDate().toString('yyyy-MM-dd')}",
            ["الاسم واللقب", "المستوى", "هاتف الولي", "الحصص", "المبلغ"], rows,
            self.store.settings())
        printing.print_html(self, html)


class ReportsPage(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.tabs = QTabWidget()
        self.tabs.addTab(TeachersTab(store), "كشف الأساتذة (شهر ميلادي)")
        self.tabs.addTab(SummaryTab(store), "ملخص الأكاديمية")
        self.tabs.addTab(DebtorsTab(store), "التلاميذ المدينون")
        self.tabs.currentChanged.connect(lambda _: self.tabs.currentWidget().refresh())
        layout = QVBoxLayout(self)
        layout.addWidget(title_label("التقارير"))
        layout.addWidget(self.tabs)

    def showEvent(self, event):
        self.tabs.currentWidget().refresh()
        super().showEvent(event)
